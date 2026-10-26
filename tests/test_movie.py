"""Tape and film stages: each repair on synthetic faults, recipe fields and a real export."""

from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import cv2
import numpy as np

from analogrepair import movie
from analogrepair.bridge import run
from analogrepair.media import inspect_video, tools_available
from analogrepair.osd import find_osd, remove_stream
from analogrepair.recipe import FILM_WERTE, Arbeitsrezept


def canvas(seed: int = 3, height: int = 360, width: int = 480) -> np.ndarray:
    """A large textured BGR picture: soft blobs, edges and fine detail."""
    random = np.random.default_rng(seed)
    base = cv2.GaussianBlur(random.uniform(0, 255, (height, width)).astype(np.float32), (0, 0), 6)
    base = cv2.normalize(base, None, 40, 200, cv2.NORM_MINMAX)
    detail = cv2.GaussianBlur(random.uniform(-30, 30, (height, width)).astype(np.float32), (0, 0), 1.2)
    picture = base + detail
    for _ in range(25):
        x, y = random.integers(0, width - 40), random.integers(0, height - 40)
        cv2.rectangle(picture, (int(x), int(y)), (int(x + random.integers(10, 40)), int(y + random.integers(10, 40))),
                      float(random.uniform(30, 220)), -1)
    picture = np.clip(picture, 0, 255).astype(np.uint8)
    return cv2.merge([picture, cv2.add(picture, 10), cv2.subtract(picture, 15)])


def pan(count: int, size: tuple[int, int] = (240, 180), step: float = 1.5, seed: int = 3,
        noise: float = 2.0) -> list[np.ndarray]:
    """``count`` frames of a slow pan over ``canvas`` with a little sensor noise."""
    big = canvas(seed)
    random = np.random.default_rng(seed + 1)
    frames = []
    for index in range(count):
        matrix = np.float32([[1, 0, -20 - step * index], [0, 1, -30 - 0.4 * step * index]])
        frame = cv2.warpAffine(big, matrix, size, flags=cv2.INTER_LINEAR).astype(np.float32)
        frame += random.normal(0, noise, frame.shape)
        frames.append(np.clip(frame, 0, 255).astype(np.uint8))
    return frames


def luma(frame: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)


def psnr(first: np.ndarray, second: np.ndarray) -> float:
    error = np.mean((first.astype(np.float64) - second.astype(np.float64)) ** 2)
    return 99.0 if error == 0 else 10 * np.log10(255 ** 2 / error)


class DustTests(unittest.TestCase):
    def test_specks_and_dropouts_are_refilled(self):
        clean = pan(7)
        dirty = [frame.copy() for frame in clean]
        spots = [(60, 50, 255), (150, 120, 0), (200, 40, 255)]
        for x, y, value in spots:
            cv2.circle(dirty[3], (x, y), 3, (value, value, value), -1)
        # A tape dropout: a short white streak in one frame.
        dirty[3][100, 30:70] = 250
        repaired = list(movie.dust_stream(dirty, 60))[3]
        for x, y, _ in spots:
            area = (slice(y - 4, y + 5), slice(x - 4, x + 5))
            self.assertLess(np.abs(luma(repaired)[area] - luma(clean[3])[area]).mean(),
                            0.25 * np.abs(luma(dirty[3])[area] - luma(clean[3])[area]).mean())
        self.assertLess(np.abs(luma(repaired)[100, 30:70] - luma(clean[3])[100, 30:70]).mean(), 20)
        # Away from the dirt the frame is left as it was.
        rest = np.ones(clean[3].shape[:2], bool)
        rest[30:140, 20:220] = False
        self.assertLess(np.abs(luma(repaired) - luma(dirty[3]))[rest].mean(), 0.5)

    def test_copied_frames_do_not_hide_dust(self):
        # Film transferred at twice its rate: every picture twice, dust included.
        pictures = pan(5, step=3.0)
        dirty = [picture.copy() for picture in pictures]
        cv2.circle(dirty[2], (120, 90), 3, (255, 255, 255), -1)
        doubled = [frame for picture in dirty for frame in (picture, picture.copy())]
        repaired = list(movie.dust_stream(doubled, 60))
        for index in (4, 5):
            self.assertLess(abs(float(luma(repaired[index])[90, 120]) - float(luma(pictures[2])[90, 120])), 30)

    def test_small_moving_light_is_kept(self):
        # A bright dot that moves faster than the background is picture, not dust.
        frames = pan(7)
        for index, frame in enumerate(frames):
            cv2.circle(frame, (40 + 2 * index, 140), 2, (255, 255, 255), -1)
        repaired = list(movie.dust_stream(frames, 60))[3]
        self.assertGreater(float(luma(repaired)[140, 46]), 200)

    def test_vertical_scratch_is_filled(self):
        clean = pan(9)
        scratched = [frame.copy() for frame in clean]
        for frame in scratched:
            frame[:, 100:102] = np.clip(frame[:, 100:102].astype(int) - 60, 0, 255).astype(np.uint8)
        repaired = list(movie.dust_stream(scratched, 60))[4]
        before = np.abs(luma(scratched[4])[:, 100:102] - luma(clean[4])[:, 100:102]).mean()
        after = np.abs(luma(repaired)[:, 100:102] - luma(clean[4])[:, 100:102]).mean()
        self.assertLess(after, 0.35 * before)

    def test_ridges_need_most_rows(self):
        frame = np.full((120, 400), 120, np.float32)
        frame[:, 200] = 60          # a full-height line
        frame[:40, 300] = 60        # a short pole
        profile = movie.column_ridges(frame)
        self.assertLess(profile[200], -20)
        self.assertEqual(profile[300], 0)


class FlickerTests(unittest.TestCase):
    def test_flicker_is_evened_out(self):
        clean = pan(15)
        gains = [1.0, 1.18, 0.86, 1.1, 0.92, 1.15, 0.9, 1.0, 1.2, 0.85, 1.05, 0.9, 1.12, 0.95, 1.0]
        flickering = [np.clip(frame.astype(np.float32) * gain, 0, 255).astype(np.uint8)
                      for frame, gain in zip(clean, gains)]
        steady = list(movie.flicker_stream(flickering, 100))
        jump = lambda frames: float(np.abs(np.diff([luma(frame).mean() for frame in frames])).mean())
        self.assertLess(jump(steady[3:-3]), 0.35 * jump(flickering[3:-3]))

    def test_slow_exposure_change_is_kept(self):
        clean = pan(15)
        ramp = [np.clip(frame.astype(np.float32) * (0.8 + 0.03 * index), 0, 255).astype(np.uint8)
                for index, frame in enumerate(clean)]
        steady = list(movie.flicker_stream(ramp, 100))
        for index in range(4, 11):
            self.assertLess(abs(luma(steady[index]).mean() - luma(ramp[index]).mean()), 1.5)

    def test_light_fit_finds_gain_and_offset(self):
        present = np.random.default_rng(5).uniform(20, 200, (60, 80)).astype(np.float32)
        params = movie.light_fit(present, present * 1.2 + 7, np.ones(present.shape, bool))
        self.assertAlmostEqual(params[0], 1.2, places=3)
        self.assertAlmostEqual(params[3], 7.0, places=2)


class TapeTests(unittest.TestCase):
    def test_tracking_band_is_refilled(self):
        clean = pan(5)
        broken = [frame.copy() for frame in clean]
        noise = np.random.default_rng(9).integers(0, 256, (14, 240, 3), dtype=np.uint8)
        broken[2][80:94] = noise
        repaired = list(movie.tape_stream(broken, 60))[2]
        before = np.abs(luma(broken[2])[80:94] - luma(clean[2])[80:94]).mean()
        after = np.abs(luma(repaired)[80:94] - luma(clean[2])[80:94]).mean()
        self.assertLess(after, 0.2 * before)
        self.assertLess(np.abs(luma(repaired)[:70] - luma(clean[2])[:70]).mean(), 1.0)

    def test_head_switching_band_is_masked(self):
        frames = pan(20)
        random = np.random.default_rng(4)
        for frame in frames:
            # The bottom eight rows torn sideways and noisy, a little differently every frame.
            frame[-8:] = np.roll(frame[-8:], int(random.integers(8, 20)), axis=1)
            frame[-8:] = np.clip(frame[-8:].astype(int) + random.integers(-60, 60, frame[-8:].shape), 0, 255)
        repaired = list(movie.tape_stream(frames, 60, fps=25))
        for frame in repaired[8:]:
            self.assertLess(float(frame[-6:].mean()), 1.0)
            self.assertGreater(float(frame[:-10].mean()), 30)

    def test_line_jitter_is_straightened(self):
        clean = pan(5)
        shifted = [frame.copy() for frame in clean]
        random = np.random.default_rng(2)
        wobble = np.repeat(random.integers(-3, 4, 180 // 6), 6).astype(np.float32)
        grid_x = np.tile(np.arange(240, dtype=np.float32), (180, 1)) + wobble[:, None]
        grid_y = np.repeat(np.arange(180, dtype=np.float32)[:, None], 240, axis=1)
        shifted[2] = cv2.remap(clean[2], grid_x, grid_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        repaired = list(movie.tape_stream(shifted, 80))[2]
        inner = (slice(10, -10), slice(10, -10))
        before = np.abs(luma(shifted[2])[inner] - luma(clean[2])[inner]).mean()
        after = np.abs(luma(repaired)[inner] - luma(clean[2])[inner]).mean()
        self.assertLess(after, 0.6 * before)

    def test_combing_tells_fields_from_frames(self):
        first, second = pan(2, step=6.0)
        woven = first.copy()
        woven[1::2] = second[1::2]
        self.assertGreater(movie.combing(cv2.cvtColor(woven, cv2.COLOR_BGR2GRAY)), movie.COMB_SHARE * 3)
        self.assertLess(movie.combing(cv2.cvtColor(first, cv2.COLOR_BGR2GRAY)), movie.COMB_SHARE / 3)


class StabiliseTests(unittest.TestCase):
    def test_weave_is_removed_and_pan_kept(self):
        random = np.random.default_rng(8)
        big = canvas(11)
        weave = random.uniform(-3, 3, (30, 2))
        frames = []
        for index in range(30):
            dx, dy = 20 + 2 * index + weave[index, 0], 30 + weave[index, 1]
            frames.append(cv2.warpAffine(big, np.float32([[1, 0, -dx], [0, 1, -dy]]), (240, 180)))
        steady = list(movie.stabilise_stream(frames, 100, fps=25))
        items = [movie._Steady(frame) for frame in steady]
        steps = np.array([movie.frame_motion(items[i - 1], items[i])[:2, 2] for i in range(6, 24)])
        # The pan of two pixels per frame stays; the weave of up to three pixels goes.
        self.assertAlmostEqual(float(steps[:, 0].mean()), 2.0, delta=0.4)
        self.assertLess(float(np.abs(np.diff(steps, axis=0)).mean()), 0.6)

    def test_still_footage_is_untouched(self):
        frames = pan(12, step=0.0, noise=0.0)
        for before, after in zip(frames, movie.stabilise_stream(frames, 100, fps=25)):
            self.assertIs(after, before)

    def test_smooth_path_keeps_a_steady_pan(self):
        times = np.arange(-2, 9, dtype=np.float64)
        self.assertAlmostEqual(float(movie.smooth_path(times, (3 * times + 5)[:, None], 3.0)[0]), 5.0, places=6)


class ColourTests(unittest.TestCase):
    def test_colour_follows_the_brightness_edge(self):
        frame = np.zeros((60, 320, 3), np.uint8)
        frame[:, :160] = (40, 40, 200)
        frame[:, 160:] = (200, 200, 200)
        ycc = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
        ycc[:, :, 1:] = cv2.blur(ycc[:, :, 1:], (9, 1))  # colour smeared sideways like tape
        bled = cv2.cvtColor(ycc, cv2.COLOR_YCrCb2BGR)
        sharp = movie.sharpen_chroma(bled, 1.0)
        width = lambda image: int((np.abs(np.diff(cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)[30, :, 1].astype(int))) > 1).sum())
        self.assertLess(width(sharp), width(bled))

    def test_black_and_white_skips_the_colour_stage(self):
        grey = [cv2.cvtColor(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR) for frame in pan(6)]
        self.assertFalse(movie.coloured(grey[0]))
        colourful = canvas()[:180, :240] // 2
        colourful[:, :120] += np.uint8([100, 20, 0])
        colourful[:, 120:] += np.uint8([0, 20, 100])
        self.assertTrue(movie.coloured(colourful))
        for before, after in zip(grey, movie.colour_stream(grey, 60)):
            self.assertIs(after, before)


class DateStampTests(unittest.TestCase):
    def test_stamp_with_ticking_seconds_is_removed(self):
        frames = pan(30, step=3.0)
        stamped = []
        for index, frame in enumerate(frames):
            frame = frame.copy()
            text = f"12.08.1994  14:03:{index // 5:02d}"
            cv2.putText(frame, text, (20, 165), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (40, 200, 255), 1, cv2.LINE_AA)
            stamped.append(frame)
        mask, guide = find_osd(np.stack(stamped))
        # The static date and the steady digits give the stamp away, and the
        # seconds sit inside the same line, so the whole stamp is covered.
        self.assertGreater((mask[150:170, 20:220] > 0).mean(), 0.5)
        cleaned = list(remove_stream(stamped, mask, guide))
        # Measured on the strokes of the text: they must be gone.
        strokes = np.abs(luma(stamped[15]) - luma(frames[15])) > 30
        self.assertGreater(strokes.sum(), 100)
        before = np.abs(luma(stamped[15]) - luma(frames[15]))[strokes].mean()
        after = np.abs(luma(cleaned[15]) - luma(frames[15]))[strokes].mean()
        self.assertLess(after, 0.3 * before)


class CleanFootageTests(unittest.TestCase):
    def test_clean_pan_stays_nearly_unchanged(self):
        frames = pan(24, step=1.0, noise=1.5)
        stream = movie.tape_stream(frames, 60)
        stream = movie.flicker_stream(stream, 60)
        stream = movie.dust_stream(stream, 60)
        stream = movie.colour_stream(stream, 0)
        repaired = list(movie.stabilise_stream(stream, 60, fps=25))
        for before, after in zip(frames[4:-4], repaired[4:-4]):
            self.assertGreater(psnr(before[8:-8, 8:-8], after[8:-8, 8:-8]), 40)


class RecipeTests(unittest.TestCase):
    def test_movie_fields_validate(self):
        Arbeitsrezept(signalart="film", stabilisierung=40, flackerausgleich=50, staubentfernung=60,
                      bandstoerung=30, koernung_behalten=True).validate()
        for name in FILM_WERTE:
            for wrong in (-1, 101, 50.5, True):
                with self.assertRaises(ValueError):
                    Arbeitsrezept(signalart="film", **{name: wrong}).validate()
        with self.assertRaises(ValueError):
            Arbeitsrezept(koernung_behalten=1).validate()

    def test_older_recipes_load_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "recipe.json"
            data = asdict(Arbeitsrezept(signalart="tape", farbberuhigung=45))
            for name in (*FILM_WERTE, "koernung_behalten"):
                del data[name]
            path.write_text(json.dumps(data), encoding="utf-8")
            loaded = Arbeitsrezept.load(path)
            self.assertEqual(loaded, Arbeitsrezept(signalart="tape", farbberuhigung=45))
            movie_recipe = Arbeitsrezept(signalart="film", staubentfernung=70, koernung_behalten=True)
            movie_recipe.save(path)
            self.assertEqual(Arbeitsrezept.load(path), movie_recipe)


@unittest.skipUnless(tools_available(), "FFmpeg tools are required")
class MovieExportTests(unittest.TestCase):
    def test_interlaced_tape_exports(self):
        with tempfile.TemporaryDirectory(prefix="analogrepair-movie-") as scratch:
            folder = Path(scratch)
            source = folder / "tape.mkv"
            # A 4:3 SD-like clip stored as interlaced fields, with sound.
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=50",
                            "-f", "lavfi", "-i", "sine=frequency=330",
                            "-t", "2", "-vf", "interlace=scan=tff", "-c:v", "libx264", "-flags", "+ildct+ilme",
                            "-x264opts", "tff=1", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)], check=True)
            info = inspect_video(source)
            self.assertTrue(movie.interlaced(source, info, 0.0, info.duration))
            recipe = asdict(Arbeitsrezept(signalart="tape", farbberuhigung=30, rauschminderung=30,
                                          vergroesserung_prozent=150, stabilisierung=40, flackerausgleich=40,
                                          staubentfernung=40, bandstoerung=40, koernung_behalten=True,
                                          osd_entfernen=False, schnittbeginn=0.2, schnittende=1.6))
            settings = folder / "request.json"
            target = folder / "tape-cleaned.mp4"
            settings.write_text(json.dumps({"action": "export", "source": str(source), "target": str(target),
                                            "recipe": recipe}), encoding="utf-8")
            run(json.loads(settings.read_text(encoding="utf-8")))
            made = inspect_video(target)
            self.assertEqual((made.width, made.height), (480, 360))
            self.assertTrue(made.has_audio)
            self.assertAlmostEqual(made.duration, 1.4, delta=0.15)
            before, after = folder / "before.png", folder / "after.png"
            run({"action": "preview", "source": str(source), "seconds": 0.9, "before": str(before),
                 "after": str(after), "recipe": recipe})
            self.assertEqual(cv2.imread(str(after)).shape[:2], (360, 480))
            self.assertEqual(cv2.imread(str(before)).shape[:2], (240, 320))


if __name__ == "__main__":
    unittest.main()
