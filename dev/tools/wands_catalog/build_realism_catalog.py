#!/usr/bin/env python3
"""Prepare full-catalog realism changes, inverse artifacts and local image jobs. No remote writes."""
import argparse
import csv
import html
import json
import logging
import re
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from build_realism_review import collect_facts, description_sentences, read_csv, unique_index, variant_prices, write_json, write_jsonl
from build_merchandising_catalog import BUNDLE_CSV_FIELDS, bundle_csv_row
from prepare_catalog import sha256, stable_fraction
from realism_rules import VERSION, price, brand, stock, title, bundle_eligible, ANCHORS, COLLECTIONS

# Standalone room essentials deliberately avoid crib sleep, bed/bedding sizing,
# faucet installation and table/chair fit assumptions missing from WANDS.
BUNDLE_ROLES = {
    "Living Room": {"Seating": ("sofas", "loveseats"), "Coffee Table": ("coffee & cocktail tables",), "Accent Light": ("table lamps",), "Area Rug": ("area rugs",)},
    "Bedroom": {"Nightstand": ("nightstands",), "Bedside Light": ("table lamps",), "Storage": ("dressers & chests",), "Accent Pillow": ("accent pillows",)},
    "Dining": {"Serving Dish": ("serving dishes & platters",), "Bowl": ("dining bowls",), "Table Linen": ("dining linens",), "Candle Holder": ("candle holders",)},
    "Home Office": {"Desk": ("desks",), "Office Chair": ("office chairs",), "Bookcase": ("bookcases",), "Task Light": ("table lamps",)},
    "Patio": {"Outdoor Seating": ("patio lounge chairs", "patio sofas"), "Patio Table": ("patio tables",), "Planter": ("planters",), "Garden Accent": ("garden statues",)},
    "Bathroom": {"Storage": ("bathroom storage",), "Mirror": ("wall & accent mirrors",), "Bath Mat": ("bath rugs & mats",), "Bath Accessories": ("bath accessories",)},
    "Nursery & Kids": {"Kids Desk": ("kids desks",), "Kids Chair": ("kids chairs",), "Bookcase": ("kids bookcases",), "Wall Decor": ("kids wall décor",)},
    "Entryway": {"Console": ("sofa & console tables",), "Bench": ("benches",), "Mirror": ("wall & accent mirrors",), "Organization": ("coat racks and hooks",)},
    "Reading Nook": {"Chair": ("accent chairs",), "Floor Lamp": ("floor lamps",), "Bookcase": ("bookcases",), "Pillow": ("accent pillows",)},
    "Pet Corner": {"Pet Bed": ("dog beds & mats", "cat beds"), "Feeding": ("dog and cat bowls, feeders & accessories",), "Storage": ("hampers & baskets", "boxes, bins, baskets, & buckets"), "Toy Organizer": ("toy boxes and organizers",)},
}
PATCH_FIELDS = ["sku", "store_view_code", "name", "description", "short_description", "meta_title", "meta_description", "price",
                "special_price", "qty", "is_in_stock", "manage_stock", "use_config_manage_stock", "backorders", "use_config_backorders",
                "lab_price_method", "lab_price_version", "lab_price_synthetic", "lab_brand", "lab_stock_scenario", "lab_sale_unit"]
EMPTY = "__EMPTY__VALUE__"


def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def copy_for(name, facts, options=None):
    sentences = description_sentences(facts)
    text = " ".join(sentences)
    content = "<p>" + html.escape(name) + ".</p>"
    if text:
        content += "<p>" + html.escape(text) + "</p>"
    if options:
        content += "<p>" + html.escape("Selected options: " + "; ".join(f"{k}: {v}" for k, v in options.items())) + ".</p>"
    if facts:
        content += "<ul>" + "".join("<li>" + html.escape(f"{key}: {value}") + "</li>" for key, value in facts.items() if key != "Product type") + "</ul>"
    return content, (name + ". " + text)[:250]


def family_prices(pricing, family):
    pack_axis = next((a for a in family["axes"] if a["attribute"] == "wands_pack_size"), None)
    axes = [a for a in family["axes"] if a["attribute"] != "wands_pack_size"]
    variants = [{**v, "options": {k: value for k, value in v["options"].items() if k != "wands_pack_size"}} for v in family["variants"]]
    prices, flags = variant_prices(pricing["amount"], axes, variants)
    if flags:
        raise ValueError(f"Unresolved family price axes: {flags}")
    if pack_axis:
        quantities = {}
        for value in pack_axis["values"]:
            match = re.fullmatch(r"Pack of ([1-9]\d*)", value)
            if not match:
                raise ValueError("Unknown pack quantity")
            quantities[value] = int(match[1])
        baseline = pricing["sale_quantity"] if pricing["quantity_priced"] else min(quantities.values())
        prices = {v["sku"]: round(max(4.99, round(prices[v["sku"]] * quantities[v["options"]["wands_pack_size"]] / baseline) - .01), 2) for v in family["variants"]}
    return prices


def product_changes(source, original, family):
    axes = {a["attribute"] for a in family["axes"]} if family else set()
    facts, withheld = collect_facts(source, axes)
    name = title({**source, "product_name": original["name"]}, axes, facts)
    pricing, branding = price(source), brand(source)
    if "composition_conflict_withheld" in pricing["flags"]:
        name = re.sub(r"\b\d+[ -]+pieces?\b|\bset of \d+\b", "", name, flags=re.I)
        name = " ".join(name.split())
        facts.pop("Pieces included", None)
        facts.pop("Included pieces", None)
    children = family["variants"] if family else []
    prices = family_prices(pricing, family) if family else {}
    rows, evidence = [], []
    for current in [original, *children]:
        is_parent = bool(family) and current["sku"] == original["sku"]
        options = current.get("options", {})
        child_name = name + (" - " + ", ".join(options.values()) if options else "")
        description, short = copy_for(child_name, facts, options)
        if is_parent:
            description += "<p>" + html.escape("Available options: " + "; ".join(a["label"] + ": " + ", ".join(a["values"]) for a in family["axes"])) + ".</p>"
        inventory = stock(current["sku"])
        amount = min(prices.values()) if is_parent else prices.get(current["sku"], pricing["amount"])
        # An ambiguous sale quantity is a genuine data exception, not a license to
        # price a ten-pack as one unit. Keep the original price pending resolution.
        if "sale_quantity_conflict" in pricing["flags"]:
            amount = float(current["price"])
        patch = {"sku": current["sku"], "store_view_code": "", "name": child_name,
                 "description": description, "short_description": short, "meta_title": child_name[:255],
                 "meta_description": short, "price": f"{amount:.2f}",
                 **{k: inventory[k] for k in ("qty", "is_in_stock", "manage_stock", "use_config_manage_stock", "backorders", "use_config_backorders")},
                 "special_price": f"{round(amount * .85, 2):.2f}" if inventory["clearance"] and not is_parent else EMPTY,
                 "lab_price_method": pricing["basis"] + "-synthetic-unit-material",
                 "lab_price_version": VERSION, "lab_price_synthetic": "Yes", "lab_brand": branding["collection"],
                 "lab_stock_scenario": inventory["scenario"], "lab_sale_unit": pricing["sale_unit"]}
        if is_parent:
            salable = any(stock(child["sku"])["is_in_stock"] == "1" for child in children)
            patch.update(qty="0", is_in_stock=str(int(salable)), manage_stock="0", use_config_manage_stock="0",
                         lab_stock_scenario="derived from children")
        rows.append(patch)
        evidence.append({"sku": current["sku"], "source_product_id": source["product_id"], "source_class": source["product_class"],
                         "pricing": pricing, "branding": branding, "specifications": facts,
                         "withheld_features": withheld, "synthetic_options": options,
                         "input_url_key_preserved": current["url_key"], "input_type_preserved": current["product_type"]})
    return rows, evidence


def rebuild_bundles(originals, source, prepared, families, patches):
    result, audit = [], []
    pools = {}
    for theme, roles in BUNDLE_ROLES.items():
        for role, allowed in roles.items():
            candidates = [r for pid, r in source.items() if pid not in families and bundle_eligible(r, theme, role, allowed)
                          and "sale_quantity_conflict" not in price(r)["flags"]]
            if not candidates:
                raise ValueError(f"No coherent assortment for {theme}/{role}")
            midpoint = median(float(patches[prepared[r["product_id"]]["sku"]]["price"]) for r in candidates)
            pools[theme, role] = [r for r in candidates if midpoint / 1.6 <= float(patches[prepared[r["product_id"]]["sku"]]["price"]) <= midpoint * 1.6]
    for index, original in enumerate(originals):
        theme = original["categories"].rsplit("/", 1)[-1]
        roles, options, used = BUNDLE_ROLES[theme], [], set()
        for role in roles:
            candidates = sorted(pools[theme, role], key=lambda r: stable_fraction(r["product_id"], original["sku"] + ":" + role))
            picks = [r for r in candidates if r["product_id"] not in used][:3]
            if not picks:
                raise ValueError(f"No distinct selection in {original['sku']}/{role}")
            picks.sort(key=lambda r: patches[prepared[r["product_id"]]["sku"]]["is_in_stock"] != "1")
            selections = []
            for row in picks:
                used.add(row["product_id"])
                patch = patches[prepared[row["product_id"]]["sku"]]
                selections.append({"sku": patch["sku"], "name": patch["name"], "price": patch["price"],
                                   "effective_price": patch["special_price"] if patch["special_price"] != EMPTY else patch["price"],
                                   "source_product_id": row["product_id"]})
            options.append({"name": role, "required": True, "type": "dropdown", "selections": selections})
        display_theme = "Kids Study" if theme == "Nursery & Kids" else "Dining Tabletop" if theme == "Dining" else theme
        name = f"{display_theme} Essentials Collection {index % 5 + 1:02d}"
        description = "<p>" + html.escape(name) + " brings together " + html.escape(", ".join(r.lower() for r in roles)) + ".</p><p>Choose one item from each group. The price is the sum of your selected components. Review each item's dimensions and care details when planning your space.</p>"
        bundle = {"sku": original["sku"], "name": name, "theme": theme, "palette": "source component finishes",
                  "description": description, "short_description": name + ": " + ", ".join(roles) + ".",
                  "url_key": original["url_key"], "options": options}
        values = bundle_csv_row(bundle)
        values["categories"] = original["categories"]
        values["is_in_stock"] = str(int(all(any(patches[s["sku"]]["is_in_stock"] == "1" for s in o["selections"]) for o in options)))
        values["lab_price_version"] = VERSION
        result.append(values)
        audit.append({**bundle, "rationale": "Standalone room essentials; no unverified paired fit, infant sleep or installation claims",
                      "default_price": round(sum(float(o["selections"][0]["effective_price"]) for o in options), 2),
                      "min_price": round(sum(min(float(s["effective_price"]) for s in o["selections"]) for o in options), 2),
                      "max_price": round(sum(max(float(s["effective_price"]) for s in o["selections"]) for o in options), 2),
                      "price_scope": "Synthetic component prices including generated clearance; excludes tax and any store-level promotions",
                      "before": original})
    return result, audit


def image_jobs(families, patches, bundles, media_dir):
    jobs = []
    for family in families.values():
        parent = family["parent"]["sku"]
        reference = next((media_dir / (parent + ext) for ext in (".jpg", ".webp", ".png") if (media_dir / (parent + ext)).is_file()), None)
        if reference is None:
            raise ValueError(f"Missing family reference for {parent}")
        reference_hash = sha256(reference)
        for variant in family["variants"]:
            sku = variant["sku"]
            changes = ", ".join(a["label"] + ": " + variant["options"][a["attribute"]] for a in family["axes"])
            jobs.append({"sku": sku, "output_file": sku + "-REALISM.jpg", "seed": int(stable_fraction(sku, VERSION) * 2**31),
                         "reference_images": [{"path": str(reference.resolve()), "sha256": reference_hash}],
                         "prompt": "Edit this product photograph into the following catalog variant: " + patches[sku]["name"] + ". Change only these option details: " + changes + ". Preserve the underlying product design, pattern, camera, background and lighting. Match the specified material and color. For a piece or light count change, show exactly that count. No labels, logos or added accessories.",
                         "acceptance": "Compare against reference; verify design, option color/material, proportions and component count before publishing"})
    for bundle in bundles:
        refs = []
        for option in bundle["options"]:
            sku = option["selections"][0]["sku"]
            reference = next((media_dir / (sku + ext) for ext in (".jpg", ".webp", ".png") if (media_dir / (sku + ext)).is_file()), None)
            if reference is None:
                raise ValueError(f"Missing bundle component reference: {sku}")
            refs.append({"path": str(reference.resolve()), "sha256": sha256(reference), "role": option["name"]})
        jobs.append({"sku": bundle["sku"], "output_file": bundle["sku"] + "-REALISM.jpg", "seed": int(stable_fraction(bundle["sku"], VERSION) * 2**31),
                     "reference_images": refs,
                     "prompt": "Create a studio catalog assortment photograph showing exactly the products in the reference images together. Collection: " + bundle["name"] + ". References in order: " + ", ".join(r["role"] for r in refs) + ". Preserve each product's actual shape, color, pattern and construction. Show every referenced item once on a warm white seamless background. No additional products, no labels, no logos. This depicts only the default selections, not every alternative.",
                     "acceptance": "Every default component appears once and matches its reference; no extras"})
    return jobs


def validate(patches, originals, bundles, family_count):
    if set(patches) != set(originals):
        raise ValueError("Product SKU set changed")
    for sku, row in patches.items():
        if not row["name"].strip() or not row["description"] or float(row["price"]) <= 0:
            raise ValueError(f"Invalid required content: {sku}")
        if len(row["name"]) > 255 or len(row["meta_title"]) > 255:
            raise ValueError(f"Title exceeds Magento limit: {sku}")
        if row["is_in_stock"] == "1" and row["manage_stock"] == "1" and int(row["qty"]) <= 0:
            raise ValueError(f"Invalid stock: {sku}")
        if row["special_price"] != EMPTY and float(row["special_price"]) >= float(row["price"]):
            raise ValueError(f"Invalid clearance price: {sku}")
    for bundle in bundles:
        for option in bundle["options"]:
            for selection in option["selections"]:
                if selection["sku"] not in patches or originals[selection["sku"]]["product_type"] != "simple":
                    raise ValueError("Bundle selection must reference an existing simple product")
    return {"sku_identity_preserved": True, "positive_prices": True, "valid_stock": True,
            "bundle_simple_references": True, "configurable_families": family_count,
            "live_import_tested": False, "images_visually_accepted": False}


def build(args):
    paths = {"source": args.source_products, "prepared": args.prepared_products,
             "families": args.merchandising_dir / "configurable-families.jsonl", "bundles": args.merchandising_dir / "bundles.csv"}
    fingerprints = {k: {"path": str(v.resolve()), "sha256": sha256(v)} for k, v in paths.items()}
    source = unique_index(read_csv(paths["source"], "\t"), "product_id")
    prepared = unique_index(read_csv(paths["prepared"]), "wands_product_id")
    with paths["families"].open() as stream:
        families = unique_index([json.loads(line) for line in stream if line.strip()], "source_product_id")
    original_bundles = read_csv(paths["bundles"])
    if set(source) != set(prepared) or not set(families) <= source.keys():
        raise ValueError("Input identities do not match")
    target = args.output_dir.resolve()
    if target.exists():
        raise ValueError("Output already exists; preserve it and choose another directory")
    target.parent.mkdir(parents=True, exist_ok=True)
    originals, patches, evidence = {}, {}, []
    for pid, row in sorted(source.items(), key=lambda pair: int(pair[0])):
        family = families.get(pid)
        current = family["parent"] if family else prepared[pid]
        changed, proof = product_changes(row, current, family)
        for item in [current, *(family["variants"] if family else [])]:
            if item["sku"] in originals:
                raise ValueError("Duplicate input SKU")
            originals[item["sku"]] = item
        patches.update((r["sku"], r) for r in changed)
        evidence.extend(proof)
    logging.info("Enriched %s products; rebuilding bundle assortments", len(patches))
    bundle_rows, bundle_proof = rebuild_bundles(original_bundles, source, prepared, families, patches)
    validation = validate(patches, originals, bundle_proof, len(families))
    jobs = image_jobs(families, patches, bundle_proof, args.media_dir)
    exceptions = [e for e in evidence if "sale_quantity_conflict" in e["pricing"]["flags"]]
    with tempfile.TemporaryDirectory(prefix=".realism-full-", dir=target.parent) as temp:
        stage = Path(temp) / "catalog"
        stage.mkdir()
        write_csv(stage / "products.patch.csv", patches.values(), PATCH_FIELDS)
        # Artifact rollback is not a substitute for the required fresh remote snapshot.
        inverse = [{field: row.get(field, EMPTY) or EMPTY for field in PATCH_FIELDS} for row in originals.values()]
        for row in inverse:
            row["store_view_code"] = ""
        write_csv(stage / "rollback.local-artifacts.csv", inverse, PATCH_FIELDS)
        write_csv(stage / "bundles.csv", bundle_rows, BUNDLE_CSV_FIELDS)
        write_csv(stage / "rollback.bundles.local-artifacts.csv", original_bundles, BUNDLE_CSV_FIELDS)
        write_jsonl(stage / "evidence.jsonl", evidence)
        write_jsonl(stage / "exceptions.jsonl", exceptions)
        write_jsonl(stage / "bundles.jsonl", bundle_proof)
        write_jsonl(stage / "image-jobs.jsonl", jobs)
        write_json(stage / "rules.json", {"version": VERSION, "anchors": ANCHORS, "collections": COLLECTIONS, "bundle_roles": BUNDLE_ROLES,
                                        "source_sha256": sha256(Path(__file__)), "rules_sha256": sha256(Path(__file__).with_name("realism_rules.py"))})
        write_json(stage / "validation.json", validation)
        if any(sha256(paths[k]) != record["sha256"] for k, record in fingerprints.items()):
            raise ValueError("Input changed during build")
        summary = {"version": VERSION, "source_products": len(source), "product_updates": len(patches),
                   "configurable_families": len(families), "bundle_updates": len(bundle_rows),
                   "bundle_selections": sum(len(o["selections"]) for b in bundle_proof for o in b["options"]),
                   "image_jobs": len(jobs), "images_generated": 0, "unchanged_price_quantity_exceptions": len(exceptions),
                   "fictional_collection_counts": dict(Counter(p["lab_brand"] for p in patches.values())),
                   "stock_counts": dict(Counter(p["lab_stock_scenario"] for p in patches.values())),
                   "price_basis_counts": dict(Counter(e["pricing"]["basis"] for e in evidence)),
                   "live_writes": 0, "deployment_gate": "Fresh remote snapshot, dry run, approved exact scope and rollback before import",
                   "schema_prerequisite": "RocketWeb_LabCatalog AddRealismAttributes patch; no manufacturer replacement",
                   "inputs": fingerprints, "outputs": {p.name: sha256(p) for p in sorted(stage.iterdir())}}
        write_json(stage / "manifest.json", summary)
        stage.rename(target)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source-products", "prepared-products", "merchandising-dir", "media-dir", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    log = args.output_dir.with_name(args.output_dir.name + ".log")
    log.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=log, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        logging.info("Starting full-catalog build")
        manifest = build(args)
        logging.info("Completed: %s", json.dumps({k: v for k, v in manifest.items() if k not in {"inputs", "outputs"}}))
        if args.json:
            print(json.dumps(manifest, indent=2))
        return 0
    except Exception:
        logging.exception("Build failed without publishing outputs")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
