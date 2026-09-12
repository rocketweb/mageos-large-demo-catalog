import copy
import datetime as dt
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release_readiness import EMPTY, bundle_options, number, validate
from snapshot_preflight import compare as remote_compare, inverse_sql, literal, load_snapshot, media_inverse, normalized, run as run_preflight
from prepare_audit_repairs import complete_records, draft
from check_storefront_observations import check_case, compare as storefront_compare


def product():
    return {"sku": "WANDS-000001", "name": "Chair", "description": "<p>Chair</p>", "short_description": "Chair",
            "meta_title": "Chair", "meta_description": "Chair", "lab_brand": "Alder Cove", "lab_sale_unit": "catalog item",
            "lab_price_method": "synthetic", "lab_price_version": "v1", "store_view_code": "", "price": "100.00",
            "special_price": EMPTY, "qty": "5", "is_in_stock": "1", "manage_stock": "1", "use_config_manage_stock": "0", "backorders": "0", "use_config_backorders": "0"}


class ReleaseReadinessTest(unittest.TestCase):
    def fixture(self):
        row = product()
        sku = row["sku"]
        original = {sku: {"sku": sku, "product_type": "simple", "url_key": "chair"}}
        evidence = {sku: {"input_type_preserved": "simple", "input_url_key_preserved": "chair"}}
        return {sku: row}, original, evidence

    def test_full_validation_does_not_modify_source(self):
        products, originals, evidence = self.fixture()
        before = copy.deepcopy(products)
        result = validate(products, [], {}, evidence, originals)
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(products, before)

    def test_missing_metadata_and_negative_stock_are_errors(self):
        products, originals, evidence = self.fixture()
        products["WANDS-000001"].update(lab_brand="", qty="-1")
        codes = {e["code"] for e in validate(products, [], {}, evidence, originals)["errors"]}
        self.assertIn("missing_attribute", codes)
        self.assertIn("numeric_bounds", codes)

    def test_price_and_identity_drift_fail(self):
        products, originals, evidence = self.fixture()
        products["WANDS-000001"]["special_price"] = "110"
        evidence["WANDS-000001"]["input_url_key_preserved"] = "changed"
        codes = {e["code"] for e in validate(products, [], {}, evidence, originals)["errors"]}
        self.assertIn("special_price", codes)
        self.assertIn("identity_drift", codes)

    def test_nonfinite_numbers_rejected(self):
        for value in ("nan", "Infinity", "bad"):
            with self.assertRaises(ValueError):
                number(value)

    def test_malformed_bundle_syntax_rejected(self):
        for value in ("name=x,sku=x", "name=x,name=y"):
            with self.assertRaises(ValueError):
                bundle_options(value)

    def test_missing_child_is_reported(self):
        products, originals, evidence = self.fixture()
        family = {"parent": {"sku": "P"}, "axes": [{"attribute": "color", "values": ["Blue"]}],
                  "variants": [{"sku": "C", "color": "Blue", "options": {"color": "Blue"}, "product_type": "simple", "visibility": "Not Visible Individually"}]}
        codes = {e["code"] for e in validate(products, [family], {}, evidence, originals)["errors"]}
        self.assertIn("missing_family_product", codes)

    def test_sql_values_cannot_break_out_of_literal(self):
        value = "x'); DROP TABLE catalog_product_entity; --"
        self.assertNotIn("DROP", literal(value))
        self.assertEqual(literal(None), "NULL")
        self.assertEqual(normalized("1.0000", "decimal"), normalized("1", "decimal"))

    def test_inverse_is_exact_scoped_and_defaults_to_rollback(self):
        result = {"eav_scopes": {("catalog_product_entity_varchar", "12"): {"7"}}, "stock_inverse": [], "bundle_diff": []}
        tables = {"catalog_product_entity_varchar": [
            {"value_id": "3", "entity_id": "7", "attribute_id": "12", "store_id": "0", "value": "Before"},
            {"value_id": "4", "entity_id": "8", "attribute_id": "12", "store_id": "0", "value": "Outside"}]}
        sql, counts = inverse_sql(result, tables, {"database": "lab", "prefix": "m_"})
        self.assertTrue(sql.endswith("ROLLBACK;\n"))
        self.assertNotIn("FOREIGN_KEY_CHECKS", sql)
        self.assertIn("`lab`.`m_catalog_product_entity_varchar`", sql)
        self.assertEqual(counts["catalog_product_entity_varchar:restore_rows"], 1)
        self.assertNotIn("Outside".encode().hex(), sql)

    def test_snapshot_wrong_request_or_staleness_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = root / "request.json"
            request.write_text(json.dumps({"packet_sha256": "packet", "expected_host": "relevance.comtom.lab"}))
            manifest = {"request_sha256": "wrong", "packet_sha256": "packet", "host": "relevance.comtom.lab", "consistent_read_only": True,
                        "captured_at": (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)).isoformat(), "tables": {}}
            (root / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "identity"):
                load_snapshot(root, request)
            manifest["request_sha256"] = hashlib.sha256(request.read_bytes()).hexdigest()
            (root / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "stale"):
                load_snapshot(root, request)

    def remote_fixture(self):
        tables = {"catalog_product_entity_" + kind: [] for kind in ("varchar", "text", "decimal", "int", "datetime")}
        tables.update({name: [] for name in ("eav_entity_attribute", "catalog_eav_attribute", "catalog_product_super_attribute",
                       "eav_attribute_option", "eav_attribute_option_value", "catalog_product_bundle_option", "catalog_product_bundle_option_value",
                       "catalog_product_bundle_selection", "catalog_product_super_link")})
        tables["catalog_product_entity"] = [{"sku": "P", "entity_id": "1", "type_id": "configurable", "attribute_set_id": "4"},
                                             {"sku": "C", "entity_id": "2", "type_id": "simple", "attribute_set_id": "4"}]
        tables["eav_attribute"] = [{"attribute_code": "price", "attribute_id": "10", "backend_type": "decimal"},
                                    {"attribute_code": "color", "attribute_id": "11", "backend_type": "int", "frontend_input": "select"}]
        tables["eav_entity_attribute"] = [{"attribute_set_id": "4", "attribute_id": "10"}, {"attribute_set_id": "4", "attribute_id": "11"}]
        tables["catalog_product_entity_decimal"] = [{"entity_id": eid, "attribute_id": "10", "store_id": "0", "value": "100.0000"} for eid in ("1", "2")]
        tables["catalog_product_entity_int"] = [{"entity_id": "2", "attribute_id": "11", "store_id": "0", "value": "21"}]
        tables["cataloginventory_stock_item"] = [{"item_id": eid, "product_id": eid, "qty": "5.0000"} for eid in ("1", "2")]
        tables["catalog_product_super_link"] = [{"parent_id": "1", "product_id": "2"}]
        tables["catalog_product_super_attribute"] = [{"product_id": "1", "attribute_id": "11"}]
        tables["catalog_eav_attribute"] = [{"attribute_id": "11", "is_global": "1"}]
        tables["eav_attribute_option"] = [{"option_id": "21", "attribute_id": "11"}]
        tables["eav_attribute_option_value"] = [{"option_id": "21", "store_id": "0", "value": "Blue"}]
        request = {"skus": ["P", "C"], "intended_types": {"P": "configurable", "C": "simple"},
                   "configurable_links": {"P": ["C"]}, "configurable_axes": {"P": ["color"]}, "variant_options": {"C": {"color": "Blue"}}}
        products = {sku: {"sku": sku, "price": "100.00", "qty": "5"} for sku in ("P", "C")}
        return products, request, tables

    def test_remote_comparison_has_exact_field_and_stock_counts(self):
        products, request, tables = self.remote_fixture()
        result = remote_compare(products, {}, request, tables)
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["changes"], [])
        products["C"].update(price="90", qty="3")
        result = remote_compare(products, {}, request, tables)
        self.assertEqual(len(result["changes"]), 2)
        self.assertEqual({r["sku"] for r in result["changes"]}, {"C"})
        self.assertEqual(result["eav_scopes"], {("catalog_product_entity_decimal", "10"): {"2"}})
        self.assertEqual(result["stock_inverse"], [{"item_id": "2", "product_id": "2", "fields": {"qty": "5.0000"}}])

    def test_remote_relationship_and_option_drift_block(self):
        products, request, tables = self.remote_fixture()
        tables["catalog_product_super_link"] = []
        tables["catalog_product_super_attribute"] = []
        tables["eav_attribute_option_value"][0]["value"] = "Red"
        tables["catalog_eav_attribute"][0]["is_global"] = "0"
        codes = {r["code"] for r in remote_compare(products, {}, request, tables)["issues"]}
        self.assertEqual(codes, {"configurable_link_mismatch", "configurable_axis_mismatch", "variant_option_mismatch", "configurable_axis_scope_or_type"})

    def test_default_source_inverse_excludes_other_sources_and_skus(self):
        result = {"eav_scopes": {}, "stock_inverse": [], "bundle_diff": [], "entities": {"A": {}}}
        tables = {"inventory_source_item": [{"source_item_id": 1, "sku": "A", "source_code": "default", "quantity": "2"},
                                            {"source_item_id": 2, "sku": "A", "source_code": "warehouse", "quantity": "3"},
                                            {"source_item_id": 3, "sku": "OUTSIDE", "source_code": "default", "quantity": "4"}]}
        sql, counts = inverse_sql(result, tables, {"database": "lab", "prefix": ""})
        self.assertEqual(counts["inventory_source_item:restore_rows"], 1)
        self.assertNotIn("warehouse".encode().hex(), sql)
        self.assertNotIn("OUTSIDE".encode().hex(), sql)
        self.assertTrue(sql.endswith("ROLLBACK;\n"))

    def test_media_inverse_preserves_other_attributes_and_master_rows(self):
        tables = {"catalog_product_entity": [{"entity_id": "1"}], "eav_attribute": [{"attribute_code": "image", "attribute_id": "10"}],
                  "catalog_product_entity_media_gallery_value": [], "catalog_product_entity_media_gallery_value_to_entity": [],
                  "catalog_product_entity_varchar": [{"entity_id": "1", "attribute_id": "10", "store_id": "0", "value": "old.jpg"},
                                                     {"entity_id": "1", "attribute_id": "20", "store_id": "0", "value": "Other attribute"},
                                                     {"entity_id": "2", "attribute_id": "10", "store_id": "0", "value": "outside.jpg"}]}
        sql = media_inverse(tables, {"database": "lab", "prefix": ""})
        self.assertIn("old.jpg".encode().hex(), sql)
        self.assertNotIn("outside.jpg".encode().hex(), sql)
        self.assertNotIn("Other attribute".encode().hex(), sql)
        self.assertNotIn("DELETE FROM `lab`.`catalog_product_entity_media_gallery`", sql)
        self.assertTrue(sql.endswith("ROLLBACK;\n"))

    def test_snapshot_to_review_artifacts_and_tamper_rejection(self):
        products, request, tables = self.remote_fixture()
        for name in ("catalog_product_relation", "catalog_product_website", "catalog_category_product", "catalog_product_bundle_selection_price",
                     "catalog_product_entity_media_gallery", "catalog_product_entity_media_gallery_value", "catalog_product_entity_media_gallery_value_to_entity",
                     "store", "store_website"):
            tables[name] = []
        digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet, snapshot = root / "packet", root / "snapshot"
            packet.mkdir()
            snapshot.mkdir()
            (packet / "products.patch.csv").write_text("sku,price,qty\nP,100,5\nC,90,3\n")
            (packet / "bundles.csv").write_text("sku,bundle_values\n")
            (packet / "manifest.json").write_text(json.dumps({"outputs": {name: digest(packet / name) for name in ("products.patch.csv", "bundles.csv")}}))
            request.update(packet_sha256=digest(packet / "manifest.json"), expected_host="relevance.comtom.lab")
            request_path = root / "request.json"
            request_path.write_text(json.dumps(request))
            manifest = {"request_sha256": digest(request_path), "packet_sha256": request["packet_sha256"], "host": request["expected_host"],
                        "database": "lab", "prefix": "", "consistent_read_only": True, "inventory_source_item_absent": True,
                        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(), "tables": {}}
            for name, rows in tables.items():
                path = snapshot / (name + ".jsonl")
                path.write_text("".join(json.dumps(row) + "\n" for row in rows))
                manifest["tables"][name] = {"rows": len(rows), "sha256": digest(path)}
            (snapshot / "manifest.json").write_text(json.dumps(manifest))
            args = SimpleNamespace(snapshot=snapshot, request=request_path, packet=packet, output_dir=root / "review", max_age_hours=24)
            self.assertEqual(run_preflight(args), 0)
            report = json.loads((args.output_dir / "preflight.json").read_text())
            self.assertEqual(report["changed_product_count"], 1)
            self.assertEqual(report["changed_field_count"], 2)
            self.assertFalse(report["live_write_authorized"])
            self.assertEqual(report["status"], "review_required")
            for name in ("rollback.review.sql", "rollback-media.review.sql"):
                self.assertTrue((args.output_dir / name).read_text().endswith("ROLLBACK;\n"))
            (packet / "products.patch.csv").write_text("sku,price,qty\nP,1,1\n")
            with self.assertRaisesRegex(ValueError, "packet file hash"):
                run_preflight(args)
            (snapshot / "catalog_product_entity.jsonl").write_text("")
            with self.assertRaisesRegex(ValueError, "file hash"):
                load_snapshot(snapshot, request_path)

    def test_incomplete_final_audit_line_is_safe_but_middle_corruption_fails(self):
        self.assertEqual(complete_records(b'{"ok":1}\n{"partial"'), [{"ok": 1}])
        with self.assertRaises(ValueError):
            complete_records(b'{"broken"\n{"ok":1}\n')

    def test_repair_draft_does_not_resolve_conflicting_facts_or_approve(self):
        row = {"product_id": "1", "product_name": "Chair", "product_class": "Chairs", "product_features": "color:blue|color:red|certified:yes"}
        audit = {"path": "image.jpg", "image_sha256": "abc", "evidence_sha256": "def", "verdict": "fail", "confidence": .95,
                 "observed_product": "Brown chair", "issues": ["Color mismatch"]}
        result = draft(audit, row, {"child"})
        self.assertEqual(result["status"], "draft_requires_review")
        self.assertEqual(result["multiple_source_values_to_review"]["color"], ["blue", "red"])
        self.assertNotIn("certified", result["source_visual_facts"])

    def test_absent_storefront_observation_cannot_pass(self):
        result = storefront_compare({"cases": [{"sku": "A"}]}, {"cases": []})
        self.assertEqual(result["not_run"], 1)
        self.assertNotEqual(result["status"], "passed")

    def test_storefront_price_stock_and_media_failures_are_visible(self):
        case = {"sku": "A", "name": "Chair", "type": "simple", "in_stock": False, "effective_price": "10"}
        obs = {"name": "Chair", "http_status": 200, "in_stock": False, "console_errors": [], "exception_visible": False,
               "broken_images": 1, "product_images_loaded": 0, "visual_acceptance": "pending", "exact_sku_search_results": ["A"],
               "evidence_paths": ["screenshot.png"], "displayed_price": "11", "can_add_to_cart": True}
        errors = check_case(case, obs)
        self.assertIn("media_loading", errors)
        self.assertIn("simple_price", errors)
        self.assertIn("simple_stock", errors)


if __name__ == "__main__":
    unittest.main()
