from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from grab_app.annotation import CropRectangle
from grab_app.recording import (
    GIF_FRAME_RATE,
    GIF_MAX_DIMENSION,
    cleanup_recordings,
    gif_command,
    gif_filter,
    next_recording_name,
    validate_recording_path,
)


class RecordingTests(unittest.TestCase):
    def test_runtime_recording_validation_is_strict(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = root / "runtime"
            runtime.mkdir()
            valid = runtime / "grab-recording-example.webm"
            valid.write_bytes(b"webm")
            self.assertEqual(validate_recording_path(valid, runtime), valid)

            for name in ("other.webm", "grab-recording-example.mp4"):
                path = runtime / name
                path.write_bytes(b"video")
                with self.assertRaises(ValueError):
                    validate_recording_path(path, runtime)

            outside = root / "grab-recording-outside.webm"
            outside.write_bytes(b"video")
            with self.assertRaises(ValueError):
                validate_recording_path(outside, runtime)

            link = runtime / "grab-recording-link.webm"
            link.symlink_to(valid)
            with self.assertRaises(ValueError):
                validate_recording_path(link, runtime)

    def test_cleanup_only_removes_old_grab_recordings(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary)
            old = runtime / "grab-recording-old.webm"
            fresh = runtime / "grab-recording-fresh.webm"
            unrelated = runtime / "unrelated.webm"
            for path in (old, fresh, unrelated):
                path.write_bytes(b"video")
            old_time = 100.0
            os.utime(old, (old_time, old_time))
            os.utime(unrelated, (old_time, old_time))
            cleanup_recordings(runtime, now=1000.0, maximum_age=500)
            self.assertFalse(old.exists())
            self.assertTrue(fresh.exists())
            self.assertTrue(unrelated.exists())

    def test_filter_and_command_apply_gif_profile(self):
        crop = CropRectangle(10, 20, 650, 500)
        filter_value = gif_filter(crop)
        self.assertIn(f"fps={GIF_FRAME_RATE}", filter_value)
        self.assertIn("crop=640:480:10:20", filter_value)
        self.assertIn(f"min({GIF_MAX_DIMENSION},iw)", filter_value)
        self.assertIn("palettegen", filter_value)
        self.assertIn("paletteuse", filter_value)
        command = gif_command(
            Path("/tmp/source recording.webm"),
            Path("/tmp/output recording.gif"),
            crop,
        )
        self.assertEqual(command[0], "ffmpeg")
        self.assertIn("/tmp/source recording.webm", command)
        self.assertIn("/tmp/output recording.gif", command)
        self.assertEqual(command[command.index("-loop") + 1], "0")
        self.assertIn("-an", command)

    def test_invalid_crop_is_rejected(self):
        with self.assertRaises(ValueError):
            gif_filter(CropRectangle(0, 0, 0, 10))

    def test_default_recording_name_is_timestamped(self):
        self.assertEqual(
            next_recording_name(datetime(2026, 7, 16, 9, 8, 7)),
            "Screen Recording 2026-07-16 09-08-07.gif",
        )

    def test_ffmpeg_integration_crops_animated_gif(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source recording.webm"
            output = root / "output recording.gif"
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc=size=64x48:rate=15:duration=0.5",
                    "-c:v",
                    "libvpx",
                    "-y",
                    str(source),
                ],
                check=True,
            )
            subprocess.run(
                gif_command(source, output, CropRectangle(8, 4, 56, 44)),
                check=True,
            )
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=width,height,nb_frames",
                    "-of",
                    "json",
                    str(output),
                ],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            )
            stream = json.loads(probe.stdout)["streams"][0]
            self.assertEqual((stream["width"], stream["height"]), (48, 40))
            self.assertGreater(int(stream["nb_frames"]), 1)


if __name__ == "__main__":
    unittest.main()
