#!/usr/bin/env python3
"""Validate frozen catalog artifacts and prepare exact release scope. No remote writes."""
import argparse
import csv
import hashlib
import itertools
import json
import logging
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

from prepare_catalog import sha256

EMPTY = "__EMPTY__VALUE__"
STOCK_FIELDS = {"qty", "is_in_stock", "manage_stock", "use_config_manage_stock", "backorders", "use_config_backorders", "min_qty", "use_config_min_qty"}
FIELD_MAP = {"product_online": "status", "bundle_price_type": "price_type", "bundle_sku_type": "sku_type",
             "bundle_price_view": "price_view", "bundle_weight_type": "weight_type", "bundle_shipment_type": "shipment_type",
             "tax_class_name": "tax_class_id"}
NON_EAV = {"sku", "store_view_code", "attribute_set_code", "product_type", "categories", "product_websites", "bundle_values", "out_of_stock_qty"} | STOCK_FIELDS


def csv_rows(path):
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"Missing/duplicate headers in {path.name}")
        rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError(f"Malformed CSV row in {path.name}")
    return rows


def json_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def index(rows, key="sku"):
    result = {}
    for row in rows:
        identity = row[key]
        if not identity or identity in result:
            raise ValueError(f"Missing/duplicate {key}: {identity}")
        result[identity] = row
    return result


def number(value):
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("Non-numeric value") from None
    if not result.is_finite():
        raise ValueError("Non-finite value")
    return result


def effective(row):
    return number(row["special_price"]) if row.get("special_price") not in (None, "", EMPTY) else number(row["price"])


def bundle_options(value):
    groups = {}
    for part in value.split("|"):
        pairs = [entry.split("=", 1) for entry in part.split(",")]
        if any(len(pair) != 2 for pair in pairs) or len({p[0] for p in pairs}) != len(pairs):
            raise ValueError("Malformed bundle selection")
        item = dict(pairs)
        if not {"name", "sku", "type", "required", "default", "default_qty", "price", "price_type", "can_change_qty"} <= item.keys():
            raise ValueError("Missing bundle selection field")
        groups.setdefault(item["name"], []).append(item)
    return groups


def validate(products, families, bundles, evidence, originals):
    errors, warnings = [], []
    def issue(target, code, detail, warning=False):
        (warnings if warning else errors).append({"sku": target, "code": code, "detail": detail})
    if set(products) != set(originals) or set(evidence) != set(products):
        issue("catalog", "identity_mismatch", "Patch, original and evidence SKU sets must match")
    expected_children, parent_skus, owned = set(), set(), {}
    for family in families:
        parent = family["parent"]["sku"]
        parent_skus.add(parent)
        axes = {axis["attribute"]: axis["values"] for axis in family["axes"]}
        actual = set()
        for child in family["variants"]:
            sku = child["sku"]
            expected_children.add(sku)
            if sku in owned:
                issue(sku, "multiple_parents", parent)
            owned[sku] = parent
            if set(child["options"]) != set(axes):
                issue(sku, "missing_axis", "Child option keys do not match family axes")
                continue
            key = tuple(child["options"][axis] for axis in axes)
            if key in actual:
                issue(parent, "duplicate_combination", str(key))
            actual.add(key)
            if child.get("product_type") != "simple" or child.get("visibility") != "Not Visible Individually":
                issue(sku, "child_identity", "Expected hidden simple child")
            for axis, value in child["options"].items():
                if value not in axes[axis] or str(child.get(axis, "")) != value:
                    issue(sku, "invalid_option", f"{axis}={value}")
        expected = set(itertools.product(*axes.values()))
        if actual != expected:
            issue(parent, "incomplete_combinations", f"Expected {len(expected)}, observed {len(actual)}")
        if parent not in products or any(c["sku"] not in products for c in family["variants"]):
            issue(parent, "missing_family_product", "Parent or child patch missing")
            continue
        row = products[parent]
        salable = any(products[c["sku"]]["is_in_stock"] == "1" for c in family["variants"])
        if row["is_in_stock"] != str(int(salable)) or row["manage_stock"] != "0" or row["use_config_manage_stock"] != "0":
            issue(parent, "parent_stock", "Parent stock must be derived from children with explicit stock management")
        if number(row["price"]) != min(number(products[c["sku"]]["price"]) for c in family["variants"]):
            issue(parent, "parent_price", "Parent reference price differs from minimum child base price")
    for sku, row in products.items():
        for name in ("name", "description", "short_description", "meta_title", "meta_description", "lab_brand", "lab_sale_unit", "lab_price_method", "lab_price_version"):
            if not row.get(name) or row[name] == EMPTY:
                issue(sku, "missing_attribute", name)
        if row.get("store_view_code") != "":
            issue(sku, "scope", "Only default/global patch scope is authorized")
        if len(row.get("name", "")) > 255 or len(row.get("meta_title", "")) > 255:
            issue(sku, "attribute_length", "Name/meta title exceeds 255 characters")
        try:
            if number(row["price"]) <= 0 or number(row["qty"]) < 0:
                issue(sku, "numeric_bounds", "Price must be positive and quantity nonnegative")
            if row["special_price"] != EMPTY and not 0 < number(row["special_price"]) < number(row["price"]):
                issue(sku, "special_price", "Special price must be positive and below base price")
            if row["manage_stock"] == "1" and row["is_in_stock"] == "1" and number(row["qty"]) <= 0:
                issue(sku, "stock_quantity", "Managed in-stock product has no quantity")
        except (ValueError, KeyError):
            issue(sku, "invalid_number", "Invalid price, special price or quantity")
        for field in ("is_in_stock", "manage_stock", "use_config_manage_stock", "backorders", "use_config_backorders"):
            if row.get(field) not in {"0", "1"}:
                issue(sku, "stock_flag", field)
        if row.get("backorders") != "0" or row.get("use_config_backorders") != "0":
            issue(sku, "backorders", "Synthetic stock must not enable inherited backorders")
        if sku in evidence and sku in originals:
            for key, original_key in (("input_type_preserved", "product_type"), ("input_url_key_preserved", "url_key")):
                if evidence[sku][key] != originals[sku][original_key]:
                    issue(sku, "identity_drift", key)
    option_count = selection_count = 0
    for sku, bundle in bundles.items():
        if sku in products or bundle.get("product_type") != "bundle":
            issue(sku, "bundle_identity", "Bundle must be separate from product updates")
        if any(bundle.get(field) != "dynamic" for field in ("bundle_price_type", "bundle_sku_type", "bundle_weight_type")):
            issue(sku, "bundle_dynamic", "Expected dynamic price, SKU and weight")
        if bundle.get("use_config_manage_stock") != "0":
            issue(sku, "inherited_bundle_stock", "manage_stock=0 is overridden by inherited configuration; runtime stock configuration must be verified", True)
        try:
            options = bundle_options(bundle["bundle_values"])
            if len(options) != 4:
                issue(sku, "option_count", "Expected four coherent required groups")
            used, possible = set(), []
            for name, selections in options.items():
                option_count += 1
                selection_count += len(selections)
                if len(selections) != 3 or sum(s["default"] == "1" for s in selections) != 1:
                    issue(sku, "selection_count", name)
                salable, defaults = [], []
                for selection in selections:
                    child = selection["sku"]
                    if child not in products or child in parent_skus or child in expected_children or child in used:
                        issue(sku, "bundle_relationship", child)
                        continue
                    used.add(child)
                    if originals.get(child, {}).get("product_type") != "simple":
                        issue(sku, "bundle_simple", child)
                    if selection["required"] != "1" or selection["type"] != "dropdown" or number(selection["default_qty"]) != 1 or number(selection["price"]) != 0:
                        issue(sku, "selection_rules", name)
                    available = products[child]["is_in_stock"] == "1"
                    salable.append(available)
                    if selection["default"] == "1":
                        defaults.append(available)
                possible.append(any(salable))
                if any(salable) and not all(defaults):
                    issue(sku, "unavailable_default", name)
            if bundle["is_in_stock"] != str(int(all(possible))):
                issue(sku, "bundle_stock", "Stock differs from required option availability")
        except (ValueError, KeyError):
            issue(sku, "bundle_syntax", "Cannot parse bundle selections")
    return {"counts": {"products": len(products), "parents": len(parent_skus), "children": len(expected_children),
                       "standalone_simple": len(products) - len(parent_skus) - len(expected_children),
                       "bundles": len(bundles), "options": option_count, "selections": selection_count,
                       "target_skus": len(set(products) | set(bundles))},
            "errors": errors, "warnings": warnings, "error_count": len(errors), "warning_count": len(warnings)}


def contracts(products, families, bundles, originals):
    cases = []
    for family in families:
        sku = family["parent"]["sku"]
        children = [{"sku": c["sku"], "options": c["options"], "base_price": products[c["sku"]]["price"],
                     "effective_price": str(effective(products[c["sku"]])), "in_stock": products[c["sku"]]["is_in_stock"] == "1"}
                    for c in family["variants"]]
        cases.append({"sku": sku, "type": "configurable", "url_key": originals[sku]["url_key"],
                      "name": products[sku]["name"], "axes": family["axes"], "children": children,
                      "expected_starting_price": str(min(number(c["effective_price"]) for c in children if c["in_stock"])) if any(c["in_stock"] for c in children) else None,
                      "in_stock": products[sku]["is_in_stock"] == "1"})
    for sku, bundle in bundles.items():
        options = bundle_options(bundle["bundle_values"])
        groups = [{"label": label, "selections": [{"sku": s["sku"], "default": s["default"] == "1", "quantity": s["default_qty"],
                   "effective_price": str(effective(products[s["sku"]])), "in_stock": products[s["sku"]]["is_in_stock"] == "1"} for s in rows]} for label, rows in options.items()]
        default_total = sum(effective(products[s["sku"]]) * number(s["default_qty"]) for rows in options.values() for s in rows if s["default"] == "1")
        cases.append({"sku": sku, "type": "bundle", "url_key": bundle["url_key"], "name": bundle["name"],
                      "options": groups, "expected_default_subtotal": str(default_total), "in_stock": bundle["is_in_stock"] == "1"})
    for scenario in ("in_stock", "low_stock", "out_of_stock"):
        row = next((r for sku, r in sorted(products.items()) if originals[sku]["product_type"] == "simple" and originals[sku].get("visibility") != "Not Visible Individually" and r["lab_stock_scenario"] == scenario), None)
        if row:
            cases.append({"sku": row["sku"], "type": "simple", "url_key": originals[row["sku"]]["url_key"], "name": row["name"],
                          "effective_price": str(effective(row)), "in_stock": row["is_in_stock"] == "1", "scenario": scenario})
    return {"status": "prepared_not_executed", "currency_assumption": "USD", "price_scope": "Before tax and any remote promotion or customer-group adjustment",
            "runtime_prerequisites": ["base URL", "URL suffix", "store code", "tax display mode", "currency", "customer group", "active price rules"], "cases": cases}


def build(args):
    packet = args.packet
    manifest = json.loads((packet / "manifest.json").read_text())
    for name, digest in manifest["outputs"].items():
        if Path(name).name != name or sha256(packet / name) != digest:
            raise ValueError("Frozen packet hash mismatch")
    for record in manifest["inputs"].values():
        if sha256(Path(record["path"])) != record["sha256"]:
            raise ValueError("Original source input changed")
    products = index(csv_rows(packet / "products.patch.csv"))
    bundles = index(csv_rows(packet / "bundles.csv"))
    evidence = index(json_rows(packet / "evidence.jsonl"))
    families = json_rows(Path(manifest["inputs"]["families"]["path"]))
    originals = index(csv_rows(Path(manifest["inputs"]["prepared"]["path"])))
    for family in families:
        originals[family["parent"]["sku"]] = family["parent"]
        for child in family["variants"]:
            if child["sku"] in originals:
                raise ValueError("Child SKU duplicates original")
            originals[child["sku"]] = child
    report = validate(products, families, bundles, evidence, originals)
    report.update(packet_sha256=sha256(packet / "manifest.json"), live_checked=False,
                  deployment_blockers=["Fresh remote snapshot and exact dry-run diff required", "Use the atomic --reconcile-bundles import path after reviewing exact removal counts",
                                       "Image generation/acceptance incomplete", "Remote importer validation and storefront execution pending"])
    args.output_dir.mkdir(parents=True, exist_ok=False)
    all_rows = [*products.values(), *bundles.values()]
    attributes = sorted({FIELD_MAP.get(field, field) for row in all_rows for field in row if field not in NON_EAV})
    axes = sorted({a["attribute"] for f in families for a in f["axes"]})
    request = {"version": 1, "expected_host": "relevance.comtom.lab", "packet_sha256": report["packet_sha256"],
               "skus": sorted(set(products) | set(bundles)), "bundle_skus": sorted(bundles), "attributes": sorted(set(attributes + axes + ["special_from_date", "special_to_date", "status", "visibility", "url_key", "image", "small_image", "thumbnail", "swatch_image"])),
               "counts": report["counts"], "intended_types": {**{sku: row["product_type"] for sku, row in originals.items()}, **{sku: "bundle" for sku in bundles}},
               "configurable_links": {f["parent"]["sku"]: sorted(c["sku"] for c in f["variants"]) for f in families},
               "configurable_axes": {f["parent"]["sku"]: [a["attribute"] for a in f["axes"]] for f in families},
               "variant_options": {c["sku"]: c["options"] for f in families for c in f["variants"]},
               "requested_actions": ["read-only snapshot", "local diff and rollback preparation"], "write_authorized": False}
    for name, data in (("validation.json", report), ("snapshot-request.json", request), ("storefront-cases.json", contracts(products, families, bundles, originals))):
        (args.output_dir / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    logging.info("Validation: %s; errors=%d warnings=%d", report["counts"], report["error_count"], report["warning_count"])
    return int(bool(report["error_count"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_suffix(".log"), level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        return build(args)
    except Exception:
        logging.exception("Readiness preparation failed; existing inputs unchanged")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
