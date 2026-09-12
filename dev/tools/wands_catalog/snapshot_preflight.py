#!/usr/bin/env python3
"""Compare a read-only remote snapshot and prepare review-only inverse SQL; never execute it."""
import argparse
import datetime as dt
import json
import logging
from collections import defaultdict
from pathlib import Path

from release_readiness import EMPTY, FIELD_MAP, NON_EAV, STOCK_FIELDS, bundle_options, csv_rows, index, json_rows, number
from prepare_catalog import sha256


def ident(value):
    if not value.replace("_", "").isalnum() or not value.isascii():
        raise ValueError("Invalid SQL identifier")
    return "`" + value + "`"


def literal(value):
    return "NULL" if value is None else "CONVERT(X'" + str(value).encode().hex() + "' USING utf8mb4)"


def normalized(value, backend):
    if value in (None, EMPTY):
        return None
    if backend in {"int", "decimal"}:
        return str(number(value).normalize())
    return str(value)


def desired_value(field, value):
    mappings = {"lab_price_synthetic": {"Yes": "1", "No": "0"}, "visibility": {"Not Visible Individually": "1", "Catalog": "2", "Search": "3", "Catalog, Search": "4"},
                "bundle_price_type": {"dynamic": "0", "fixed": "1"}, "bundle_sku_type": {"dynamic": "0", "fixed": "1"},
                "bundle_weight_type": {"dynamic": "0", "fixed": "1"}, "bundle_price_view": {"Price range": "0", "As low as": "1"},
                "bundle_shipment_type": {"together": "0", "separately": "1"}}
    return mappings.get(field, {}).get(value, value)


def load_snapshot(root, request_path, max_age_hours=24):
    manifest = json.loads((root / "manifest.json").read_text())
    request = json.loads(request_path.read_text())
    if manifest.get("request_sha256") != sha256(request_path) or manifest.get("packet_sha256") != request["packet_sha256"]:
        raise ValueError("Snapshot request/packet identity mismatch")
    if manifest.get("host") != request["expected_host"] or manifest.get("consistent_read_only") is not True:
        raise ValueError("Wrong destination or non-consistent snapshot")
    age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(manifest["captured_at"])).total_seconds() / 3600
    if age < -0.1 or age > max_age_hours:
        raise ValueError("Snapshot is stale or has a future timestamp")
    tables = {}
    for name, info in manifest["tables"].items():
        ident(name)
        path = root / (name + ".jsonl")
        if sha256(path) != info["sha256"]:
            raise ValueError("Snapshot file hash mismatch")
        tables[name] = json_rows(path)
        if len(tables[name]) != info["rows"]:
            raise ValueError("Snapshot row count mismatch")
    required = {"catalog_product_entity", "eav_attribute", "eav_entity_attribute", "catalog_eav_attribute", "cataloginventory_stock_item",
                "catalog_product_super_link", "catalog_product_super_attribute", "catalog_product_relation", "catalog_product_website", "catalog_category_product",
                "catalog_product_bundle_option", "catalog_product_bundle_option_value", "catalog_product_bundle_selection", "catalog_product_bundle_selection_price",
                "catalog_product_entity_media_gallery", "catalog_product_entity_media_gallery_value", "catalog_product_entity_media_gallery_value_to_entity",
                "store", "store_website", "eav_attribute_option", "eav_attribute_option_value"} | {"catalog_product_entity_" + t for t in ("varchar", "text", "decimal", "int", "datetime")}
    if not required <= tables.keys():
        raise ValueError("Incomplete snapshot tables")
    if "inventory_source_item" not in tables and manifest.get("inventory_source_item_absent") is not True:
        raise ValueError("Missing inventory coverage declaration")
    return manifest, request, tables


def compare(products, bundles, request, tables):
    entities = index(tables["catalog_product_entity"])
    by_id = {str(row["entity_id"]): row["sku"] for row in entities.values()}
    attributes = {r["attribute_code"]: r for r in tables["eav_attribute"]}
    assignments = {(str(r["attribute_set_id"]), str(r["attribute_id"])) for r in tables["eav_entity_attribute"]}
    issues, changes, eav_scopes, stock_inverse = [], [], defaultdict(set), []
    if set(entities) != set(request["skus"]):
        issues.append({"code": "remote_sku_mismatch", "missing": sorted(set(request["skus"]) - entities.keys()), "extra": sorted(entities.keys() - set(request["skus"]))})
    values = {}
    for kind in ("varchar", "text", "decimal", "int", "datetime"):
        for row in tables["catalog_product_entity_" + kind]:
            values[(str(row["entity_id"]), str(row["attribute_id"]), str(row["store_id"]))] = row["value"]
    stock = defaultdict(list)
    for row in tables["cataloginventory_stock_item"]:
        stock[str(row["product_id"])].append(row)
    for row in [*products.values(), *bundles.values()]:
        sku = row["sku"]
        if sku not in entities:
            continue
        entity = entities[sku]
        eid = str(entity["entity_id"])
        if entity["type_id"] != request["intended_types"][sku]:
            issues.append({"sku": sku, "code": "type_mismatch"})
        for field, raw in row.items():
            if raw == "" or field in NON_EAV or field in {"tax_class_name"}:
                continue
            code = FIELD_MAP.get(field, field)
            attribute = attributes.get(code)
            if not attribute:
                issues.append({"sku": sku, "code": "missing_attribute", "attribute": code})
                continue
            aid, kind = str(attribute["attribute_id"]), attribute["backend_type"]
            if (str(entity["attribute_set_id"]), aid) not in assignments:
                issues.append({"sku": sku, "code": "unassigned_attribute", "attribute": code})
            if kind not in {"varchar", "text", "decimal", "int", "datetime"}:
                issues.append({"sku": sku, "code": "unsupported_backend", "attribute": code})
                continue
            old = values.get((eid, aid, "0"))
            new = desired_value(field, raw)
            if normalized(old, kind) != normalized(new, kind):
                changes.append({"sku": sku, "kind": "attribute", "field": code, "before": old, "after": None if new == EMPTY else new})
                eav_scopes[("catalog_product_entity_" + kind, aid)].add(eid)
        intended_stock = {("min_qty" if k == "out_of_stock_qty" else k): v for k, v in row.items() if (k in STOCK_FIELDS or k == "out_of_stock_qty") and v != ""}
        if len(stock[eid]) != 1:
            issues.append({"sku": sku, "code": "ambiguous_stock_rows", "count": len(stock[eid])})
        else:
            before = stock[eid][0]
            different = {key: before.get(key) for key, value in intended_stock.items() if normalized(before.get(key), "decimal") != normalized(value, "decimal")}
            if different:
                changes.extend({"sku": sku, "kind": "stock", "field": key, "before": before.get(key), "after": intended_stock[key]} for key in different)
                stock_inverse.append({"item_id": before["item_id"], "product_id": eid, "fields": different})
    links = defaultdict(set)
    for row in tables["catalog_product_super_link"]:
        links[str(row["parent_id"])].add(by_id.get(str(row["product_id"]), "OUTSIDE_SCOPE:" + str(row["product_id"])))
    for sku, children in request["configurable_links"].items():
        if sku in entities and links[str(entities[sku]["entity_id"])] != set(children):
            issues.append({"sku": sku, "code": "configurable_link_mismatch"})
    super_attributes = defaultdict(set)
    for row in tables["catalog_product_super_attribute"]:
        super_attributes[str(row["product_id"])].add(str(row["attribute_id"]))
    global_scopes = {str(r["attribute_id"]): str(r["is_global"]) for r in tables["catalog_eav_attribute"]}
    for sku, axes in request.get("configurable_axes", {}).items():
        if sku not in entities:
            continue
        expected = {str(attributes[code]["attribute_id"]) for code in axes if code in attributes}
        if len(expected) != len(axes) or super_attributes[str(entities[sku]["entity_id"])] != expected:
            issues.append({"sku": sku, "code": "configurable_axis_mismatch"})
        for code in axes:
            attr = attributes.get(code)
            if attr and (attr["frontend_input"] != "select" or global_scopes.get(str(attr["attribute_id"])) != "1"):
                issues.append({"sku": sku, "code": "configurable_axis_scope_or_type", "attribute": code})
    labels = {str(r["option_id"]): r["value"] for r in tables["eav_attribute_option_value"] if str(r["store_id"]) == "0"}
    option_owner = {str(r["option_id"]): str(r["attribute_id"]) for r in tables["eav_attribute_option"]}
    for sku, options_expected in request.get("variant_options", {}).items():
        if sku not in entities:
            continue
        for code, label in options_expected.items():
            aid = str(attributes.get(code, {}).get("attribute_id", "missing"))
            oid = str(values.get((str(entities[sku]["entity_id"]), aid, "0"), "missing"))
            if labels.get(oid) != label or option_owner.get(oid) != aid:
                issues.append({"sku": sku, "code": "variant_option_mismatch", "attribute": code})
    for sku, row in products.items():
        if sku in entities and row.get("special_price") not in (None, "", EMPTY):
            for field in ("special_from_date", "special_to_date"):
                aid = str(attributes.get(field, {}).get("attribute_id", "missing"))
                if values.get((str(entities[sku]["entity_id"]), aid, "0")):
                    issues.append({"sku": sku, "code": "existing_special_date_requires_review", "field": field})
    bundle_diff = []
    options = {str(r["option_id"]): r for r in tables["catalog_product_bundle_option"]}
    titles = {str(r["option_id"]): r["title"] for r in tables["catalog_product_bundle_option_value"] if str(r["store_id"]) == "0"}
    for sku, row in bundles.items():
        if sku not in entities:
            continue
        eid = str(entities[sku]["entity_id"])
        old = []
        for selection in tables["catalog_product_bundle_selection"]:
            if str(selection["parent_product_id"]) == eid:
                oid = str(selection["option_id"])
                old.append({"option_id": oid, "title": titles.get(oid), "type": options.get(oid, {}).get("type"),
                            "sku": by_id.get(str(selection["product_id"]), "OUTSIDE_SCOPE:" + str(selection["product_id"])),
                            "default": str(selection["is_default"]), "qty": str(selection["selection_qty"])})
        target = bundle_options(row["bundle_values"])
        bundle_diff.append({"sku": sku, "entity_id": eid, "before": old, "after": target,
                            "before_option_count": sum(str(o["parent_id"]) == eid for o in options.values()),
                            "before_selection_count": len(old), "after_option_count": len(target), "after_selection_count": sum(map(len, target.values()))})
    return {"issues": issues, "changes": changes, "bundle_diff": bundle_diff, "eav_scopes": eav_scopes, "stock_inverse": stock_inverse, "entities": entities}


def inverse_sql(result, tables, manifest):
    qualify = lambda table: ident(manifest["database"]) + "." + ident(manifest["prefix"] + table)
    lines = ["-- REVIEW ONLY. Requires an approved maintenance window and verified post-import state.",
             "-- Do not disable foreign keys. This file deliberately ends with ROLLBACK.", "START TRANSACTION;"]
    counts = defaultdict(int)
    def insert(table, rows):
        for row in rows:
            lines.append("INSERT INTO " + qualify(table) + " (" + ",".join(ident(k) for k in row) + ") VALUES (" + ",".join(literal(v) for v in row.values()) + ");")
            counts[table + ":restore_rows"] += 1
    for (table, aid), ids in sorted(result["eav_scopes"].items()):
        for offset in range(0, len(ids), 400):
            group = sorted(ids)[offset:offset + 400]
            lines.append("DELETE FROM " + qualify(table) + " WHERE attribute_id=" + literal(aid) + " AND entity_id IN (" + ",".join(literal(i) for i in group) + ");")
        insert(table, [r for r in tables[table] if str(r["entity_id"]) in ids and str(r["attribute_id"]) == aid])
    for item in result["stock_inverse"]:
        lines.append("UPDATE " + qualify("cataloginventory_stock_item") + " SET " + ",".join(ident(k) + "=" + literal(v) for k, v in item["fields"].items())
                     + " WHERE item_id=" + literal(item["item_id"]) + " AND product_id=" + literal(item["product_id"]) + ";")
        counts["cataloginventory_stock_item:restore_rows"] += 1
    if "inventory_source_item" in tables:
        skus = sorted(result.get("entities", {}))
        for offset in range(0, len(skus), 400):
            lines.append("DELETE FROM " + qualify("inventory_source_item") + " WHERE source_code=" + literal("default")
                         + " AND sku IN (" + ",".join(literal(s) for s in skus[offset:offset + 400]) + ");")
        insert("inventory_source_item", [r for r in tables["inventory_source_item"] if r["sku"] in result.get("entities", {}) and r["source_code"] == "default"])
    ids = {r["entity_id"] for r in result["bundle_diff"]}
    restore_tables = [("catalog_product_bundle_option", "parent_id"), ("catalog_product_bundle_option_value", "parent_product_id"),
                      ("catalog_product_bundle_selection", "parent_product_id"), ("catalog_product_bundle_selection_price", "parent_product_id"),
                      ("catalog_product_relation", "parent_id")]
    if ids:
        for table, column in reversed(restore_tables):
            lines.append("DELETE FROM " + qualify(table) + " WHERE " + ident(column) + " IN (" + ",".join(literal(i) for i in sorted(ids)) + ");")
        for table, column in restore_tables:
            insert(table, [r for r in tables[table] if str(r[column]) in ids])
    lines.extend(["-- Inspect affected rows and verify the inverse in an isolated clone before authorizing COMMIT.", "ROLLBACK;"])
    return "\n".join(lines) + "\n", dict(counts)


def media_inverse(tables, manifest):
    ids = {str(r["entity_id"]) for r in tables["catalog_product_entity"]}
    qualify = lambda table: ident(manifest["database"]) + "." + ident(manifest["prefix"] + table)
    lines = ["-- REVIEW ONLY: media phase inverse. Old gallery master rows/files must still exist.",
             "-- Use immutable new upload paths. Never remove shared gallery master rows or old files.", "START TRANSACTION;"]
    scopes = ["catalog_product_entity_media_gallery_value", "catalog_product_entity_media_gallery_value_to_entity"]
    image_attributes = {str(r["attribute_id"]) for r in tables["eav_attribute"] if r["attribute_code"] in {"image", "small_image", "thumbnail", "swatch_image"}}
    for table in scopes + ["catalog_product_entity_varchar"]:
        filter_clause = ""
        if table == "catalog_product_entity_varchar":
            if not image_attributes:
                continue
            filter_clause = " AND attribute_id IN (" + ",".join(literal(a) for a in sorted(image_attributes)) + ")"
        for offset in range(0, len(ids), 400):
            group = sorted(ids)[offset:offset + 400]
            lines.append("DELETE FROM " + qualify(table) + " WHERE entity_id IN (" + ",".join(literal(i) for i in group) + ")" + filter_clause + ";")
        for row in tables[table]:
            if str(row["entity_id"]) in ids and (table != "catalog_product_entity_varchar" or str(row["attribute_id"]) in image_attributes):
                lines.append("INSERT INTO " + qualify(table) + " (" + ",".join(ident(k) for k in row) + ") VALUES (" + ",".join(literal(v) for v in row.values()) + ");")
    lines.extend(["-- New unreferenced files/master rows are retained for later separately approved cleanup.", "ROLLBACK;"])
    return "\n".join(lines) + "\n"


def run(args):
    manifest, request, tables = load_snapshot(args.snapshot, args.request, args.max_age_hours)
    if sha256(args.packet / "manifest.json") != request["packet_sha256"]:
        raise ValueError("Selected packet differs from approved snapshot request")
    packet_manifest = json.loads((args.packet / "manifest.json").read_text())
    for name, digest in packet_manifest["outputs"].items():
        if Path(name).name != name or sha256(args.packet / name) != digest:
            raise ValueError("Frozen packet file hash mismatch")
    result = compare(index(csv_rows(args.packet / "products.patch.csv")), index(csv_rows(args.packet / "bundles.csv")), request, tables)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    sql, counts = inverse_sql(result, tables, manifest)
    (args.output_dir / "rollback.review.sql").write_text(sql)
    (args.output_dir / "rollback-media.review.sql").write_text(media_inverse(tables, manifest))
    for name, rows in (("field-diff.jsonl", result["changes"]), ("bundle-diff.jsonl", result["bundle_diff"])):
        (args.output_dir / name).write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    report = {"status": "review_required", "live_write_authorized": False, "target_skus": len(request["skus"]),
              "found_skus": len(result["entities"]), "changed_field_count": len(result["changes"]),
              "changed_product_count": len({r["sku"] for r in result["changes"]}), "bundle_targets": len(result["bundle_diff"]),
              "old_bundle_options": sum(r["before_option_count"] for r in result["bundle_diff"]), "old_bundle_selections": sum(r["before_selection_count"] for r in result["bundle_diff"]),
              "new_bundle_options": sum(r["after_option_count"] for r in result["bundle_diff"]), "new_bundle_selections": sum(r["after_selection_count"] for r in result["bundle_diff"]),
              "snapshot_table_rows": {name: len(rows) for name, rows in tables.items()}, "inverse_restore_rows": counts,
              "issues": result["issues"], "snapshot_sha256": sha256(args.snapshot / "manifest.json"),
              "remaining_gates": ["Native importer validation in an isolated clone", "Explicit bundle-option reconciliation", "MSI source-item reconciliation and rollback rehearsal",
                                  "Tax class/category/website invariance verification", "Media DB associations and filesystem backup/rehearsal", "Full DB backup and approved maintenance window",
                                  "Runtime stock inheritance and active promotion/date checks", "Output visual acceptance and storefront execution"]}
    (args.output_dir / "preflight.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    logging.info("Preflight: %d fields changed; %d issues; inverse SQL is review-only", len(result["changes"]), len(result["issues"]))
    return int(bool(result["issues"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("packet", "request", "snapshot", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--max-age-hours", type=float, default=24)
    args = parser.parse_args()
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_suffix(".log"), level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        return run(args)
    except Exception:
        logging.exception("Preflight failed; no live changes performed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
