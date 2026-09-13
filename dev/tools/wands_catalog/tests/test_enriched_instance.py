from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'distribution/acceptance'


class EnrichedInstanceTest(unittest.TestCase):
    def test_case_receipts_are_isolated_per_database(self):
        source=(ROOT/'commerce_case.php').read_text()
        self.assertIn("'/var/commerce/' . $database . '/'",source)

    def test_tier_price_adapter_respects_global_price_scope(self):
        source = (ROOT / 'commerce_case.php').read_text()
        self.assertIn("getValue('catalog/price/scope')", source)
        self.assertIn("'website_id'=>$priceWebsite", source)

    def test_product_import_uses_native_link_preserving_behavior(self):
        source = (ROOT.parents[4] / 'app/code/RocketWeb/LabCatalog/Model/Catalog/ProductImporter.php').read_text()
        self.assertIn("'behavior' => Import::BEHAVIOR_APPEND", source)

    def test_installer_options_use_cli_string_types(self):
        source = (ROOT / 'enriched_install.php').read_text()
        self.assertNotRegex(source, r"'--[^']+'\s*=>\s*\d+")
        self.assertIn('stream_get_contents(STDIN)', source)

    def test_harness_refuses_non_target_directory(self):
        result = subprocess.run([sys.executable, str(ROOT / 'enriched_instance.py'), 'bootstrap'],
                                cwd='/private/tmp', capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Wrong target root', result.stderr)


if __name__ == '__main__': unittest.main()
