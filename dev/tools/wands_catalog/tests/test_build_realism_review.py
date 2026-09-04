from __future__ import annotations

import sys
import csv
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_realism_review import (
    collect_facts, clean_title, price_proposal, variant_prices, bundle_flags,
    sample_products, availability, render_review, DEPARTMENTS, image_briefs,
)


def source(name="Desk chair", cls="Office Chairs", features="", pid="1"):
    return {"product_id": pid, "product_name": name, "product_class": cls,
            "product_features": features, "category hierarchy": "Furniture / Chairs"}


class RealismReviewTest(unittest.TestCase):
    def test_class_pricing_ignores_marketing_title(self):
        short = price_proposal(source())
        stuffed = price_proposal(source("Velvet desk chair vanity bed sofa"))
        self.assertEqual(short, stuffed)
        self.assertEqual(short["profile"], "Office Chairs")

    def test_unknown_class_is_held_not_guessed_from_title(self):
        self.assertIsNone(price_proposal(source(cls="Unknown"))["amount"])

    def test_conflicting_features_and_unitless_dimensions_are_withheld(self):
        facts, flags = collect_facts(source(features=
            "Frame Material: Solid Wood|Frame Material: MDF|Overall Width - Side to Side: 42|Shape: Round"))
        self.assertEqual(facts, {"Shape": "Round"})
        self.assertTrue(any("conflict" in flag for flag in flags))
        self.assertTrue(any("unit" in flag for flag in flags))

    def test_explicit_units_retained_and_claims_excluded(self):
        facts, _ = collect_facts(source(features="Width: 42 in|Warranty: Lifetime|Certified: Yes"))
        self.assertEqual(facts, {"Width": "42 in"})

    def test_cross_alias_conflicts_withheld(self):
        facts, flags = collect_facts(source(features="Width: 42 in|Overall Width - Side to Side: 36 in"))
        self.assertNotIn("Width", facts)
        self.assertTrue(flags)

    def test_color_axis_withholds_source_color(self):
        facts, flags = collect_facts(source(features="Color: Blue|Frame Material: Wood"), {"color"})
        self.assertNotIn("Color", facts)
        self.assertIn("Frame material", facts)
        self.assertTrue(flags)

    def test_size_axis_withholds_source_dimensions(self):
        facts, _ = collect_facts(source(features="Width: 42 in|Shape: Round"), {"wands_size"})
        self.assertEqual(facts, {"Shape": "Round"})

    def test_title_is_short_specific_and_preserves_model_token(self):
        row = source("Marlowe solid wood desk chair for home study living room", features="Frame Material: Solid Wood")
        self.assertEqual(clean_title(row, {"Frame material": "Solid Wood"}), "Marlowe Solid Wood Desk Chair")

    def test_short_source_title_is_not_replaced_by_broad_class(self):
        self.assertEqual(clean_title(source("emma body pillowcase", "Sheets And Sheet Sets"), {}), "Emma Body Pillowcase")
        self.assertEqual(clean_title(source("bowie coffee table with storage", "Coffee & Cocktail Tables"), {"Upholstery": "Linen"}), "Bowie Coffee Table With Storage")

    def test_chair_specific_upholstery_and_features_are_retained(self):
        row = source("elegant velvet desk chair for girls women modern swivel office computer chair on wheels cute vanity chair leisure chair w/arm for home study living room", features="Seat Upholstery Material: velvet|Swivel: yes|Armed: yes|Casters: yes")
        facts, _ = collect_facts(row)
        self.assertEqual(clean_title(row, facts), "Velvet Swivel Desk Chair with Arms")

    def test_bundle_multiclass_uses_exact_tokens_not_substrings(self):
        self.assertFalse(bundle_flags("End Tables|Nightstands", ("nightstands",), 100, [100]))
        self.assertTrue(bundle_flags("Patio Sofas", ("sofas",), 100, [100]))

    def test_prices_do_not_depend_on_option_order_or_color(self):
        axes = [{"attribute": "wands_size", "values": ["King", "Twin", "Queen"]},
                {"attribute": "color", "values": ["Blue", "Black"]}]
        variants = [{"sku": size+color, "options": {"wands_size": size, "color": color}}
                    for size in axes[0]["values"] for color in axes[1]["values"]]
        first, flags = variant_prices(100, axes, variants)
        axes[0]["values"].reverse()
        second, _ = variant_prices(100, axes, variants)
        self.assertFalse(flags)
        self.assertEqual(first, second)
        self.assertLess(first["TwinBlue"], first["QueenBlue"])
        self.assertLess(first["QueenBlue"], first["KingBlue"])
        self.assertEqual(first["KingBlue"], first["KingBlack"])

    def test_unknown_size_holds_entire_family(self):
        prices, flags = variant_prices(100, [{"attribute": "wands_size", "values": ["Mystery"]}],
                                      [{"sku": "A", "options": {"wands_size": "Mystery"}}])
        self.assertEqual(prices, {})
        self.assertTrue(flags)

    def test_bundle_exact_class_and_price_outlier(self):
        self.assertTrue(bundle_flags("Office Chairs", ("chairs",), 20, [20]))
        self.assertTrue(bundle_flags("Dog Beds & Mats", ("dog beds & mats",), 680, [55, 90, 680]))

    def test_sampling_order_independent_and_exact_quotas(self):
        rows = [source(pid=str(n)) for n in range(20)]
        first = sample_products(rows, {}, ["Furniture"], 10)
        self.assertEqual(first, sample_products(list(reversed(rows)), {}, ["Furniture"], 10))
        self.assertEqual(len(first), 10)

    def test_insufficient_sample_fails_closed(self):
        with self.assertRaises(ValueError):
            sample_products([], {}, ["Furniture"], 10)

    def test_availability_is_deterministic_and_explicitly_synthetic(self):
        self.assertEqual(availability("A"), availability("A"))
        self.assertTrue(availability("A")["synthetic"])

    def test_html_escapes_source_text(self):
        page = render_review([], [{"sku": "<script>alert(1)</script>"}], {})
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)

    def test_image_briefs_never_combine_different_light_counts(self):
        products = [{"sku": "F", "axes": [{"attribute": "wands_light_count"}, {"attribute": "color"}],
                     "variants": [{"sku": "A", "options": {"color": "Black", "wands_light_count": "1 Light"}},
                                  {"sku": "B", "options": {"color": "Black", "wands_light_count": "3 Lights"}}]}]
        briefs = image_briefs(products)
        self.assertEqual(len(briefs), 2)
        self.assertTrue(all(b["geometry_review_required"] and b["reference_image"] is None for b in briefs))

    def test_cli_quiet_reproducible_read_only_and_preserves_existing_packet(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_path, prepared_path = root / "source.tsv", root / "prepared.csv"
            raw = [{**source(pid=str(i * 10 + n)), "category hierarchy": dept + " / Chairs"}
                   for i, dept in enumerate(DEPARTMENTS) for n in range(10)]
            prepared = [{"wands_product_id": r["product_id"], "sku": "S" + r["product_id"],
                         "name": "Desk Chair", "description": "Original", "price": "200", "qty": "10", "url_key": "chair-" + r["product_id"]} for r in raw]
            for path, rows, delimiter in [(source_path, raw, "\t"), (prepared_path, prepared, ",")]:
                with path.open("w", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter=delimiter)
                    writer.writeheader()
                    writer.writerows(rows)
            (root / "configurable-families.jsonl").write_text("")
            (root / "bundles.csv").write_text("sku,categories,bundle_values\n")
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            command = [sys.executable, str(Path(__file__).resolve().parents[1] / "build_realism_review.py"),
                       "--source-products", str(source_path), "--prepared-products", str(prepared_path),
                       "--merchandising-dir", str(root), "--output-dir"]
            for directory in ("first", "second"):
                result = subprocess.run([*command, str(root / directory)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr + (root / (directory + ".log")).read_text())
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "")
            first = root / "first"
            for path in first.iterdir():
                self.assertEqual(path.read_bytes(), (root / "second" / path.name).read_bytes())
            manifest = json.loads((first / "manifest.json").read_text())
            self.assertEqual(manifest["products"], 100)
            self.assertEqual(manifest["live_affected_products"], 0)
            self.assertFalse(list(first.glob("*.csv")))
            for name, contents in before.items():
                self.assertEqual((root / name).read_bytes(), contents)
            original = (first / "manifest.json").read_bytes()
            result = subprocess.run([*command, str(first)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual((first / "manifest.json").read_bytes(), original)
            self.assertIn("already exists", (root / "first.log").read_text())


if __name__ == "__main__":
    unittest.main()
