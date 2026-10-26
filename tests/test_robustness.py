"""Failure cases that must not destroy an earlier render or load bad settings."""

from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

from analogrepair.media import VideoKenndaten, inspect_video, tools_available
from analogrepair.processor import process_one
from analogrepair.recipe import Arbeitsrezept
from analogrepair.restoration import process_temporal


@unittest.skipUnless(tools_available(), "FFmpeg tools are required")
class ExportRecoveryTest(unittest.TestCase):
    def test_failed_export_keeps_existing_result(self):
        with tempfile.TemporaryDirectory() as scratch:
            folder = Path(scratch)
            target = folder / "result.mp4"
            target.write_bytes(b"existing result")
            info = VideoKenndaten(1.0, 64, 64, False)
            result = process_one(folder / "missing.mp4", target, Arbeitsrezept(),
                                 info, lambda value: None, threading.Event())
            self.assertFalse(result.success)
            self.assertEqual(target.read_bytes(), b"existing result")
            self.assertFalse(list(folder.glob(".result-*.mp4")))

    def test_canceled_temporal_export_keeps_existing_result(self):
        with tempfile.TemporaryDirectory() as scratch:
            folder = Path(scratch)
            source = folder / "source.mp4"
            target = folder / "result.mp4"
            target.write_bytes(b"existing result")
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=8",
                            "-t", "1", "-c:v", "libx264", str(source)], check=True)
            cancel = threading.Event()
            cancel.set()
            result = process_temporal(source, target, Arbeitsrezept(signalart="tape"),
                                      inspect_video(source), lambda value: None, cancel)
            self.assertFalse(result.success)
            self.assertEqual(target.read_bytes(), b"existing result")
            self.assertFalse(list(folder.glob(".result-*.mp4")))


if __name__ == "__main__":
    unittest.main()
