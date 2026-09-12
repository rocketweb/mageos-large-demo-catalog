#!/usr/bin/env python3
"""Check captured storefront observations against release cases. Does not browse or submit orders."""
import argparse
import json
import logging
from decimal import Decimal
from pathlib import Path


def close(actual, expected):
    try:
        a, b = Decimal(str(actual)), Decimal(str(expected))
        return a.is_finite() and b.is_finite() and abs(a - b) <= Decimal("0.01")
    except Exception:
        return False


def check_case(case, observed):
    errors = []
    def require(condition, code):
        if not condition:
            errors.append(code)
    require(observed.get("http_status") == 200, "http_status")
    require(observed.get("name") == case["name"], "product_name")
    require(observed.get("in_stock") is case["in_stock"], "availability")
    require(observed.get("console_errors") == [], "console_errors")
    require(observed.get("exception_visible") is False, "storefront_exception")
    require(observed.get("broken_images") == 0 and observed.get("product_images_loaded", 0) > 0, "media_loading")
    require(observed.get("visual_acceptance") == "accepted", "visual_review")
    require(case["sku"] in observed.get("exact_sku_search_results", []), "exact_sku_search")
    require(bool(observed.get("evidence_paths")), "missing_evidence")
    if case["type"] == "configurable":
        require(set(observed.get("axis_codes", [])) == {a["attribute"] for a in case["axes"]}, "configurable_axes")
        actual = {row["sku"]: row for row in observed.get("variants", [])}
        require(set(actual) == {c["sku"] for c in case["children"]}, "variant_coverage")
        for child in case["children"]:
            row = actual.get(child["sku"], {})
            require(row.get("options") == child["options"], "variant_options:" + child["sku"])
            require(row.get("can_add_to_cart") is child["in_stock"], "variant_stock:" + child["sku"])
            if child["in_stock"]:
                require(close(row.get("displayed_price"), child["effective_price"]), "variant_price:" + child["sku"])
                require(row.get("image_matches_options") is True, "variant_image:" + child["sku"])
        if case["in_stock"]:
            require(close(observed.get("starting_price"), case["expected_starting_price"]), "configurable_starting_price")
    elif case["type"] == "bundle":
        groups = {g["label"]: g for g in observed.get("options", [])}
        require(set(groups) == {g["label"] for g in case["options"]}, "bundle_option_labels")
        for expected in case["options"]:
            group = groups.get(expected["label"], {})
            choices = {c["sku"]: c for c in group.get("selections", [])}
            permitted = {s["sku"] for s in expected["selections"]}
            salable = {s["sku"] for s in expected["selections"] if s["in_stock"]}
            require(salable <= set(choices) <= permitted, "bundle_selection_set:" + expected["label"])
            require(group.get("required") is True, "bundle_required:" + expected["label"])
            for selection in expected["selections"]:
                if selection["sku"] in choices:
                    current = choices[selection["sku"]]
                    require(current.get("enabled") is selection["in_stock"], "bundle_stock:" + selection["sku"])
                    if selection["in_stock"]:
                        require(close(current.get("displayed_price"), selection["effective_price"]), "bundle_price:" + selection["sku"])
        if case["in_stock"]:
            require(close(observed.get("default_subtotal"), case["expected_default_subtotal"]), "bundle_default_total")
            require(observed.get("alternative_total_verified") is True, "bundle_alternative_total")
    else:
        require(close(observed.get("displayed_price"), case["effective_price"]), "simple_price")
        require(observed.get("can_add_to_cart") is case["in_stock"], "simple_stock")
    return errors


def compare(cases, observations):
    records = {}
    for row in observations.get("cases", []):
        if row["sku"] in records:
            raise ValueError("Duplicate storefront observation")
        records[row["sku"]] = row
    expected = {c["sku"] for c in cases["cases"]}
    if set(records) - expected:
        raise ValueError("Observation SKU is outside the case manifest")
    context = observations.get("context", {})
    context_ready = (context.get("currency") == "USD" and context.get("prices_exclude_tax") is True
                     and context.get("additional_price_rules") is False and context.get("customer_group") == "NOT LOGGED IN"
                     and context.get("store") and context.get("base_url") and context.get("captured_at"))
    results = []
    for case in cases["cases"]:
        row = records.get(case["sku"])
        if not row:
            results.append({"sku": case["sku"], "status": "not_run", "errors": []})
        elif not context_ready:
            results.append({"sku": case["sku"], "status": "blocked_context", "errors": ["Resolve store, tax, currency, customer group and promotion assumptions before price comparison"]})
        else:
            errors = check_case(case, row)
            results.append({"sku": case["sku"], "status": "failed" if errors else "passed", "errors": errors})
    return {"status": "passed" if all(r["status"] == "passed" for r in results) and results else "incomplete_or_failed",
            "results": results, "passed": sum(r["status"] == "passed" for r in results),
            "not_run": sum(r["status"] == "not_run" for r in results), "total_cases": len(results)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.output.with_suffix(".log"), level=logging.INFO)
    try:
        report = compare(json.loads(args.cases.read_text()), json.loads(args.observations.read_text()))
        with args.output.open("x") as stream:
            json.dump(report, stream, indent=2)
        logging.info("Storefront observations: %d/%d passed", report["passed"], report["total_cases"])
        return int(report["status"] != "passed")
    except Exception:
        logging.exception("Observation check failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
