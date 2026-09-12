import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from realism_rules import price, class_tokens, brand, stock, title, bundle_eligible
from build_realism_catalog import product_changes, copy_for, validate, family_prices
import test_build_merchandising_catalog as fixtures


def row(cls="Office Chairs", name="Velvet office chair", features=""):
    return {"product_id": "42963", "product_class": cls, "product_name": name,
            "product_features": features, "category hierarchy": "Furniture / Office Furniture / Office Chairs"}


class RealismCatalogTest(unittest.TestCase):
    def test_class_beats_misleading_title(self):
        self.assertEqual(price(row())["amount"], price(row(name="Vanity sofa office chair"))["amount"])

    def test_missing_class_uses_taxonomy_not_title(self):
        self.assertEqual(price(row(cls=""))["basis"], "taxonomy")
        self.assertGreater(price(row(cls=""))["amount"], 100)

    def test_pillowcase_subtype_not_sheet_set(self):
        self.assertLess(price(row(cls="Sheets And Sheet Sets", name="Emma body pillowcase"))["amount"], 40)

    def test_pack_pricing_does_not_apply_twice(self):
        single = price(row(cls="Cabinet and Drawer Knobs", name="Knob"))["amount"]
        pack = price(row(cls="Cabinet and Drawer Knobs", name="Knob pack of 10", features="Number of Pieces Included: 10"))
        self.assertEqual(pack["sale_quantity"], 10)
        self.assertLess(pack["amount"], single * 11)
        self.assertGreater(pack["amount"], single * 7)

    def test_unit_conflict_does_not_guess_quantity(self):
        result = price(row(cls="Cabinet and Drawer Knobs", name="Knob pack of 10", features="Number of Pieces Included: 4"))
        self.assertIn("sale_quantity_conflict", result["flags"])

    def test_bedding_composition_is_not_per_piece_pricing(self):
        result = price(row(cls="Bedding Sets", name="Three piece bedding", features="Number of Pieces Included: 3|Number of Pieces Included: 4"))
        self.assertNotIn("sale_quantity_conflict", result["flags"])
        self.assertIn("composition_conflict_withheld", result["flags"])

    def test_brand_preserves_explicit_source_brand(self):
        result = brand(row(features="Brand: All-Clad"))
        self.assertEqual(result["source_brand"], "All-Clad")
        self.assertTrue(result["fictional_collection"])

    def test_stock_deterministic_without_unsupported_delivery_promise(self):
        a = stock("X")
        self.assertEqual(a, stock("X"))
        self.assertNotIn("delivery_date", a)
        self.assertEqual(a["backorders"], "0")

    def test_title_removes_conflicting_family_color(self):
        name = title(row(cls="Area Rugs", name="Goggin Floral Silver/Plum Area Rug"), {"color"}, {})
        self.assertNotIn("Silver", name)
        self.assertNotIn("Plum", name)
        self.assertIn("Goggin", name)

    def test_bundle_rejects_outdoor_sofa_for_indoor_room(self):
        self.assertFalse(bundle_eligible(row(cls="Patio Sofas"), "Living Room", "Seating", ("sofas",)))
        self.assertTrue(bundle_eligible(row(cls="Sofas"), "Living Room", "Seating", ("sofas",)))

    def test_bundle_rejects_child_desk_for_adult_office(self):
        self.assertFalse(bundle_eligible(row(cls="Kids Desks|Desks"), "Home Office", "Desk", ("desks",)))

    def test_class_tokens_exact_and_trimmed(self):
        self.assertEqual(class_tokens("End Tables | Nightstands"), {"end tables", "nightstands"})

    def test_product_changes_preserve_inputs_and_escape_html(self):
        import copy
        source = fixtures.BuildMerchandisingCatalogTest.source_row(1, "Office Chairs")
        source["product_name"] = "<script>chair</script>"
        original = fixtures.BuildMerchandisingCatalogTest.prepared_row(source)
        snapshot = copy.deepcopy(original)
        patches, proof = product_changes(source, original, None)
        self.assertEqual(original, snapshot)
        self.assertNotIn("<script>", patches[0]["description"])
        self.assertEqual(proof[0]["input_url_key_preserved"], original["url_key"])
        validate({patches[0]["sku"]: patches[0]}, {original["sku"]: original}, [], 0)

    def test_parent_stock_is_derived_and_has_no_independent_quantity(self):
        import copy
        source = fixtures.BuildMerchandisingCatalogTest.source_row(1, "Office Chairs")
        original = fixtures.BuildMerchandisingCatalogTest.prepared_row(source)
        original["product_type"] = "configurable"
        children = []
        for color in ("Blue", "Black"):
            child = copy.deepcopy(original)
            child.update(sku=color, product_type="simple", options={"color": color})
            children.append(child)
        family = {"axes": [{"attribute": "color", "label": "Color", "values": ["Blue", "Black"]}], "variants": children}
        patches, _ = product_changes(source, original, family)
        self.assertEqual(patches[0]["qty"], "0")
        self.assertEqual(patches[0]["manage_stock"], "0")
        self.assertEqual(patches[1]["price"], patches[2]["price"])
        self.assertEqual(patches[0]["is_in_stock"], str(int(any(p["is_in_stock"] == "1" for p in patches[1:]))))

    def test_pack_variants_price_by_quantity_not_option_position(self):
        family = {"axes": [{"attribute": "wands_pack_size", "values": ["Pack of 10", "Pack of 4"]}],
                  "variants": [{"sku": "A", "options": {"wands_pack_size": "Pack of 4"}},
                               {"sku": "B", "options": {"wands_pack_size": "Pack of 10"}}]}
        prices = family_prices({"amount": 40, "sale_quantity": 4, "quantity_priced": True}, family)
        self.assertAlmostEqual(prices["A"], 39.99)
        self.assertAlmostEqual(prices["B"], 99.99)


if __name__ == "__main__":
    unittest.main()
