from __future__ import annotations

import csv
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_merchandising_catalog import (
    CONFIGURABLE_CSV_FIELDS,
    PlanConfig,
    build_plan,
    deduplicate_family_names,
    plan_family,
)


class BuildMerchandisingCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source_rows = [
            self.source_row(index, product_class)
            for index, product_class in enumerate(
                [
                    "Area Rugs",
                    "Area Rugs",
                    "Beds",
                    "Beds",
                    "Accent Chairs",
                    "Accent Chairs",
                    "Curtains",
                    "Accent Pillows",
                    "Desks",
                    "Dining Tables",
                    "Tile",
                    "Table Lamps",
                    "Outdoor Conversation Sets",
                    "Patio Tables",
                    "Kids Beds",
                    "Dog Beds & Mats",
                    "Sofas",
                    "Coffee & Cocktail Tables",
                    "Office Chairs",
                    "Bookcases",
                    "Vanities",
                    "Wall & Accent Mirrors",
                    "Bathroom Sink Faucets",
                    "Bedding Sets",
                    "Nightstands",
                    "Dressers & Chests",
                    "Dining Chairs",
                    "Bar Stools",
                    "Planters",
                    "Bath Rugs & Mats",
                    "Crib Bedding Sets",
                    "Coat Racks and Hooks",
                    "Ottomans",
                    "Floor Lamps",
                    "Dog and Cat Bowls, Feeders & Accessories",
                    "Pet Gates",
                ]
            )
        ]
        self.prepared_rows = [self.prepared_row(row) for row in self.source_rows]

    @staticmethod
    def source_row(index: int, product_class: str) -> dict[str, str]:
        department = "Furniture"
        if "Rug" in product_class:
            department = "Rugs"
        elif product_class.startswith(("Outdoor", "Patio", "Planter")):
            department = "Outdoor"
        elif product_class.startswith(("Kids", "Crib")):
            department = "Baby & Kids"
        elif product_class.startswith(("Dog", "Pet", "Cat")):
            department = "Pet"
        return {
            "product_id": str(index + 1),
            "product_name": f"Sample {product_class} {index + 1}",
            "product_class": product_class,
            "category hierarchy": f"{department} / {product_class}",
            "product_description": f"Original description for {product_class.lower()} {index + 1}.",
            "product_features": (
                "color : navy|finish : walnut|primarymaterial : solid wood|"
                "mattresssize : queen|overallwidth-sidetoside:60|"
                "seatheight-floortoseat:30|seatingcapacity:4|numberofpiecesincluded:3"
            ),
            "average_rating": "4.5",
            "review_count": "20",
        }

    @staticmethod
    def prepared_row(source_row: dict[str, str]) -> dict[str, str]:
        product_id = int(source_row["product_id"])
        return {
            "sku": f"WANDS-{product_id:06d}",
            "store_view_code": "",
            "attribute_set_code": "Default",
            "product_type": "simple",
            "categories": f"WANDS Catalog/{source_row['category hierarchy'].replace(' / ', '/')}",
            "product_websites": "wands",
            "name": source_row["product_name"].title(),
            "description": source_row["product_description"],
            "short_description": source_row["product_description"],
            "weight": "10.00",
            "product_online": "1",
            "tax_class_name": "Taxable Goods",
            "visibility": "Catalog, Search",
            "price": "199.99",
            "url_key": f"wands-{product_id}-sample",
            "meta_title": source_row["product_name"].title(),
            "meta_description": source_row["product_description"],
            "qty": "20",
            "out_of_stock_qty": "0",
            "use_config_min_qty": "1",
            "is_in_stock": "1",
            "manage_stock": "1",
            "use_config_manage_stock": "0",
            "wands_product_id": source_row["product_id"],
            "wands_product_class": source_row["product_class"],
            "wands_average_rating": "4.50",
            "wands_review_count": "20",
            "lab_price_method": "test",
            "lab_price_version": "test-v1",
            "lab_price_synthetic": "Yes",
        }

    def test_two_axis_family_has_six_unique_hidden_children(self) -> None:
        family = plan_family(self.source_rows[0], self.prepared_rows[0], one_axis=False)

        self.assertEqual(len(family["axes"]), 2)
        self.assertEqual(len(family["variants"]), 6)
        self.assertEqual(len({variant["sku"] for variant in family["variants"]}), 6)
        self.assertEqual(
            len({tuple(variant["options"].items()) for variant in family["variants"]}),
            6,
        )
        self.assertTrue(all(variant["visibility"] == "Not Visible Individually" for variant in family["variants"]))
        self.assertTrue(all(variant["wands_product_id"] == "" for variant in family["variants"]))

    def test_one_axis_family_has_four_variants_and_rewritten_copy(self) -> None:
        family = plan_family(self.source_rows[2], self.prepared_rows[2], one_axis=True)

        self.assertEqual(len(family["axes"]), 1)
        self.assertEqual(len(family["variants"]), 4)
        self.assertNotEqual(family["parent"]["description"], self.prepared_rows[2]["description"])
        self.assertIn("Choose", family["parent"]["description"])
        self.assertTrue(all(variant["description"] for variant in family["variants"]))

    def test_axis_profiles_fit_lamps_and_outdoor_sets(self) -> None:
        lamp = plan_family(self.source_rows[33], self.prepared_rows[33], one_axis=False)
        outdoor_set = plan_family(self.source_rows[12], self.prepared_rows[12], one_axis=False)

        self.assertEqual([axis["attribute"] for axis in lamp["axes"]], ["wands_finish", "color"])
        self.assertEqual(
            [axis["attribute"] for axis in outdoor_set["axes"]],
            ["wands_piece_count", "color"],
        )

    def test_sized_family_uses_natural_option_order_and_removes_fixed_dimension_from_parent_name(self) -> None:
        source = self.source_row(90, "Doormats")
        source["product_name"] = "Welcome 30 In. x 18 In. Door Mat"
        prepared = self.prepared_row(source)
        prepared["name"] = "Welcome 30 In. x 18 In. Door Mat"

        family = plan_family(source, prepared, one_axis=True)

        self.assertNotIn("30 In", family["parent"]["name"])
        self.assertEqual(
            family["axes"][0]["values"],
            ["18 in x 30 in", "24 in x 36 in", "30 in x 48 in", "36 in x 60 in"],
        )
        prices = [float(variant["price"]) for variant in family["variants"]]
        self.assertEqual(prices, sorted(prices))

    def test_bunk_bed_uses_bunk_configuration_sizes(self) -> None:
        source = self.source_row(91, "Kids Beds")
        source["product_name"] = "Convertible Bunk Bed"
        prepared = self.prepared_row(source)

        family = plan_family(source, prepared, one_axis=True)

        self.assertEqual(
            family["axes"][0]["values"],
            ["Twin over Twin", "Twin over Full", "Full over Full", "Twin XL over Queen"],
        )

    def test_light_count_family_name_does_not_claim_one_fixed_count(self) -> None:
        source = self.source_row(92, "Chandeliers")
        source["product_name"] = "Emmaline 6-Light Candle Chandelier"
        prepared = self.prepared_row(source)
        prepared["name"] = "Emmaline 6-Light Candle Chandelier"

        family = plan_family(source, prepared, one_axis=True)

        self.assertEqual(family["parent"]["name"], "Emmaline Candle Chandelier")
        self.assertEqual(family["axes"][0]["attribute"], "wands_light_count")

    def test_duplicate_family_names_receive_distinct_collection_names_and_copy(self) -> None:
        first = plan_family(self.source_rows[0], self.prepared_rows[0], one_axis=True)
        second_source = dict(self.source_rows[0], product_id="999")
        second_prepared = dict(self.prepared_rows[0], sku="WANDS-000999", wands_product_id="999")
        second = plan_family(second_source, second_prepared, one_axis=True)

        deduplicate_family_names([first, second])

        self.assertNotEqual(first["parent"]["name"], second["parent"]["name"])
        self.assertIn(first["parent"]["name"], first["parent"]["description"])
        self.assertIn(second["parent"]["name"], second["variants"][0]["description"])

    def test_configurable_parent_preserves_required_price(self) -> None:
        family = plan_family(self.source_rows[0], self.prepared_rows[0], one_axis=True)

        self.assertEqual(family["parent"]["price"], self.prepared_rows[0]["price"])

    def test_small_plan_is_exact_deterministic_and_excludes_configurable_parents_from_bundles(self) -> None:
        config = PlanConfig(
            group_quotas={
                "rugs_mats": 1,
                "beds_bedding": 1,
                "chairs_stools": 1,
                "curtains_pillows": 1,
                "casegoods": 1,
                "tile_lighting": 1,
                "outdoor": 1,
                "baby_pet": 1,
            },
            one_axis_quotas={
                "rugs_mats": 1,
                "beds_bedding": 0,
                "chairs_stools": 0,
                "curtains_pillows": 0,
                "casegoods": 0,
                "tile_lighting": 0,
                "outdoor": 0,
                "baby_pet": 0,
            },
            bundle_themes={"Living Room": 1},
        )

        first = build_plan(self.source_rows, self.prepared_rows, config)
        second = build_plan(self.source_rows, self.prepared_rows, config)

        self.assertEqual(first, second)
        self.assertEqual(len(first["families"]), 8)
        self.assertEqual(sum(len(family["variants"]) for family in first["families"]), 46)
        self.assertEqual(len(first["bundles"]), 1)
        parent_skus = {family["parent"]["sku"] for family in first["families"]}
        bundle_skus = {
            selection["sku"]
            for bundle in first["bundles"]
            for option in bundle["options"]
            for selection in option["selections"]
        }
        self.assertFalse(parent_skus & bundle_skus)

    def test_writer_outputs_native_magento_columns_and_manifest_hashes(self) -> None:
        config = PlanConfig(
            group_quotas={
                "rugs_mats": 1,
                "beds_bedding": 1,
                "chairs_stools": 1,
                "curtains_pillows": 1,
                "casegoods": 1,
                "tile_lighting": 1,
                "outdoor": 1,
                "baby_pet": 1,
            },
            one_axis_quotas={group: 0 for group in (
                "rugs_mats", "beds_bedding", "chairs_stools", "curtains_pillows",
                "casegoods", "tile_lighting", "outdoor", "baby_pet",
            )},
            bundle_themes={"Living Room": 1},
        )

        with tempfile.TemporaryDirectory() as directory:
            from build_merchandising_catalog import write_plan

            result = write_plan(build_plan(self.source_rows, self.prepared_rows, config), Path(directory))

            self.assertEqual(result["configurable_parents"], 8)
            self.assertEqual(result["simple_children"], 48)
            self.assertEqual(result["bundle_products"], 1)
            self.assertEqual(result["bundle_image_prompts"], 1)
            self.assertEqual(
                result["image_prompts"],
                result["variant_image_prompts"] + result["bundle_image_prompts"],
            )
            self.assertEqual(result["pilot_families"], 8)
            self.assertEqual(result["pilot_children"], 48)
            self.assertEqual(result["pilot_bundles"], 1)
            self.assertIn("configurable_parents_csv_sha256", result)
            with (Path(directory) / "image-prompts.jsonl").open(encoding="utf-8") as stream:
                image_prompts = [json.loads(line) for line in stream]
            bundle_prompt = next(prompt for prompt in image_prompts if prompt.get("kind") == "bundle")
            self.assertEqual(bundle_prompt["sku"], "WANDS-BUNDLE-001")
            self.assertEqual(bundle_prompt["output_file"], "WANDS-BUNDLE-001.jpg")
            self.assertIn("Living Room", bundle_prompt["prompt"])
            self.assertIn("No visible text", bundle_prompt["prompt"])
            with (Path(directory) / "configurable-parents.csv").open(newline="", encoding="utf-8") as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(list(row), CONFIGURABLE_CSV_FIELDS)
            self.assertIn("sku=", row["configurable_variations"])
            self.assertIn("wands_size=", row["configurable_variation_labels"])
            manifest = json.loads((Path(directory) / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], 1)
            pilot_manifest = json.loads(
                (Path(directory) / "batches" / "pilot" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(pilot_manifest["families"], 8)
            self.assertEqual(pilot_manifest["children"], 48)
            self.assertTrue((Path(directory) / pilot_manifest["children_csv"]).is_file())
            self.assertTrue((Path(directory) / pilot_manifest["rollback_parents_csv"]).is_file())
            self.assertTrue((Path(directory) / pilot_manifest["rollback_disable_bundles_csv"]).is_file())
            with (Path(directory) / pilot_manifest["image_prompts_jsonl"]).open(encoding="utf-8") as stream:
                self.assertTrue(all(json.loads(line).get("kind") != "bundle" for line in stream))
            with (Path(directory) / pilot_manifest["bundle_image_prompts_jsonl"]).open(
                encoding="utf-8"
            ) as stream:
                pilot_bundle_prompts = [json.loads(line) for line in stream]
            self.assertEqual(len(pilot_bundle_prompts), 1)
            self.assertEqual(pilot_bundle_prompts[0]["kind"], "bundle")
            with (Path(directory) / pilot_manifest["rollback_parents_csv"]).open(
                newline="", encoding="utf-8"
            ) as stream:
                self.assertEqual(sum(1 for _ in csv.DictReader(stream)), 8)
            with (Path(directory) / pilot_manifest["rollback_disable_bundles_csv"]).open(
                newline="", encoding="utf-8"
            ) as stream:
                self.assertEqual(sum(1 for _ in csv.DictReader(stream)), 1)

    def test_pilot_selection_prioritizes_two_axis_coverage_and_group_breadth(self) -> None:
        from build_merchandising_catalog import select_pilot_families

        families = []
        for index, (group, one_axis, axes) in enumerate((
            ("rugs", False, ["wands_size", "color"]),
            ("rugs", True, ["wands_size"]),
            ("rugs", False, ["wands_size", "color"]),
            ("lighting", False, ["wands_finish", "color"]),
            ("lighting", False, ["wands_light_count", "wands_finish"]),
            ("lighting", True, ["wands_finish"]),
            ("outdoor", False, ["wands_piece_count", "color"]),
            ("outdoor", True, ["wands_piece_count"]),
        )):
            families.append({
                "group": group,
                "one_axis": one_axis,
                "axes": [{"attribute": attribute} for attribute in axes],
                "parent": {"sku": f"WANDS-{index:06d}"},
            })

        selected = select_pilot_families(families, 7)

        self.assertEqual(len(selected), 7)
        self.assertEqual({family["group"] for family in selected}, {"rugs", "lighting", "outdoor"})
        self.assertEqual(sum(not family["one_axis"] for family in selected), 4)

    def test_build_result_is_concise_by_default_and_logs_completion(self) -> None:
        from build_merchandising_catalog import emit_build_result

        manifest = {
            "configurable_parents": 2000,
            "simple_children": 10800,
            "bundle_products": 50,
            "image_prompts": 3385,
        }
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            (output_dir / "manifest.json").write_text("{}\n", encoding="utf-8")
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                emit_build_result(manifest, output_dir, json_stdout=False)

            terminal_output = stdout.getvalue()
            self.assertEqual(terminal_output.count("\n"), 1)
            self.assertNotIn("attribute_options", terminal_output)
            self.assertIn("2,000 configurable parents", terminal_output)
            events = [
                json.loads(line)
                for line in (output_dir / "build-merchandising.log").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(events[-1]["status"], "completed")
            self.assertEqual(events[-1]["image_prompts"], 3385)


if __name__ == "__main__":
    unittest.main()
