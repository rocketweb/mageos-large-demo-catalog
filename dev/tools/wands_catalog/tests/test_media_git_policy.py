"""Product binaries stay outside the source repository; provenance stays versioned."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".tif", ".tiff"}


@unittest.skipUnless(shutil.which("git"), "Git is required to validate ignore policy")
class MediaGitPolicyTest(unittest.TestCase):
    def test_ignore_rules_exclude_product_images_but_keep_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".gitignore").write_bytes((ROOT / ".gitignore").read_bytes())
            subprocess.run(["git", "init", "--quiet", str(root)], check=True, capture_output=True)
            for suffix in sorted(IMAGE_SUFFIXES):
                for extension in (suffix, suffix.upper()):
                    for path in (
                        "pub/media/import/wands/WANDS-000001" + extension,
                        "var/wands/bulk-realism-v3/media/WANDS-000001" + extension,
                        "dev/tools/wands_catalog/assets/reference-repairs-v2/WANDS-000001" + extension,
                        "dev/tools/wands_catalog/assets/WANDS-BUNDLE-001-REALISM" + extension,
                    ):
                        with self.subTest(path=path):
                            result = subprocess.run(
                                ["git", "-C", str(root), "check-ignore", "--no-index", "--quiet", path],
                                capture_output=True,
                            )
                            self.assertEqual(result.returncode, 0, path + " must be ignored")
            for path in (
                "dev/tools/wands_catalog/reference-repairs.json",
                "dev/tools/wands_catalog/assets/reference-repairs-v2/generation-events.jsonl",
                "dev/tools/wands_catalog/assets/reference-repairs-v2/reference-audit.jsonl",
                "dev/tools/wands_catalog/README.md",
                "dev/tools/wands_catalog/assets/tool-screenshot.png",
                "dev/tools/wands_catalog/assets/workflow-diagram.webp",
                "dev/tools/wands_catalog/preview.jpg",
                "dev/tools/wands_catalog/WANDS-tool-preview.png",
                "app/design/frontend/Example/theme/web/images/logo.png",
            ):
                with self.subTest(path=path):
                    result = subprocess.run(
                        ["git", "-C", str(root), "check-ignore", "--no-index", "--quiet", path],
                        capture_output=True,
                    )
                    self.assertEqual(result.returncode, 1, path + " must remain eligible for Git")

    def test_index_contains_no_product_images(self):
        if not (ROOT / ".git").exists():
            self.skipTest("Source archive has no Git index")
        result = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z", "--",
             "dev/tools/wands_catalog", "pub/media", "var"],
            check=True, capture_output=True, text=True,
        )
        images = [path for path in result.stdout.split("\0")
                  if Path(path).suffix.lower() in IMAGE_SUFFIXES and (
                      path.startswith(("pub/media/", "var/"))
                      or Path(path).name.startswith("WANDS-BUNDLE-")
                      or (Path(path).name.startswith("WANDS-") and Path(path).name[6:7].isdigit())
                  )]
        self.assertEqual(images, [], "Untrack product images while preserving local files")
