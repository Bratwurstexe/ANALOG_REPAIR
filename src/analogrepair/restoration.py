"""Frame-by-frame export path: the repair of tapes and film, date stamp removal,
fusion (noise reduction and upscaling) and the look.

The methods use optical-flow alignment and conservative error gating. They do
not claim to reconstruct content absent from every neighboring frame.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
from pathlib import Path
import subprocess
import tempfile
import threading
from typing import Callable, Iterable, Iterator

import cv2
import numpy as np

from .look import Look, look_frame, look_stream
from .media import PROCESS_FLAGS, VideoKenndaten
from .movie import (DEINTERLACE, colour_stream, dust_stream, flicker_stream, interlaced,
                    stabilise_stream, tape_stream)
from .osd import detect_osd, remove_stream
from .processor import (Laufergebnis, caption_workspace, encoding_options,
                        diagnostic_tail, output_duration, temporary_output, video_filters)
from .recipe import Arbeitsrezept
from .upscale import fuse_stream, target_size


# Date stamp mask (0/255) and guide of steady edge orientations, see osd.find_osd.
Overlay = tuple[np.ndarray, np.ndarray]


def _fused(recipe: Arbeitsrezept) -> bool:
    """Whether the multi-frame fusion stage runs (noise reduction or a new size)."""
    return recipe.vergroesserung_prozent != 100 or recipe.rauschminderung > 0


@dataclass(frozen=True)
class _Effort:
    """How much work the frame stages spend: neighbours, flow detail, fill size."""

    colour_radius: int
    colour_flow: int
    osd_radius: int
    osd_flow: int
    osd_fill: float
    fusion_radius: int
    fusion_flow: int
    fusion_preset: int
    fusion_interpolation: int


EFFORTS = {
    "fast": _Effort(2, 240, 3, cv2.DISOPTICAL_FLOW_PRESET_ULTRAFAST, 0.5,
                    1, 320, cv2.DISOPTICAL_FLOW_PRESET_ULTRAFAST, cv2.INTER_LINEAR),
    "balanced": _Effort(3, 320, 4, cv2.DISOPTICAL_FLOW_PRESET_FAST, 0.5,
                        2, 400, cv2.DISOPTICAL_FLOW_PRESET_FAST, cv2.INTER_LINEAR),
    "best": _Effort(3, 320, 6, cv2.DISOPTICAL_FLOW_PRESET_FAST, 1.0,
                    2, 480, cv2.DISOPTICAL_FLOW_PRESET_MEDIUM, cv2.INTER_CUBIC),
}


# Share of the grain that "Keep film grain" leaves in the fused picture.
GRAIN_KEPT = 0.3


def _movie_stages(stream: Iterable[np.ndarray], recipe: Arbeitsrezept, osd: Overlay | None,
                  effort: _Effort, fps: float) -> Iterable[np.ndarray]:
    """The repair of tapes and film, see movie.py; deinterlacing happened in the decoder.

    The date stamp is painted out before anything moves the picture, so it is
    still where it was found. Stages left at 0 are skipped.
    """
    stream = tape_stream(stream, recipe.bandstoerung, fps)
    if recipe.osd_entfernen and osd is not None:
        stream = remove_stream(stream, *osd, effort.osd_radius, effort.osd_flow, effort.osd_fill)
    stream = flicker_stream(stream, recipe.flackerausgleich)
    stream = dust_stream(stream, recipe.staubentfernung)
    stream = stabilise_stream(stream, recipe.stabilisierung, fps)
    stream = colour_stream(stream, recipe.farbberuhigung, effort.colour_radius, effort.colour_flow)
    # A colourisation stage for black-and-white film belongs here: after every
    # repair, before fusion and upscaling.
    return stream


def _stages(frames: Iterable[np.ndarray], recipe: Arbeitsrezept,
            osd: Overlay | None, first_index: int = 0, look: bool = True,
            fps: float = 25.0) -> Iterator[np.ndarray]:
    """Chain the frame stages in their fixed order: tape and film repair (with the
    date stamp), fusion, look.

    ``first_index`` is the frame number of the first frame in the recording; the
    film grain of the look is seeded with it. ``look=False`` leaves the look out.
    ``fps`` sets the time spans of the tape and film stages.
    """
    effort = EFFORTS[recipe.aufwand]
    stream: Iterable[np.ndarray] = _movie_stages(frames, recipe, osd, effort, fps)
    if _fused(recipe):
        keep = GRAIN_KEPT if recipe.koernung_behalten else 0.0
        stream = fuse_stream(stream, recipe.vergroesserung_prozent, recipe.rauschminderung / 100,
                             recipe.kantendetail / 50, effort.fusion_radius, effort.fusion_flow,
                             effort.fusion_preset, effort.fusion_interpolation, keep)
    finish = Look.of(recipe)
    if look and finish.active:
        stream = look_stream(stream, finish, first_index)
    return iter(stream)


def clip_mask(source: Path, recipe: Arbeitsrezept, info: VideoKenndaten,
               duration: float) -> Overlay | None:
    """Date stamp mask and guide for the cut; only needed when the stamp is removed."""
    if recipe.osd_entfernen:
        return detect_osd(source, recipe.schnittbeginn, duration, info.width, info.height)
    return None


def _crop(osd: Overlay, box: tuple[int, int, int, int]) -> Overlay:
    x, y, width, height = box
    mask, guide = osd
    return (np.ascontiguousarray(mask[y:y + height, x:x + width]),
            np.ascontiguousarray(guide[y:y + height, x:x + width]))


BAR_LEVEL = 24
BAR_SAMPLES = 8


def picture_box(source: Path, start: float, duration: float,
                width: int, height: int) -> tuple[int, int, int, int]:
    """(x, y, width, height) of the picture inside black side or top bars.

    Tape transfers often hold a 4:3 picture in a 16:9 file, film scans a
    picture inside a black surround. The bars are no picture and need no
    repair, so the stages skip them: up to a quarter less work. A side counts
    as bars only when it stays dark in every sampled frame and adds up to at
    least 5 % of the frame; otherwise the whole frame is returned.
    """
    capture = cv2.VideoCapture(str(source))
    brightest = None
    try:
        for index in range(BAR_SAMPLES):
            capture.set(cv2.CAP_PROP_POS_MSEC, (start + duration * (index + 0.5) / BAR_SAMPLES) * 1000)
            okay, frame = capture.read()
            if not okay or frame.shape[:2] != (height, width):
                continue
            luma = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightest = luma if brightest is None else np.maximum(brightest, luma)
    finally:
        capture.release()
    if brightest is None:
        return 0, 0, width, height

    def span(profile: np.ndarray, size: int) -> tuple[int, int]:
        lit = np.flatnonzero(profile > BAR_LEVEL)
        if not len(lit):
            return 0, size
        first, last = int(lit[0]), int(lit[-1]) + 1
        if first + size - last < size * 0.05:
            return 0, size
        # Even edges keep the 4:2:0 chroma of the output aligned.
        first, last = first - first % 2, min(size, last + last % 2)
        return first, last - first

    # A high percentile instead of the maximum ignores single noisy pixels.
    x, inner_width = span(np.percentile(brightest, 90, axis=0), width)
    y, inner_height = span(np.percentile(brightest, 90, axis=1), height)
    return x, y, inner_width, inner_height


def _placement(box: tuple[int, int, int, int], width: int, height: int,
               percent: int) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    """Picture size, frame size and picture position in the output frame."""
    x, y, inner_width, inner_height = box
    full = target_size(width, height, percent) if percent != 100 else (width, height)
    inner = target_size(inner_width, inner_height, percent) if percent != 100 else (inner_width, inner_height)
    offset = (min(full[0] - inner[0], round(x * full[0] / width / 2) * 2),
              min(full[1] - inner[1], round(y * full[1] / height / 2) * 2))
    return inner, full, offset


def preview_frame(source: Path, seconds: float, recipe: Arbeitsrezept, info: VideoKenndaten,
                  osd: Overlay | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Original and processed frame at ``seconds``, run through the full stage chain."""
    before, _, after = preview_frames(source, seconds, recipe, info, osd)
    return before, after


def preview_frames(source: Path, seconds: float, recipe: Arbeitsrezept, info: VideoKenndaten,
                   osd: Overlay | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Original, repaired without the look, and fully processed frame at ``seconds``.

    A short run of frames around the moment is decoded so that every temporal
    stage sees real neighbours; ``osd`` can carry a mask detected earlier.
    Without a look the last two are the same picture.
    """
    recipe.validate()
    duration = output_duration(info, recipe)
    if osd is None:
        osd = clip_mask(source, recipe, info, duration)
    box = picture_box(source, recipe.schnittbeginn, duration, info.width, info.height)
    # Stabilising smooths the motion over up to half a second; give it that much on each side.
    lead, span = 0.6, 1.2
    start = max(0.0, seconds - lead)
    preroll = min(3.0, start)

    def decode(filters: str) -> list[np.ndarray]:
        args = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "quiet", "-ss", str(start - preroll),
                "-i", str(source), "-ss", str(preroll), "-t", str(span), "-map", "0:v:0"]
        if filters:
            args.extend(["-vf", filters])
        args.extend(["-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1"])
        raw = subprocess.run(args, capture_output=True, timeout=120, creationflags=PROCESS_FLAGS).stdout
        size = info.width * info.height * 3
        return [np.frombuffer(raw[index:index + size], np.uint8).reshape(info.height, info.width, 3)
                for index in range(0, len(raw) - size + 1, size)]

    frames = decode("")
    if not frames:
        raise ValueError("Could not decode frames at this moment")
    middle = min(len(frames) - 1, round((seconds - start) / span * len(frames)))
    # The original is shown as recorded; the repair starts from full frames.
    worked = (decode(DEINTERLACE) or frames) if interlaced(source, info, recipe.schnittbeginn,
                                                          duration) else frames
    middle = min(middle, len(worked) - 1)
    x, y, inner_width, inner_height = box
    pictures = [np.ascontiguousarray(frame[y:y + inner_height, x:x + inner_width]) for frame in worked]
    if osd is not None:
        osd = _crop(osd, box)
    # Stages are lazy: stop as soon as the frame of interest has come through.
    # The look is the last stage and needs no neighbours, so it is applied to
    # that one frame only, with the frame number an export would give it.
    plain = next(islice(_stages(pictures, recipe, osd, look=False, fps=info.fps or 25.0),
                        middle, None))
    finished = look_frame(plain, Look.of(recipe), round(start * info.fps) + middle)
    _, (full_width, full_height), (left, top) = _placement(box, info.width, info.height,
                                                           recipe.vergroesserung_prozent)

    def placed(picture: np.ndarray) -> np.ndarray:
        result = np.zeros((full_height, full_width, 3), np.uint8)
        result[top:top + picture.shape[0], left:left + picture.shape[1]] = picture
        return result

    return frames[middle], placed(plain), placed(finished)


# Seconds of footage decoded before and after a cut as repair context.
CONTEXT_SECONDS = 0.5


def _decoder(source: Path, start: float, seconds: float, fps: float,
             box: tuple[int, int, int, int], deinterlace: bool = False) -> list[str]:
    # FFmpeg's timestamp seek is reliable for damaged transport streams; OpenCV's
    # CAP_PROP_POS_MSEC can land several frames before the requested cut.
    args = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error"]
    if start > 0:
        args.extend(["-ss", f"{start:.6f}"])
    crop = "crop={2}:{3}:{0}:{1}".format(*box)
    # Fields are woven into full frames first, one frame per frame, on the whole picture.
    args.extend(["-i", str(source), "-t", f"{seconds:.6f}", "-map", "0:v:0", "-an", "-sn",
                 "-vf", f"{DEINTERLACE},{crop}" if deinterlace else crop, "-r", f"{fps:.6f}",
                 "-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1"])
    return args


def _encoder(size: tuple[int, int], fps: float) -> list[str]:
    return ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{size[0]}x{size[1]}",
            "-r", f"{fps:.6f}", "-i", "pipe:0"]


def _pump(decoder_args: list[str], encoder_args: list[str], workplace: str | None, size: tuple[int, int],
          frame_limit: int, recipe: Arbeitsrezept, osd: Overlay | None,
          cancel: threading.Event, report: Callable[[int], None],
          skip: int = 0, decode_limit: int | None = None, first_index: int = 0,
          fps: float = 25.0) -> str:
    """Decode frames, run the stages and encode ``frame_limit`` of them.

    ``skip`` frames before the cut and the frames after it (up to
    ``decode_limit`` decoded in all) give the first and last frames of the cut
    real neighbours to be repaired from; they are not written out.
    ``first_index`` is the frame number of the first decoded frame.
    Returns an error message, or "" on success.
    """
    width, height = size
    log = tempfile.TemporaryFile(mode="w+b")
    decoder_log = tempfile.TemporaryFile(mode="w+b")
    decoder = None
    encoder = None
    try:
        decoder = subprocess.Popen(decoder_args, stdout=subprocess.PIPE,
                                   stderr=decoder_log, creationflags=PROCESS_FLAGS)
        encoder = subprocess.Popen(encoder_args, stdin=subprocess.PIPE, stderr=log,
                                   cwd=workplace, creationflags=PROCESS_FLAGS)
        sent = 0
        frame_bytes = width * height * 3
        assert decoder.stdout is not None
        assert encoder.stdin is not None

        def decoded() -> Iterator[np.ndarray]:
            for _ in range(decode_limit or frame_limit + skip):
                raw = decoder.stdout.read(frame_bytes)
                if len(raw) != frame_bytes or cancel.is_set():
                    return
                yield np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3)

        passed = 0
        for enhanced in _stages(decoded(), recipe, osd, first_index, fps=fps):
            if cancel.is_set() or sent >= frame_limit:
                break
            if passed < skip:
                passed += 1
                continue
            encoder.stdin.write(enhanced.tobytes())
            sent += 1
            report(sent)
        encoder.stdin.close()
        decoder.stdout.close()
        if decoder.poll() is None:
            decoder.terminate()
        decoder.wait(timeout=30)
        encoder.wait(timeout=120)
        if encoder.returncode or sent == 0:
            return diagnostic_tail(log) or diagnostic_tail(decoder_log) or "Temporal export failed"
        return ""
    except Exception:
        for proc in (decoder, encoder):
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait()
        raise
    finally:
        if decoder is not None and decoder.stdout:
            decoder.stdout.close()
        if encoder is not None and encoder.stdin and not encoder.stdin.closed:
            encoder.stdin.close()
        log.close()
        decoder_log.close()


def process_temporal(source: Path, target: Path, recipe: Arbeitsrezept, info: VideoKenndaten,
                     progress: Callable[[float], None],
                     cancel: threading.Event) -> Laufergebnis:
    """Frame-by-frame export: tape and film repair, date stamp, noise reduction, upscaling, look."""
    recipe.validate()
    duration = output_duration(info, recipe)
    source = source.resolve()
    target = target.resolve()
    if source == target:
        raise ValueError("Source and destination must differ")
    osd = clip_mask(source, recipe, info, duration)
    # Fusion applies detail and size itself; FFmpeg must not do it again.
    filters = video_filters(recipe, upscaled=_fused(recipe))
    options = encoding_options(recipe, info, duration)
    fps = info.fps
    if not fps:
        capture = cv2.VideoCapture(str(source))
        fps = capture.get(cv2.CAP_PROP_FPS) if capture.isOpened() else 0.0
        capture.release()
    if fps <= 0 or fps > 240:
        raise ValueError("Could not read video frame rate")
    box = picture_box(source, recipe.schnittbeginn, duration, info.width, info.height)
    x, y, width, height = box
    if osd is not None:
        osd = _crop(osd, box)
    out_size, (full_width, full_height), (left, top) = _placement(box, info.width, info.height,
                                                                  recipe.vergroesserung_prozent)
    if out_size != (full_width, full_height):
        # The stages see the picture only; the bars come back as clean black.
        filters = f"pad={full_width}:{full_height}:{left}:{top}:black," + filters
    frame_limit = max(1, round(duration * fps))
    # Context around the cut: the repair of the first and last frames can then
    # draw on neighbours that lie just outside the kept part.
    lead = min(recipe.schnittbeginn, CONTEXT_SECONDS)
    tail = max(0.0, min(CONTEXT_SECONDS, info.duration - (recipe.schnittbeginn + duration)))
    lead_frames = round(lead * fps)
    decode_limit = lead_frames + frame_limit + round(tail * fps)
    workspace = None
    try:
        workspace = caption_workspace(recipe)
        pending = temporary_output(target)
    except Exception:
        if workspace:
            workspace.cleanup()
        raise
    # Only the caption filter needs a working directory (relative font and text paths).
    workplace = workspace.name if workspace else None
    try:
        encoder_args = _encoder(out_size, fps)
        if info.has_audio:
            if recipe.schnittbeginn:
                encoder_args.extend(["-ss", str(recipe.schnittbeginn)])
            encoder_args.extend(["-i", str(source)])
        encoder_args.extend(["-map", "0:v:0"])
        if info.has_audio:
            encoder_args.extend(["-map", "1:a?"])
        encoder_args.extend(["-t", str(duration), "-vf", filters])
        encoder_args.extend(options)
        encoder_args.extend(["-shortest", str(pending)])
        deinterlace = interlaced(source, info, recipe.schnittbeginn, duration)
        message = _pump(_decoder(source, recipe.schnittbeginn - lead_frames / fps, lead + duration + tail, fps, box,
                                 deinterlace),
                        encoder_args, workplace, (width, height), frame_limit, recipe, osd, cancel,
                        lambda sent: progress(min(1.0, sent / frame_limit)),
                        skip=lead_frames, decode_limit=decode_limit,
                        first_index=max(0, round(recipe.schnittbeginn * fps) - lead_frames), fps=fps)
        if cancel.is_set():
            return Laufergebnis(source, target, False, "Canceled")
        if message:
            return Laufergebnis(source, target, False, message)
        pending.replace(target)
        progress(1.0)
        return Laufergebnis(source, target, True, "Done")
    finally:
        pending.unlink(missing_ok=True)
        if workspace:
            workspace.cleanup()
