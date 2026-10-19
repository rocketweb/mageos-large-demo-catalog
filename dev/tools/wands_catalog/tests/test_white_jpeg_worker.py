"""Exercise the real encoding/checkpoint path with a small, fixed test mask.

The production BiRefNet model is verified separately by the real Mini pilot.
"""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import white_jpeg_worker as worker
from white_jpeg_monitor import issues, verify_completed_copy


class MaskSession:
    def predict(self, image):
        mask = Image.new("L", image.size, 0)
        ImageDraw.Draw(mask).rectangle((8, 8, 23, 23), fill=255)
        return [mask]


class WhiteJpegWorkerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "originals"
        self.source.mkdir()
        for blue in (20, 80, 160):
            image = Image.new("RGB", (32, 32), (240, 230, 195))
            ImageDraw.Draw(image).rectangle((8, 8, 23, 23), fill=(30, 90, blue))
            encoded = io.BytesIO()
            image.save(encoded, "JPEG", quality=95)
            data = encoded.getvalue()
            (self.source / (hashlib.sha256(data).hexdigest() + ".jpg")).write_bytes(data)
        self.weights = self.root / "model"
        self.weights.write_bytes(b"test model identity")
        self.job = self.root / "candidate"
        self.model_patch = patch.object(worker, "MODEL_SHA256", worker.sha256(self.weights))
        self.model_patch.start()
        self.signal_patch = patch.object(worker.signal, "signal")
        self.signal_patch.start()
        self.original_bytes = {p.name: p.read_bytes() for p in self.source.iterdir()}
        with contextlib.redirect_stdout(io.StringIO()):
            worker.prepare(self.source, self.job, self.source, self.weights, 3)

    def tearDown(self):
        self.signal_patch.stop()
        self.model_patch.stop()
        self.temp.cleanup()

    def run_job(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return worker.run(self.job, session_factory=lambda config: MaskSession(), **kwargs)

    def assert_originals_intact(self):
        self.assertEqual(self.original_bytes, {p.name: p.read_bytes() for p in self.source.iterdir()})

    def test_resume_preserves_finished_files_and_originals(self):
        first = self.run_job(max_images=1)
        self.assertEqual((first["state"], first["done"]), ("checkpointed", 1))
        output = next((self.job / "media/wands-expanded").glob("*.jpg"))
        before = (output.read_bytes(), output.stat().st_mtime_ns)
        final = self.run_job()
        self.assertEqual((final["state"], final["done"], final["failed"]), ("complete", 3, 0))
        self.assertEqual(before, (output.read_bytes(), output.stat().st_mtime_ns))
        self.assertEqual(len((self.job / "mapping.csv").read_text().splitlines()), 4)
        for path in (self.job / "media/wands-expanded").glob("*.jpg"):
            self.assertEqual(worker.sha256(path), path.stem)
            with Image.open(path) as image:
                self.assertEqual(image.mode, "RGB")
                self.assertTrue(image.info["progressive"])
                # Lossy JPEG can introduce a few levels of ringing near an edge.
                self.assertLessEqual(max(255-c for c in image.getpixel((0, 0))), 3)
        self.assert_originals_intact()

    def test_crash_after_file_publish_reuses_orphan_without_overwrite(self):
        real_convert = worker.convert_one
        def crash(*args):
            real_convert(*args)
            raise KeyboardInterrupt("simulated termination before checkpoint")
        with patch.object(worker, "convert_one", side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                self.run_job()
        output = next((self.job / "media/wands-expanded").glob("*.jpg"))
        before = (output.read_bytes(), output.stat().st_mtime_ns)
        final = self.run_job()
        self.assertEqual((final["done"], final["restarts"]), (3, 1))
        self.assertEqual(before, (output.read_bytes(), output.stat().st_mtime_ns))
        self.assert_originals_intact()

    def test_changed_input_is_reported_and_other_images_finish(self):
        changed = sorted(self.source.iterdir())[0]
        data = bytearray(changed.read_bytes())
        data[-1] ^= 1
        changed.write_bytes(data)
        final = self.run_job()
        self.assertEqual((final["state"], final["done"], final["failed"]), ("complete_with_errors", 2, 1))
        self.assertIn("hash mismatch", final["failures"][0]["error"])
        self.assertEqual(changed.read_bytes(), data)

    def test_changed_completed_output_stops_resume(self):
        self.run_job(max_images=1)
        output = next((self.job / "media/wands-expanded").glob("*.jpg"))
        output.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "Checkpointed output"):
            self.run_job()
        self.assertEqual(output.read_bytes(), b"changed")
        self.assert_originals_intact()

    def test_missing_completed_file_is_regenerated_on_resume(self):
        self.run_job(max_images=1)
        output = next((self.job / "media/wands-expanded").glob("*.jpg"))
        before = output.read_bytes()
        output.unlink()
        final = self.run_job()
        self.assertEqual((final["state"], final["done"]), ("complete", 3))
        self.assertEqual(output.read_bytes(), before)
        self.assert_originals_intact()

    def test_monitor_detects_stall_dead_worker_disk_and_failure(self):
        now = time.time()
        snapshot = {"state": "running", "updated_at": now, "started_at": now-1000,
                    "last_finished_at": now-700, "worker_alive": False,
                    "free_disk_bytes": 1, "reserve_bytes": 100, "failed": 1}
        problems = issues(snapshot, now)
        self.assertEqual(len(problems), 4)
        snapshot.update(state="complete", worker_alive=False, free_disk_bytes=1000, failed=0)
        self.assertEqual(issues(snapshot, now), [])

    def test_completed_copy_verifies_all_original_and_output_hashes(self):
        final = self.run_job()
        config = {"originals": str(self.source)}
        verified = verify_completed_copy(self.job, config, final)
        self.assertEqual((verified["originals_intact"], verified["candidate_mappings_verified"]), (3, 3))
        output = next((self.job / "media/wands-expanded").glob("*.jpg"))
        output.write_bytes(b"corrupted local copy")
        with self.assertRaisesRegex(ValueError, "candidate hash mismatch"):
            verify_completed_copy(self.job, config, final)


if __name__ == "__main__":
    unittest.main()
