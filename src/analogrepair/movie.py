"""The repair of digitised tapes (VHS, S-VHS, Hi8, Video8, camcorder) and film
(8 mm, Super 8, 16 mm).

Tape loses whole rows to
tracking noise, shows a torn band at the bottom where the video heads switch
and lets lines wander sideways (time-base error); its colour is smeared far
wider than its brightness. Film collects dust and scratches, flickers from
frame to frame and weaves in the gate. Every stage below compares a frame
with its motion-aligned neighbours and changes only what clearly stands out
against them, so a clean clip passes nearly unchanged.

The stages, in the order ``restoration._stages`` runs them:

1. Deinterlacing (``interlaced``): interlaced tape transfers are turned into
   full frames by FFmpeg's bwdif filter in the decoder, before anything else.
2. Tape noise (``tape_stream``): rows far off the median of the aligned
   neighbours and full of fine detail are tracking noise and are refilled
   from the neighbours; a broken band that sits at the bottom of nearly every
   frame is the head switch and is masked black; every line is shifted back
   onto the neighbours by a 1-D match of its horizontal gradient.
3. Date stamp: ``osd.remove_stream`` (in ``restoration``), before anything
   moves the picture, so the stamp is still where it was found.
4. Flicker (``flicker_stream``): brightness gain and offset, each a plane
   across the picture, fitted to the median of the aligned neighbours of the
   same shot. Slow exposure changes survive, as the median follows them.
5. Dust, dropouts and scratches (``dust_stream``): a pixel that is brighter
   (or darker) than both aligned neighbours while they agree with each other
   is a speck and is refilled from them. Thin columns that differ from both
   sides over most rows in most frames are scratches and are filled across.
6. Stabilising (``stabilise_stream``): a similarity motion per frame from
   tracked corners, a trajectory smoothed by a local linear fit, and a warp
   by the difference; the uncovered border comes from neighbouring frames.
7. Colour (``colour_stream``): the analog chroma re-estimation of
   ``analog.repair_stream``, then chroma sharpened along luma edges against
   the colour bleed of tape. Skipped for black-and-white footage.
   A colourisation stage for black-and-white film would follow here, after
   every repair and before fusion and upscaling.
8. Fusion and upscaling (``upscale.fuse_stream``), which can keep a share of
   the film grain.

Duplicated frames are common in transfers (Super 8 at 18 fps stored as 25 or
50 fps, old film with every frame twice or three times). They carry the same
dust and the same flicker, so the stages compare against the nearest
*distinct* frames.
"""

from __future__ import annotations

from collections import deque
from itertools import chain, islice
import math
from pathlib import Path
import subprocess
from typing import Iterable, Iterator

import cv2
import numpy as np

from .analog import repair_stream
from .media import PROCESS_FLAGS, VideoKenndaten
from .pipeline import PerThread, SafeDIS, ordered_map, window_map
from .upscale import _median


# Shot boundaries: correlation of two normalised 64 x 48 thumbnails below this.
CUT_LIKENESS = 0.45
# A neighbour is a copy of the frame (not a new picture) below this mean
# luma difference, or below this share of the largest difference around.
DUP_FLOOR = 0.3
DUP_SHARE = 0.3

# Interlacing: a line that sticks out from both lines next to it while the
# lines two away agree with it is a comb tooth.
COMB_STEP = 12.0
COMB_SHARE = 0.004
INTERLACED_ORDERS = {"tt", "bb", "tb", "bt"}
DEINTERLACE = "bwdif=mode=send_frame:parity=auto:deint=all"

TAPE_RADIUS = 2
TAPE_FLOW_WIDTH = 320
# The head switch tears at most this share of the picture at the bottom.
SWITCH_ZONE = 0.08
# Rows of a time-base error that count as one wobble; slower drifts are picture motion.
JITTER_SLOW = 12.0
JITTER_MIN = 0.35
JITTER_SHARE = 0.2

FLICKER_RADIUS = 6
FLICKER_WIDTH = 160

DUST_RADIUS = 3
DUST_FLOW_WIDTH = 480
# Specks larger than this share of the picture are moving things the
# alignment missed, not dirt.
SPECK_AREA = 0.004
SPECKS_AT_MOST = 0.03
# Share of a neighbourhood (an eighth of the width across) covered with
# specks above which they are texture, not dirt.
SPECK_CROWD = 0.12
# Share of rows (and of frames in the window) a scratch must cover.
SCRATCH_ROWS = 0.75
SCRATCH_FRAMES = 0.6

STABLE_WIDTH = 480
STABLE_REACH = 30
# Largest correction, as a share of the picture width.
STABLE_LIMIT = 0.06
# Corrections below this many pixels are left out.
STABLE_DEAD = 0.6
# Luma below which a region touching the frame border is surround (bars, gate), not picture.
SURROUND_LEVEL = 20

COLOUR_PROBE = 12
# Brightness difference (grey levels) at which a sample counts as the other side of an edge.
BLEED_MATCH = 12.0
BLEED_SELF = 0.15


# ------------------------------------------------------------------ helpers


def _gray(frame: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def _shrink(gray: np.ndarray, width: int) -> np.ndarray:
    height, full = gray.shape
    factor = min(1.0, width / full)
    return cv2.resize(gray, (max(8, round(full * factor)), max(8, round(height * factor))),
                      interpolation=cv2.INTER_AREA)


def _tiny(gray: np.ndarray) -> np.ndarray:
    """A 64 x 48 thumbnail with zero mean and unit spread, for shot boundaries."""
    thumb = cv2.resize(gray, (64, 48), interpolation=cv2.INTER_AREA).astype(np.float32)
    return (thumb - thumb.mean()) / max(float(thumb.std()), 1.0)


def same_shot(first: np.ndarray, second: np.ndarray) -> bool:
    """Whether two thumbnails from ``_tiny`` show the same shot.

    The thumbnails are normalised, so a flicker or a fade does not count as
    a cut; a frame without any structure (black) does.
    """
    return float((first * second).mean()) > CUT_LIKENESS


class _Flow:
    """Dense optical flow on reduced frames and warping at any size, one per pool thread."""

    def __init__(self, preset: int = cv2.DISOPTICAL_FLOW_PRESET_MEDIUM) -> None:
        self.dis = SafeDIS(preset)
        self.grids: dict[tuple[int, int], tuple[np.ndarray, np.ndarray]] = {}

    def calc(self, present: np.ndarray, other: np.ndarray) -> np.ndarray:
        """Flow from ``present`` into ``other``: present(x) matches other(x + flow(x))."""
        return self.dis.calc(present, other, None)

    def warp(self, image: np.ndarray, flow: np.ndarray) -> np.ndarray:
        """``image`` (any size) moved onto the grid of the frame the flow was measured from."""
        height, width = image.shape[:2]
        if (width, height) not in self.grids:
            self.grids[width, height] = tuple(np.meshgrid(np.arange(width, dtype=np.float32),
                                                          np.arange(height, dtype=np.float32)))
        grid_x, grid_y = self.grids[width, height]
        small_height, small_width = flow.shape[:2]
        if (small_width, small_height) != (width, height):
            flow = cv2.resize(flow, (width, height), interpolation=cv2.INTER_LINEAR)
        return cv2.remap(image, grid_x + flow[:, :, 0] * (width / small_width),
                         grid_y + flow[:, :, 1] * (height / small_height),
                         cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def _pick(window: list, center: int, per_side: int) -> tuple[list[int], list[int]]:
    """Up to ``per_side`` distinct frames before and after the centre, nearest first.

    Frames across a cut are never used, and copies of the centre frame are
    skipped: they carry the same dust and the same flicker.
    """
    present = window[center]
    sides: list[list[int]] = []
    for step in (-1, 1):
        found, index, last = [], center + step, present
        while 0 <= index < len(window) and same_shot(last.tiny, window[index].tiny):
            found.append(index)
            last = window[index]
            index += step
        sides.append(found)
    gaps = {index: float(cv2.absdiff(present.small, window[index].small).mean()) for index in sides[0] + sides[1]}
    if not gaps:
        return [], []
    floor = max(DUP_FLOOR, DUP_SHARE * max(gaps.values()))
    before, after = ([index for index in side if gaps[index] > floor][:per_side] for side in sides)
    return before, after


def _runs(flags: np.ndarray, gap: int, shortest: int) -> np.ndarray:
    """Close gaps of up to ``gap`` rows in a row mask and drop runs shorter than ``shortest``."""
    flags = flags.astype(np.uint8)[:, None]
    if gap:
        flags = cv2.morphologyEx(flags, cv2.MORPH_CLOSE, np.ones((gap + 2, 1), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(flags, connectivity=4)
    keep = stats[:, cv2.CC_STAT_HEIGHT] >= shortest
    keep[0] = False
    return keep[labels[:, 0]]


def _normalised_blur(values: np.ndarray, weight: np.ndarray, sigma: float) -> tuple[np.ndarray, np.ndarray]:
    """Weighted vertical Gaussian of a per-row signal; also returns the blurred weight."""
    column = np.ascontiguousarray(np.stack([values * weight, weight], axis=1).astype(np.float32))[:, None, :]
    blurred = cv2.GaussianBlur(column, (1, 0), sigmaX=0.1, sigmaY=sigma, borderType=cv2.BORDER_REPLICATE)[:, 0, :]
    return blurred[:, 0] / np.maximum(blurred[:, 1], 1e-6), blurred[:, 1]


# ------------------------------------------------------------ deinterlacing


def combing(gray: np.ndarray) -> float:
    """Share of pixels that look like comb teeth of interlaced motion."""
    luma = gray.astype(np.float32)
    middle = luma[2:-2]
    up, down = middle - luma[1:-3], middle - luma[3:-1]
    tooth = np.minimum(np.abs(up), np.abs(down))
    same_field = np.maximum(np.abs(middle - luma[:-4]), np.abs(middle - luma[4:]))
    teeth = (up * down > 0) & (tooth > COMB_STEP) & (same_field < 0.5 * tooth)
    return float(teeth.mean())


def _sample_gray(source: Path, start: float, duration: float, width: int, height: int,
                 count: int) -> list[np.ndarray]:
    args = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "quiet"]
    if start:
        args.extend(["-ss", f"{start:.3f}"])
    args.extend(["-i", str(source), "-t", f"{max(0.2, duration):.3f}", "-map", "0:v:0",
                 "-vf", f"fps={max(count / max(duration, 0.2), 0.05):.6f}", "-frames:v", str(count),
                 "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"])
    raw = subprocess.run(args, capture_output=True, timeout=300, creationflags=PROCESS_FLAGS).stdout
    size = width * height
    return [np.frombuffer(raw[index:index + size], np.uint8).reshape(height, width)
            for index in range(0, len(raw) - size + 1, size)]


def interlaced(source: Path, info: VideoKenndaten, start: float, duration: float) -> bool:
    """Whether the cut was recorded as interlaced fields and needs deinterlacing.

    A field order in the file decides. Many transfers are stored as
    progressive although they were captured from fields, so without one the
    picture is checked for comb teeth: most sampled frames must show them
    (frames without motion show none, so a share of them may be clean).
    """
    if info.field_order in INTERLACED_ORDERS:
        return True
    frames = _sample_gray(source, start, duration, info.width, info.height, 12)
    if len(frames) < 3:
        return False
    shares = sorted(combing(frame) for frame in frames)
    return shares[len(shares) // 2] > COMB_SHARE


# --------------------------------------------------------------- tape noise


class _TapeFrame:
    def __init__(self, frame: np.ndarray) -> None:
        self.frame = frame
        gray = _gray(frame)
        self.luma = gray.astype(np.float32)
        self.small = _shrink(gray, TAPE_FLOW_WIDTH)
        self.tiny = _tiny(gray)


def _row_shifts(luma: np.ndarray, reference: np.ndarray, reach: int) -> tuple[np.ndarray, np.ndarray]:
    """Per row, the horizontal shift that lines ``luma`` up with ``reference``, and its weight 0..1.

    Rows are compared by their horizontal gradient, averaged over three
    rows; the minimum is refined with a parabola. A row counts only when it
    has texture, the shift clearly fits better than no shift, and the left,
    middle and right thirds of the row agree on it: a time-base error moves
    the whole line, while motion the alignment missed differs across it.
    """
    height, width = luma.shape
    own = cv2.Sobel(luma, cv2.CV_32F, 1, 0, ksize=3)
    theirs = cv2.Sobel(reference, cv2.CV_32F, 1, 0, ksize=3)
    span = width - 2 * reach
    bounds = [reach + span * part // 3 for part in range(4)]
    thirds = np.empty((3, 2 * reach + 1, height), np.float32)
    for index, shift in enumerate(range(-reach, reach + 1)):
        for part in range(3):
            left, right = bounds[part], bounds[part + 1]
            thirds[part, index] = cv2.absdiff(own[:, left + shift:right + shift], theirs[:, left:right]).mean(axis=1)
    thirds = np.stack([cv2.blur(part, (3, 1), borderType=cv2.BORDER_REPLICATE) for part in thirds])
    costs = thirds.mean(axis=0)
    picks = thirds.argmin(axis=1)
    agree = (picks.max(axis=0) - picks.min(axis=0)) <= 1
    rows = np.arange(height)
    best = costs.argmin(axis=0)
    middle = np.clip(best, 1, 2 * reach - 1)
    left, centre, right = costs[middle - 1, rows], costs[middle, rows], costs[middle + 1, rows]
    bend = left - 2 * centre + right
    fraction = np.where(bend > 1e-6, 0.5 * (left - right) / np.maximum(bend, 1e-6), 0.0)
    shift = middle - reach + np.clip(fraction, -0.5, 0.5)
    shift = np.where(best == middle, shift, best - reach).astype(np.float32)
    still = costs[reach]
    gain = still - costs[best, rows]
    texture = np.abs(theirs).mean(axis=1)
    weight = np.clip(gain / (0.05 * still + 1e-3) - 0.5, 0, 1) * (texture > 4.0) * agree
    return shift, weight.astype(np.float32)


def _bridge_rows(motion: np.ndarray, trusted: np.ndarray) -> np.ndarray:
    """Flow with the untrusted rows replaced by a weighted blend of the trusted rows around them."""
    if trusted.all():
        return motion
    weight = np.ascontiguousarray(np.broadcast_to(trusted[:, None], motion.shape[:2]), np.float32)
    sigma = max(2.0, motion.shape[0] / 20)
    total = cv2.GaussianBlur(weight, (0, 0), sigma, borderType=cv2.BORDER_REPLICATE)
    carried = np.dstack([cv2.GaussianBlur(motion[:, :, axis] * weight, (0, 0), sigma, borderType=cv2.BORDER_REPLICATE)
                         for axis in range(2)]) / np.maximum(total, 1e-3)[:, :, None]
    return np.where(weight[:, :, None] > 0, motion, carried).astype(np.float32)


def _jitter(luma: np.ndarray, reference: np.ndarray, strength: float) -> np.ndarray | None:
    """Per-row shift that removes line jitter, or None when there is none worth correcting."""
    width = luma.shape[1]
    reach = max(3, round(width / 120))
    shift, weight = _row_shifts(luma, reference, reach)
    if weight.mean() < 0.15:
        return None
    # A shift common to all rows is picture motion the alignment left over.
    order = np.argsort(shift)
    cumulative = np.cumsum(weight[order])
    shift = shift - shift[order][np.searchsorted(cumulative, cumulative[-1] / 2)]
    fine, cover = _normalised_blur(shift, weight, 1.0)
    slow, _ = _normalised_blur(shift, weight, JITTER_SLOW)
    wobble = (fine - slow) * np.clip(cover / 0.3, 0, 1)
    spread = math.sqrt(float((weight * wobble ** 2).sum() / max(weight.sum(), 1e-6)))
    # A time-base error runs through the picture; a kink in a few rows is a
    # local mismatch of the alignment.
    widespread = float((weight * (np.abs(wobble) > 0.5)).sum() / max(weight.sum(), 1e-6))
    if spread < JITTER_MIN or widespread < JITTER_SHARE:
        return None
    return (wobble * min(1.0, 1.5 * strength)).astype(np.float32)


def _tape_window(flow: _Flow, window: list[_TapeFrame], center: int, strength: float) -> tuple[np.ndarray, int]:
    """The frame with tracking noise and line jitter repaired, and the height of a broken bottom band."""
    present = window[center]
    before, after = _pick(window, center, 2)
    picks = before + after
    if not picks:
        return present.frame, 0
    motions = [cv2.GaussianBlur(flow.calc(present.small, window[index].small), (0, 0), 1.5) for index in picks]
    reference = _median([flow.warp(window[index].luma, motion) for index, motion in zip(picks, motions)])
    height = present.luma.shape[0]
    # Distance outside what the reference shows within a pixel either way: a
    # sharp edge off by a fraction of a line is not noise, random dots are.
    near = np.ones((3, 3), np.uint8)
    error = (np.maximum(present.luma - cv2.dilate(reference, near), 0)
             + np.maximum(cv2.erode(reference, near) - present.luma, 0)).mean(axis=1)
    typical = float(np.median(error))
    own_detail = np.abs(np.diff(present.luma, axis=1)).mean(axis=1)
    their_detail = np.abs(np.diff(reference, axis=1)).mean(axis=1)
    noisy = (error > (4.5 - 2.5 * strength) * typical + 4) & (own_detail > 1.3 * their_detail + 1)
    noisy = _runs(noisy, 3, 2)
    if noisy.mean() > 0.5:
        noisy[:] = False  # Most of the frame differs: a flash or a cut, not tape noise.
    # A band reaching the bottom edge is the head switch; it is broken in the
    # neighbours too, so it is masked later instead of refilled.
    band = 0
    zone = max(2, round(SWITCH_ZONE * height))
    while band < zone and noisy[height - 1 - band]:
        band += 1
    if band:
        noisy[height - band:] = False
    result = present.frame
    luma = present.luma
    if noisy.any():
        rows = cv2.dilate(noisy.astype(np.uint8)[:, None], np.ones((5, 1), np.uint8)).astype(np.float32)
        rows = np.maximum(cv2.GaussianBlur(rows, (1, 0), sigmaX=0.1, sigmaY=1.5), rows)
        # The motion measured inside the noise is meaningless: carry it in
        # from the rows above and below.
        small_rows = cv2.resize(rows, (1, motions[0].shape[0]), interpolation=cv2.INTER_LINEAR)[:, 0]
        trusted = (small_rows < 0.05).astype(np.float32)
        fill = _median([flow.warp(window[index].frame, _bridge_rows(motion, trusted))
                        for index, motion in zip(picks, motions)])
        weight = np.ascontiguousarray(np.broadcast_to(rows, present.luma.shape))
        result = cv2.blendLinear(fill, result, weight, 1 - weight)
        luma = luma * (1 - weight) + reference * weight
    # Line wobble is measured against neighbours aligned only with the broad
    # motion; fine motion would follow the wobble itself.
    broad = max(2.0, motions[0].shape[0] / 12)
    steady = _median([flow.warp(window[index].luma, cv2.GaussianBlur(motion, (0, 0), broad))
                      for index, motion in zip(picks, motions)])
    shift = _jitter(luma, steady, strength)
    if shift is not None:
        width = luma.shape[1]
        grid_x = np.tile(np.arange(width, dtype=np.float32), (height, 1))
        grid_y = np.repeat(np.arange(height, dtype=np.float32)[:, None], width, axis=1)
        result = cv2.remap(result, grid_x + shift[:, None], grid_y, cv2.INTER_LINEAR,
                           borderMode=cv2.BORDER_REPLICATE)
    return result, band


def tape_stream(frames: Iterable[np.ndarray], amount: int, fps: float = 25.0) -> Iterator[np.ndarray]:
    """Tracking noise refilled, line jitter removed and the head-switch band masked.

    The band is masked only while it shows in most of the last second of
    frames, at the height it usually has, so the mask does not flicker.
    """
    if amount <= 0:
        yield from frames
        return
    flows = PerThread(lambda: _Flow(cv2.DISOPTICAL_FLOW_PRESET_FAST))
    recent: deque[int] = deque(maxlen=max(5, round(fps)))
    for frame, band in window_map(frames, TAPE_RADIUS, _TapeFrame,
                                  lambda window, center: _tape_window(flows.get(), window, center, amount / 100)):
        recent.append(band)
        height = int(np.percentile(recent, 60))
        if height:
            frame = frame.copy()
            frame[-height:] = 0
        yield frame


# ------------------------------------------------------------------ flicker


class _LightFrame:
    def __init__(self, frame: np.ndarray) -> None:
        self.frame = frame
        gray = _gray(frame)
        self.small = _shrink(gray, FLICKER_WIDTH)
        self.tiny = _tiny(gray)


def _planes(width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
    return np.meshgrid(np.linspace(-1, 1, width, dtype=np.float32), np.linspace(-1, 1, height, dtype=np.float32))


def light_fit(present: np.ndarray, reference: np.ndarray, usable: np.ndarray) -> np.ndarray | None:
    """Gain and offset planes that turn ``present`` into ``reference``.

    Six numbers: gain = g0 + gx x + gy y and offset = o0 + ox x + oy y, with
    x and y from -1 to 1 across the picture. Fitted by least squares, twice,
    the second time without the pixels the first fit explained worst.
    """
    height, width = present.shape
    across, down = _planes(width, height)
    values = present[usable]
    design = np.stack([values, values * across[usable], values * down[usable],
                       np.ones_like(values), across[usable], down[usable]], axis=1).astype(np.float64)
    target = reference[usable].astype(np.float64)
    keep = np.ones(len(target), bool)
    params = None
    for _ in range(2):
        if keep.sum() < 64:
            return None
        params, *_ = np.linalg.lstsq(design[keep], target[keep], rcond=None)
        residual = np.abs(design @ params - target)
        keep = residual <= max(2.0, 2.5 * float(np.median(residual)))
    return params


def _flicker_window(flow: _Flow, window: list[_LightFrame], center: int, strength: float) -> np.ndarray:
    present = window[center]
    before, after = _pick(window, center, 3)
    if len(before) + len(after) < 2:
        return present.frame
    small = present.small.astype(np.float32)
    layers = [small]
    for index in before + after:
        other = window[index]
        layers.append(flow.warp(other.small.astype(np.float32), flow.calc(present.small, other.small)))
    reference = np.median(np.stack(layers), axis=0)
    spread = np.median(np.abs(np.stack(layers[1:]) - reference), axis=0)
    usable = (small > 6) & (small < 249) & (spread < 12)
    if usable.mean() < 0.3:
        return present.frame
    params = light_fit(small, reference, usable)
    if params is None:
        return present.frame
    gain, gain_x, gain_y, offset, offset_x, offset_y = (float(value) for value in params)
    if not 0.5 < gain < 2.0 or max(abs(gain_x), abs(gain_y)) > 0.3 or abs(offset) > 60:
        return present.frame
    height, width = present.frame.shape[:2]
    across, down = _planes(width, height)
    gain_plane = 1 + strength * (gain - 1 + gain_x * across + gain_y * down)
    offset_plane = strength * (offset + offset_x * across + offset_y * down)
    change = (gain_plane - 1) * 128 + offset_plane
    if float(np.abs(change).max()) < 0.75:
        return present.frame
    picture = present.frame.astype(np.float32) * gain_plane[:, :, None] + offset_plane[:, :, None]
    return np.clip(picture + 0.5, 0, 255).astype(np.uint8)


def flicker_stream(frames: Iterable[np.ndarray], amount: int) -> Iterator[np.ndarray]:
    """Frame-to-frame brightness flicker evened out against the neighbours of the same shot."""
    if amount <= 0:
        yield from frames
        return
    flows = PerThread(lambda: _Flow(cv2.DISOPTICAL_FLOW_PRESET_FAST))
    yield from window_map(frames, FLICKER_RADIUS, _LightFrame,
                          lambda window, center: _flicker_window(flows.get(), window, center, amount / 100))


# ------------------------------------------------------ dust and scratches


def column_ridges(luma: np.ndarray) -> np.ndarray:
    """Per column, how much a thin line stands out from both sides over most rows.

    Positive for a bright line, negative for a dark one, zero where fewer than
    three quarters of the rows agree.
    """
    height, width = luma.shape
    reach = max(2, width // 320)
    rows = luma[::4]
    sides = np.empty_like(rows)
    sides[:, reach:-reach] = 0.5 * (rows[:, :-2 * reach] + rows[:, 2 * reach:])
    sides[:, :reach] = rows[:, :reach]
    sides[:, -reach:] = rows[:, -reach:]
    ridge = rows - sides
    low = np.percentile(ridge, 100 * (1 - SCRATCH_ROWS), axis=0)
    high = np.percentile(ridge, 100 * SCRATCH_ROWS, axis=0)
    profile = np.where(low > 0, low, np.where(high < 0, high, 0)).astype(np.float32)
    margin = max(reach + 1, width // 50)
    profile[:margin] = 0
    profile[-margin:] = 0
    return profile


class _DustFrame:
    def __init__(self, frame: np.ndarray, scratches: bool = True) -> None:
        self.frame = frame
        gray = _gray(frame)
        self.luma = gray.astype(np.float32)
        self.small = _shrink(gray, DUST_FLOW_WIDTH)
        self.tiny = _tiny(gray)
        self.ridge = column_ridges(self.luma) if scratches else None


def specks(present: np.ndarray, before: np.ndarray, after: np.ndarray, strength: float) -> np.ndarray:
    """Boolean mask of dust, dirt and dropouts: in ``present`` only, not in the aligned neighbours.

    A pixel counts when it is brighter (or darker) than everything near it
    in both neighbours by a margin set by the noise and the texture, while
    the two neighbours agree. Looking at everything near it, not only at the
    same place, keeps small moving lights that the alignment missed.
    """
    height, width = present.shape
    middle = (before + after) * 0.5
    # A brightness change over an area (uneven flicker, a misframed frame) is
    # not dirt: compare after taking out the smooth part of the difference.
    present = present - cv2.GaussianBlur(present - middle, (0, 0), max(4.0, width / 40))
    rise = present - middle
    sample = rise[::4, ::4]
    noise = 1.4826 * float(np.median(np.abs(sample - np.median(sample))))
    texture = cv2.blur(cv2.magnitude(cv2.Sobel(middle, cv2.CV_32F, 1, 0), cv2.Sobel(middle, cv2.CV_32F, 0, 1)), (5, 5))
    level = max(8.0, (5.0 - 2.5 * strength) * noise) + 0.25 * texture
    reach = max(3, width // 60)
    near = np.ones((2 * reach + 1, 2 * reach + 1), np.uint8)
    brightest = cv2.dilate(np.maximum(before, after), near)
    darkest = cv2.erode(np.minimum(before, after), near)
    agree = cv2.absdiff(before, after) < level
    spots = ((present - brightest > level) | (darkest - present > level)) & agree
    spots = spots.astype(np.uint8)
    if not spots.any():
        return spots.astype(bool)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(spots, connectivity=8)
    keep = stats[:, cv2.CC_STAT_AREA] <= SPECK_AREA * height * width
    keep[0] = False
    spots = keep[labels].astype(np.uint8)
    # Dust is sparse; a dense crowd of "specks" is grain or texture that the
    # alignment did not match.
    crowd = max(31, width // 8) | 1
    spots &= (cv2.blur(spots.astype(np.float32), (crowd, crowd)) < SPECK_CROWD).astype(np.uint8)
    if spots.mean() > SPECKS_AT_MOST:
        return np.zeros(spots.shape, bool)  # Alignment failed across the frame.
    grow = max(1, width // 480)
    spots = cv2.dilate(spots, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 3, 2 * grow + 3)))
    return spots > 0


def scratch_columns(profiles: list[np.ndarray], center: int, strength: float) -> list[tuple[int, int]]:
    """Column spans (first, last) of scratches: thin lines in most frames of the window."""
    present = profiles[center]
    stack = np.abs(np.stack(profiles))
    noise = 1.4826 * float(np.median(np.abs(present))) + 1e-3
    level = max(3.0, (8.0 - 4.0 * strength) * noise)
    marked = (stack > level).astype(np.uint8)
    # Scratches wander a little with the film; allow two columns either way.
    near = cv2.dilate(marked, np.ones((1, 5), np.uint8))
    lasting = near.mean(axis=0) >= SCRATCH_FRAMES
    current = (np.abs(present) > level) & lasting
    columns = np.flatnonzero(current)
    spans: list[tuple[int, int]] = []
    widest = max(6, len(present) // 100)
    for column in columns:
        if spans and column - spans[-1][1] <= 1:
            spans[-1] = (spans[-1][0], int(column))
        else:
            spans.append((int(column), int(column)))
    return [span for span in spans if span[1] - span[0] < widest]


def fill_scratches(frame: np.ndarray, luma: np.ndarray, spans: list[tuple[int, int]]) -> np.ndarray:
    """Fill scratch columns across from both sides, in the rows where the line shows."""
    height, width = luma.shape
    reach = max(2, width // 320)
    result = frame.astype(np.float32)
    for first, last in spans:
        left, right = max(0, first - reach), min(width - 1, last + reach)
        if right - left < 2:
            continue
        inside = luma[:, first:last + 1].mean(axis=1)
        sides = 0.5 * (luma[:, left] + luma[:, right])
        strength = np.abs(inside - sides)
        rows = cv2.GaussianBlur(strength[:, None], (1, 0), sigmaX=0.1, sigmaY=4)[:, 0]
        shown = np.clip((rows - 2.0) / 4.0, 0, 1)[:, None, None]
        share = ((np.arange(left + 1, right, dtype=np.float32) - left) / (right - left))[None, :, None]
        across = result[:, left:left + 1] * (1 - share) + result[:, right:right + 1] * share
        result[:, left + 1:right] = result[:, left + 1:right] * (1 - shown) + across * shown
    return np.clip(result + 0.5, 0, 255).astype(np.uint8)


def _dust_window(flow: _Flow, window: list[_DustFrame], center: int, strength: float) -> np.ndarray:
    present = window[center]
    result = present.frame
    before, after = _pick(window, center, 1)
    if before and after:
        previous, following = window[before[0]], window[after[0]]
        to_previous = flow.calc(present.small, previous.small)
        to_following = flow.calc(present.small, following.small)
        mask = specks(present.luma, flow.warp(previous.luma, to_previous),
                      flow.warp(following.luma, to_following), strength)
        if mask.any():
            fill = cv2.addWeighted(flow.warp(previous.frame, to_previous), 0.5,
                                   flow.warp(following.frame, to_following), 0.5, 0)
            alpha = mask.astype(np.float32)
            alpha = np.maximum(cv2.GaussianBlur(alpha, (0, 0), 1.0), alpha)
            result = cv2.blendLinear(fill, result, alpha, 1 - alpha)
    if present.ridge is not None:
        spans = scratch_columns([item.ridge for item in window], center, strength)
        if spans:
            # While the picture moves sideways, a line that moves with it is
            # part of the picture; a scratch stays on the film frame. The
            # farthest frame of the shot shows the most movement.
            far_before, far_after = _pick(window, center, len(window))
            far = max(far_before[-1:] + far_after[-1:], key=lambda index: abs(index - center), default=None)
            if far is not None:
                to_far = flow.calc(present.small, window[far].small)
                sideways = float(np.median(to_far[:, :, 0])) * present.luma.shape[1] / to_far.shape[1]
                if abs(sideways) >= 1.5:
                    carried = column_ridges(flow.warp(window[far].luma, to_far))
                    spans = [(first, last) for first, last in spans
                             if np.abs(carried[max(0, first - 1):last + 2]).max()
                             < 0.5 * np.abs(present.ridge[first:last + 1]).max()]
        if spans:
            result = fill_scratches(result, present.luma, spans)
    return result


def dust_stream(frames: Iterable[np.ndarray], amount: int) -> Iterator[np.ndarray]:
    """Dust, dirt, tape dropouts and vertical scratches removed."""
    if amount <= 0:
        yield from frames
        return
    flows = PerThread(_Flow)
    yield from window_map(frames, DUST_RADIUS, _DustFrame,
                          lambda window, center: _dust_window(flows.get(), window, center, amount / 100))


# -------------------------------------------------------------- stabilising


def picture_area(gray: np.ndarray) -> np.ndarray:
    """255 inside the picture, 0 on the dark surround that touches the frame border.

    A scan shows the film's own edge and the gate, a tape transfer black
    bars; they hold still while the picture weaves, so they must not move
    with it. Dark parts of the picture that reach the border count as
    surround too, which does no harm: dark stays dark.
    """
    dark = (cv2.blur(gray, (5, 5)) < SURROUND_LEVEL).astype(np.uint8)
    count, labels = cv2.connectedComponents(dark, connectivity=4)
    if count <= 1:
        return np.full(gray.shape, 255, np.uint8)
    rim = np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])
    touching = np.zeros(count, bool)
    touching[rim] = True
    touching[0] = False
    return np.where(touching[labels], 0, 255).astype(np.uint8)


class _Steady:
    def __init__(self, frame: np.ndarray) -> None:
        self.frame = frame
        gray = _gray(frame)
        self.small = _shrink(gray, STABLE_WIDTH)
        self.tiny = _tiny(gray)
        self.scale = frame.shape[1] / self.small.shape[1]
        self.picture = picture_area(gray)


def frame_motion(previous: _Steady, current: _Steady) -> np.ndarray | None:
    """Similarity (3 x 3) from ``current`` pixel positions to ``previous`` ones.

    None at a cut or where too few corners can be followed; RANSAC keeps the
    motion of the majority, so a burned-in stamp or the gate edge does not
    hold it at zero.
    """
    if not same_shot(previous.tiny, current.tiny):
        return None
    corners = cv2.goodFeaturesToTrack(current.small, 400, 0.01, 6, blockSize=7)
    if corners is None or len(corners) < 24:
        return None
    moved, status, _ = cv2.calcOpticalFlowPyrLK(current.small, previous.small, corners, None,
                                                winSize=(21, 21), maxLevel=3)
    found = status[:, 0] == 1
    if found.sum() < 24:
        return None
    matrix, inliers = cv2.estimateAffinePartial2D(corners[found], moved[found], method=cv2.RANSAC,
                                                  ransacReprojThreshold=1.0)
    if matrix is None or inliers.sum() < max(16, 0.35 * found.sum()):
        return None
    matrix[:, 2] *= current.scale
    return np.vstack([matrix, [0.0, 0.0, 1.0]])


def _parameters(matrix: np.ndarray) -> np.ndarray:
    return np.array([matrix[0, 2], matrix[1, 2], math.atan2(matrix[1, 0], matrix[0, 0]),
                     math.log(max(1e-6, math.hypot(matrix[0, 0], matrix[1, 0])))])


def _similarity(params: np.ndarray) -> np.ndarray:
    move_x, move_y, angle, size = params
    scale = math.exp(size)
    return np.array([[scale * math.cos(angle), -scale * math.sin(angle), move_x],
                     [scale * math.sin(angle), scale * math.cos(angle), move_y], [0.0, 0.0, 1.0]])


def smooth_path(times: np.ndarray, params: np.ndarray, sigma: float) -> np.ndarray:
    """Value at time 0 of a Gaussian-weighted straight-line fit to ``params`` (one row per time).

    A straight-line fit keeps a steady pan steady even at the start and end
    of a shot, where a plain average would lag.
    """
    weight = np.exp(-0.5 * (times / sigma) ** 2)
    total, first, second = weight.sum(), (weight * times).sum(), (weight * times * times).sum()
    level = (weight[:, None] * params).sum(axis=0)
    slope = (weight[:, None] * times[:, None] * params).sum(axis=0)
    determinant = total * second - first * first
    if determinant < 1e-9:
        return level / total
    return (second * level - first * slope) / determinant


def _settle(item: _Steady, matrix: np.ndarray, neighbours: list[tuple[_Steady, np.ndarray]]) -> np.ndarray:
    """The picture of ``item`` warped by ``matrix`` (output to source positions).

    The surround outside the picture stays where it is. Where the moved
    picture leaves a gap, neighbouring frames fill it, and what is still
    open keeps the frame's own pixels.
    """
    frame = item.frame
    height, width = frame.shape[:2]
    corners = np.array([[0, 0, 1], [width, 0, 1], [0, height, 1], [width, height, 1]], np.float64).T
    if np.abs(matrix @ corners - corners).max() < STABLE_DEAD:
        return frame  # Too small to see; resampling would only soften the picture.
    flags = cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP
    edge = np.ones((3, 3), np.uint8)

    def covered(source: _Steady, transform: np.ndarray) -> np.ndarray:
        # One pixel less than the warp covers, so no surround seeps in at the rim.
        return cv2.erode(cv2.warpAffine(source.picture, transform[:2], (width, height),
                                        flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP, borderValue=0), edge) > 0

    result = cv2.warpAffine(frame, matrix[:2], (width, height), flags=flags, borderMode=cv2.BORDER_REPLICATE)
    inside = item.picture > 0
    hole = inside & ~covered(item, matrix)
    for other, transform in neighbours:
        if not hole.any():
            break
        reached = covered(other, transform) & hole
        if reached.any():
            patch = cv2.warpAffine(other.frame, transform[:2], (width, height), flags=flags,
                                   borderMode=cv2.BORDER_REPLICATE)
            result[reached] = patch[reached]
            hole &= ~reached
    keep = hole | ~inside
    result[keep] = frame[keep]
    return result


def stabilise_stream(frames: Iterable[np.ndarray], amount: int, fps: float = 25.0) -> Iterator[np.ndarray]:
    """Gate weave and camera shake removed; pans, zooms and slow moves are kept.

    The motion between consecutive frames is chained into a path per shot.
    Each frame is moved to the smoothed path, at most by STABLE_LIMIT of the
    width; ``amount`` sets how long a wobble may last and still be removed
    (up to half a second).
    """
    if amount <= 0:
        yield from frames
        return
    sigma = max(1.0, (0.08 + 0.42 * amount / 100) * fps / 2.5)
    radius = min(STABLE_REACH, max(2, math.ceil(2.5 * sigma)))
    prepared = ordered_map(_Steady, frames)

    def pairs() -> Iterator[tuple[_Steady | None, _Steady]]:
        previous = None
        for item in prepared:
            yield previous, item
            previous = item

    def measured(pair: tuple[_Steady | None, _Steady]) -> tuple:
        previous, item = pair
        if previous is None:
            return item, None, 0.0
        return item, frame_motion(previous, item), float(cv2.absdiff(previous.small, item.small).mean())

    motions = ordered_map(measured, pairs())

    def job(window: deque, center: int) -> tuple:
        item, path, shot, _ = window[center]
        members = [(index, entry) for index, entry in enumerate(window) if entry[2] == shot]
        # Time counts in distinct pictures: copies of a film frame belong to
        # the same moment, or the judder of a frame-rate conversion would be
        # taken for shake.
        gaps = [entry[3] for _, entry in members]
        floor = max(DUP_FLOOR, DUP_SHARE * max(gaps[1:], default=0.0))
        moments = np.cumsum([position > 0 and gap > floor for position, gap in enumerate(gaps)])
        here = moments[[index for index, _ in members].index(center)]
        times = (moments - here).astype(np.float64)
        pace = max(0.25, (moments[-1] + 1) / len(members))
        params = np.array([_parameters(entry[1]) for _, entry in members])
        smooth = _similarity(smooth_path(times, params, sigma * pace))
        members = [(index - center, entry) for index, entry in members]
        correction = np.linalg.inv(path) @ smooth
        height, width = item.frame.shape[:2]
        corners = np.array([[0, 0, 1], [width, 0, 1], [0, height, 1], [width, height, 1]], np.float64).T
        reach = float(np.abs(correction @ corners - corners).max())
        limit = STABLE_LIMIT * width
        if reach > limit:
            correction = np.eye(3) + (correction - np.eye(3)) * (limit / reach)
            smooth = path @ correction
        neighbours = [(entry[0], np.linalg.inv(entry[1]) @ smooth)
                      for offset, entry in sorted(members, key=lambda pair: abs(pair[0]))
                      if offset and abs(offset) <= 2]
        return item, correction, neighbours

    def jobs() -> Iterator[tuple]:
        window: deque = deque()
        first = emitted = 0
        path, shot = np.eye(3), 0
        for count, (item, motion, gap) in enumerate(motions, start=1):
            if motion is None:
                path, shot = np.eye(3), shot + 1
            else:
                path = path @ motion
            window.append((item, path.copy(), shot, gap))
            while emitted + radius < count:
                yield job(window, emitted - first)
                emitted += 1
                while emitted - first > radius:
                    window.popleft()
                    first += 1
        while emitted < first + len(window):
            yield job(window, emitted - first)
            emitted += 1
            while emitted - first > radius and len(window) > 1:
                window.popleft()
                first += 1

    yield from ordered_map(lambda arguments: _settle(*arguments), jobs())


# ------------------------------------------------------------------- colour


def coloured(frame: np.ndarray) -> bool:
    """Whether a frame carries colour at all; a tint over black and white does not count."""
    small = cv2.resize(frame, (160, 120), interpolation=cv2.INTER_AREA)
    chroma = cv2.cvtColor(small, cv2.COLOR_BGR2YCrCb)[:, :, 1:].reshape(-1, 2).astype(np.float32)
    spread = np.abs(chroma - np.median(chroma, axis=0)).sum(axis=1)
    return float(np.percentile(spread, 90)) > 6.0


def sharpen_chroma(frame: np.ndarray, strength: float) -> np.ndarray:
    """Colour pulled onto the brightness edges, against the colour bleed of tape.

    Tape records colour with about a tenth of the brightness detail, so it
    smears sideways past every edge. Near a brightness edge, each pixel
    takes its colour from samples one smear width to its left and right,
    weighted by how well their brightness matches its own: those
    samples lie beyond the smear, on the same side of the edge. Away from
    brightness edges the colour is left alone.
    """
    if strength <= 0:
        return frame
    ycc = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb).astype(np.float32)
    height, width = frame.shape[:2]
    reach = max(4, width // 64)
    luma = ycc[:, :, 0]
    padded = cv2.copyMakeBorder(ycc, 0, 0, reach, reach, cv2.BORDER_REPLICATE)
    # The pixel itself counts a little, so a thing narrower than the reach,
    # whose samples both fall outside it, keeps its own colour.
    total = np.full((height, width), BLEED_SELF, np.float32)
    colour = ycc[:, :, 1:] * BLEED_SELF
    contrast = np.zeros((height, width), np.float32)
    for step in (-reach, reach):
        sample = padded[:, reach + step:reach + step + width]
        gap = np.abs(sample[:, :, 0] - luma)
        weight = np.exp(-np.square(gap / BLEED_MATCH)) + 1e-3
        total += weight
        colour += sample[:, :, 1:] * weight[:, :, None]
        contrast = np.maximum(contrast, gap)
    edge = np.clip((contrast - 8.0) / 16.0, 0, 1) * min(1.0, 1.2 * strength)
    ycc[:, :, 1:] += (colour / total[:, :, None] - ycc[:, :, 1:]) * edge[:, :, None]
    return cv2.cvtColor(np.clip(ycc + 0.5, 0, 255).astype(np.uint8), cv2.COLOR_YCrCb2BGR)


def colour_stream(frames: Iterable[np.ndarray], amount: int, radius: int = 3,
                  flow_width: int = 320) -> Iterator[np.ndarray]:
    """Chroma re-estimated from the neighbours and sharpened; black-and-white footage passes."""
    if amount <= 0:
        yield from frames
        return
    source = iter(frames)
    head = list(islice(source, COLOUR_PROBE))
    stream = chain(head, source)
    if not any(coloured(frame) for frame in head):
        yield from stream
        return
    yield from ordered_map(lambda frame: sharpen_chroma(frame, amount / 100),
                           repair_stream(stream, amount, None, radius, flow_width))
