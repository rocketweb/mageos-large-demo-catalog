#!/usr/bin/env python3
"""Build a deterministic, review-only realism sample. Never import into Magento."""
from __future__ import annotations

import argparse
import csv
import html
import json
import logging
import math
import re
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from build_merchandising_catalog import BUNDLE_DEFINITIONS
from prepare_catalog import department, normalized_text, parse_features, sha256, stable_fraction

VERSION = "wands-realism-review-v1"
DEPARTMENTS = ["Furniture", "Kitchen & Tabletop", "Home Improvement", "Décor & Pillows",
               "Outdoor", "Storage & Organization", "Bed & Bath", "Baby & Kids", "Lighting", "Rugs"]

# Explicit synthetic USD anchors, NOT researched retail prices. Exact classes only.
# Each tuple is (singular merchandising noun, base price). No title keyword pricing.
PROFILES = {
    "Office Chairs": ("Office Chair", 220), "Accent Chairs": ("Accent Chair", 300),
    "Beds": ("Bed", 550), "Coffee & Cocktail Tables": ("Coffee Table", 250),
    "Bar Stools": ("Bar Stool", 140), "End Tables": ("End Table", 120),
    "Desks": ("Desk", 280), "Dining Tables": ("Dining Table", 600),
    "Slow Cookers": ("Slow Cooker", 65), "Plates & Saucers": ("Plate / Saucer", 30),
    "Food Storage & Dispensers": ("Food Storage Container", 25),
    "Serving Dishes & Platters": ("Serving Dish", 40), "Bread & Loaf Pans": ("Loaf Pan", 22),
    "Dining Bowls": ("Dining Bowl", 25),
    "Floor & Wall Tile": ("Floor / Wall Tile", 65), "Vanities": ("Bathroom Vanity", 750),
    "Cabinet and Drawer Pulls": ("Cabinet Pull", 12), "Cabinet and Drawer Knobs": ("Cabinet Knob", 8),
    "Bathroom Sink Faucets": ("Bathroom Sink Faucet", 160), "Wall Plates": ("Wall Plate", 15),
    "Accent Pillows": ("Accent Pillow", 35), "Wall Art": ("Wall Art", 80),
    "Curtains & Drapes": ("Curtain Panel", 55), "Wall Décor": ("Wall Decor", 55),
    "Wall & Accent Mirrors": ("Wall Mirror", 140), "Decorative Objects": ("Decorative Accent", 35),
    "Outdoor Conversation Sets": ("Outdoor Conversation Set", 950), "Patio Sofas": ("Patio Sofa", 700),
    "Garden Statues": ("Garden Statue", 80), "Planters": ("Planter", 55),
    "Patio Lounge Chairs": ("Patio Lounge Chair", 240),
    "Bathroom Storage": ("Bathroom Storage", 100), "Wall Mounted Shelves": ("Wall Shelf", 55),
    "Shoe Storage": ("Shoe Storage", 90), "Hampers & Baskets": ("Hamper / Basket", 45),
    "Boxes, Bins, Baskets, & Buckets": ("Storage Container", 30),
    "Bedding Sets": ("Bedding Set", 100), "Sheets And Sheet Sets": ("Sheet Set", 65),
    "Bath Accessories": ("Bath Accessory", 25),
    "Shower Curtain Hooks and Accessories": ("Shower Curtain Accessory", 15),
    "Shower Curtains": ("Shower Curtain", 30),
    "Kids Chairs": ("Kids Chair", 95), "Kids Beds": ("Kids Bed", 380),
    "Crib Bedding Sets": ("Crib Bedding Set", 75), "Kids Wall Décor": ("Kids Wall Decor", 35),
    "Kids Desks": ("Kids Desk", 160),
    "Chandeliers": ("Chandelier", 300), "Table Lamps": ("Table Lamp", 85),
    "Vanity Lighting": ("Vanity Light", 130), "Light Bulbs": ("Light Bulb", 15),
    "Wall Sconces": ("Wall Sconce", 100), "Area Rugs": ("Area Rug", 180),
    "Kitchen Mats": ("Kitchen Mat", 35), "Doormats": ("Doormat", 25),
    "Rug Pads": ("Rug Pad", 40), "Stair Treads": ("Stair Tread", 35),
}

FACT_KEYS = {
    "primarymaterial": "Material", "material": "Material", "framematerial": "Frame material",
    "upholsterymaterial": "Upholstery", "woodspecies": "Wood species", "color": "Color",
    "finish": "Finish", "shape": "Shape", "pattern": "Pattern", "rugshape": "Shape",
    "pileheight": "Pile height", "overallwidthsidetoside": "Width", "width": "Width",
    "overallheighttoptobottom": "Height", "height": "Height",
    "overalldepthfronttoback": "Depth", "depth": "Depth", "length": "Length",
    "overalllengthendtoend": "Length", "assemblyrequired": "Assembly required",
    "numberofdrawers": "Drawers", "numberofshelves": "Shelves", "numberofpiecesincluded": "Pieces included",
    "piecesincluded": "Included pieces", "reversible": "Reversible", "productcare": "Care",
    "producttype": "Product type", "bulbbase": "Bulb base", "bulbtype": "Bulb type",
    "seatupholsterymaterial": "Seat upholstery", "backupholsterymaterial": "Back upholstery",
    "swivel": "Swivel", "armed": "Arms", "casters": "Casters", "adjustableseatheight": "Adjustable seat height",
    "seatcolor": "Seat color", "backcolor": "Back color", "framecolor": "Frame color",
}
DIMENSIONS = {"Width", "Height", "Depth", "Length", "Pile height"}
MATERIALS = {"Material", "Frame material", "Upholstery", "Wood species", "Seat upholstery", "Back upholstery"}
CLAIM_PATTERN = re.compile(r"certif|warrant|antimicrob|antibacter|non.?toxic|fire.?resist|flame.?retard|hypoallergen|safe for|lead.?free", re.I)


def collect_facts(row, axes=frozenset()):
    grouped = defaultdict(list)
    for key, values in parse_features(row.get("product_features", "")).items():
        if key in FACT_KEYS:
            grouped[FACT_KEYS[key]].extend(values)
    facts, flags = {}, []
    for label, values in sorted(grouped.items()):
        unique = {v.casefold(): v for v in values}
        if len(unique) != 1:
            flags.append(f"conflict: {label}: {' / '.join(sorted(unique))}")
            continue
        value = next(iter(unique.values()))
        if not value.strip() or value.casefold() in {"n/a", "unknown", "null"}:
            continue
        if label in DIMENSIONS and not re.search(r"\b(?:in|inch|inches|ft|feet|cm|mm|m)\b|[\"′″']", value, re.I):
            flags.append(f"missing unit: {label}: {value}")
            continue
        varied = ((label in {"Color", "Seat color", "Back color", "Frame color"} and "color" in axes) or
                  (label == "Finish" and "wands_finish" in axes) or
                  (label in MATERIALS and "wands_material" in axes) or
                  (label in DIMENSIONS and axes.intersection({"wands_size", "wands_length", "wands_seat_height"})) or
                  (label in {"Pieces included", "Included pieces"} and axes.intersection({"wands_piece_count", "wands_pack_size"})))
        if varied or CLAIM_PATTERN.search(value):
            flags.append(f"withheld for variant or claim review: {label}: {value}")
            continue
        facts[label] = value
    return facts, flags


def clean_title(row, facts):
    """Retain useful source wording. Only compact long, marketing-heavy titles."""
    original = normalized_text(row["product_name"])
    title = re.split(r"\bfor (?:home|girls|women|living room)\b", original, maxsplit=1, flags=re.I)[0].strip(" ,")
    if len(original) > 100 and row["product_class"] == "Office Chairs":
        title = (facts.get("Seat upholstery", facts.get("Upholstery", "")) + " " +
                 ("Swivel " if facts.get("Swivel", "").lower() == "yes" else "") + "Desk Chair").strip().title()
        if facts.get("Arms", "").lower() == "yes":
            title += " with Arms"
        return title
    if len(title) > 100:
        title = title.split(",", 1)[0]
    if len(title) > 100:
        noun = PROFILES.get(row["product_class"], (row["product_class"], 0))[0]
        match = re.search(re.escape(noun), title, re.I)
        title = title[:match.end()] if match else " ".join(title.split()[:12])
    return title.title()


def price_proposal(row):
    profile = PROFILES.get(row["product_class"])
    if profile is None:
        return {"amount": None, "profile": None, "synthetic": True, "hold": "No exact class rule"}
    base = profile[1]
    # A small reproducible spread gives visual variation without pretending to know cost.
    amount = round(base * (0.9 + stable_fraction(row["product_id"], VERSION + ":price") * .2)) - .01
    return {"amount": round(amount, 2), "profile": row["product_class"], "anchor": base,
            "currency": "USD", "synthetic": True, "method": "exact-class-anchor-plus-10pct-spread",
            "hold": "Validate sale unit, pack count, dimensions and material tier before approval"}


def size_value(value):
    named = {"toddler": 0, "twin": 1, "twin xl": 1.2, "full": 2, "queen": 3, "king": 4,
             "small": 1, "medium": 2, "large": 3, "extra large": 4,
             "twin over twin": 2, "twin over full": 3, "full over full": 4, "twin xl over queen": 4.2}
    if value.lower() in named:
        return named[value.lower()]
    if re.fullmatch(r"\d+(?:\.\d+)? (?:in|ft)(?: x \d+(?:\.\d+)? (?:in|ft))?", value):
        dimensions = re.findall(r"(\d+(?:\.\d+)?) (in|ft)", value)
        return math.prod(float(n) * (12 if unit == "ft" else 1) for n, unit in dimensions)
    if re.fullmatch(r"(?:Seats |Pack of )?\d+(?: Pieces| Lights?)?", value):
        return float(re.search(r"\d+", value)[0])
    return None


def variant_prices(base, axes, variants):
    multipliers, flags = {}, []
    for axis in axes:
        attribute, values = axis["attribute"], axis["values"]
        if attribute in {"color", "wands_finish"}:
            multipliers[attribute] = dict.fromkeys(values, 1)
        elif attribute == "wands_material":
            known = {"Cotton": .95, "Engineered Wood": .9, "Faux Leather": 1,
                     "Leather": 1.25, "Linen Blend": 1.05, "Metal": 1.05, "Polyester": .95,
                     "Solid Wood": 1.2, "Velvet": 1.1, "Wool": 1.15}
            if not set(values) <= known.keys():
                flags.append("Unknown material: hold family pricing")
            else:
                multipliers[attribute] = {value: known[value] for value in values}
        else:
            sizes = {value: size_value(value) for value in values}
            if any(value is None for value in sizes.values()):
                flags.append(f"Unknown size/count in {attribute}: hold family pricing")
            else:
                ranks = sorted(set(sizes.values()))
                multipliers[attribute] = {value: 1 + .15 * ranks.index(size) for value, size in sizes.items()}
    if flags or base is None:
        return {}, flags or ["No class price: hold family pricing"]
    result = {}
    for variant in variants:
        options = variant["options"]
        if set(options) != set(multipliers) or any(v not in multipliers[k] for k, v in options.items()):
            raise ValueError(f"Variant axes do not match: {variant['sku']}")
        result[variant["sku"]] = round(round(base * math.prod(multipliers[k][v] for k, v in options.items())) - .01, 2)
    return result, []


def sample_products(rows, families, departments=DEPARTMENTS, count=10):
    result = []
    for dept in departments:
        candidates = sorted((r for r in rows if department(r) == dept and r["product_class"] in PROFILES),
                            key=lambda r: stable_fraction(r["product_id"], VERSION + ":sample"))
        if len(candidates) < count:
            raise ValueError(f"Insufficient supported products in {dept}")
        selected = []
        # Keep the known keyword-stuffed chair as a regression example.
        for row in candidates:
            if row["product_id"] == "42963":
                selected.append(row)
        for row in candidates:
            if len([r for r in selected if r["product_id"] in families]) >= 2:
                break
            if row["product_id"] in families and row not in selected:
                selected.append(row)
        used_classes = {r["product_class"] for r in selected}
        for row in candidates:
            if len(selected) >= count:
                break
            if row["product_class"] not in used_classes:
                selected.append(row)
                used_classes.add(row["product_class"])
        for row in candidates:
            if len(selected) >= count:
                break
            if row not in selected:
                selected.append(row)
        result.extend(selected[:count])
    return result


def availability(sku):
    value = stable_fraction(sku, VERSION + ":stock")
    state = "in_stock" if value < .78 else "low_stock" if value < .90 else "out_of_stock" if value < .97 else "backorder"
    qty = 12 + int(value * 60) if state == "in_stock" else 1 + int(value * 3) if state == "low_stock" else 0
    return {"synthetic": True, "scenario": state, "qty": qty,
            "merchandising": "clearance_candidate" if stable_fraction(sku, VERSION + ":clearance") < .08 else "regular",
            "hold": "Backorders need an explicit policy; no delivery date or bestseller claim is inferred"}


def description_sentences(facts):
    templates = {
        "Seat upholstery": "The seat is upholstered in {}.", "Back upholstery": "The back upholstery is {}.",
        "Upholstery": "Upholstered in {}.", "Frame material": "The frame is made from {}.",
        "Material": "Made from {}.", "Wood species": "Wood species: {}.",
        "Shape": "The shape is {}.", "Pattern": "The pattern is {}.",
        "Color": "Finished in {}.", "Finish": "The finish is {}.",
        "Drawers": "Number of drawers: {}.", "Shelves": "Number of shelves: {}.",
        "Pieces included": "Includes {} pieces.", "Included pieces": "Included pieces: {}.",
        "Care": "Care instructions: {}.",
    }
    sentences = [template.format(facts[label].rstrip(".")) for label, template in templates.items() if label in facts]
    features = [phrase for label, phrase in (("Arms", "armrests"), ("Casters", "casters"),
                ("Swivel", "swivel movement"), ("Adjustable seat height", "adjustable seat height"))
                if facts.get(label, "").casefold() == "yes"]
    if features:
        sentences.insert(0, "Features include " + ", ".join(features) + ".")
    if facts.get("Assembly required", "").casefold() in {"yes", "no"}:
        sentences.append("Assembly is required." if facts["Assembly required"].casefold() == "yes" else "No assembly is required.")
    return sentences[:5]


def product_review(row, prepared, family):
    axes = family["axes"] if family else []
    facts, flags = collect_facts(row, {a["attribute"] for a in axes})
    title = clean_title({**row, "product_name": prepared["name"]}, facts)
    price = price_proposal(row)
    fragments = description_sentences(facts)
    description = f"<p>{html.escape(title)}.</p>"
    if fragments:
        description += "<p>" + html.escape(" ".join(fragments[:5])) + "</p>"
    else:
        flags.append("Sparse facts: description needs editorial review")
    shared_description = description
    if axes:
        description += "<p>" + html.escape("Choose " + "; ".join(
            a["label"].lower() + ": " + ", ".join(a["values"]) for a in axes) + ".") + "</p>"
        flags.append("Synthetic options: verify source-specific constraints before applying shared specifications")
    prices, price_flags = variant_prices(price["amount"], axes, family["variants"]) if family else ({}, [])
    flags += price_flags
    if abs(float(prepared["price"]) - price["amount"]) / max(float(prepared["price"]), 1) > .5:
        flags.append("Price changes by more than 50 percent")
    flags.append("Check title preserves collection/model, quantity and distinguishing details")
    flags.append("Brand unresolved: preserve existing real-brand mentions; do not relabel without review")
    variants = []
    for variant in family["variants"] if family else []:
        variants.append({"sku": variant["sku"], "options": variant["options"],
                         "before_price": variant["price"], "proposed_price": prices.get(variant["sku"]),
                         "proposed_name": title + " - " + ", ".join(variant["options"].values()),
                         "proposed_description": shared_description + "<p>Selected configuration: " + html.escape(
                             "; ".join(a["label"] + ": " + variant["options"][a["attribute"]] for a in axes)) + ".</p>",
                         "availability_proposal": availability(variant["sku"])})
    return {"sku": prepared["sku"], "source_product_id": row["product_id"], "department": department(row),
            "class": row["product_class"], "status": "review_only", "source": row,
            "before": {k: prepared.get(k, "") for k in ("name", "description", "price", "qty", "url_key")},
            "proposal": {"name": title, "description": description, "price": price,
                         "parent_price_range": [min(prices.values()), max(prices.values())] if prices else None,
                         "specifications": facts, "brand": None,
                         "availability": {"derived_from_children": True, "synthetic": True,
                                          "salable_scenarios": ["in_stock", "low_stock"],
                                          "salable_child_count": sum(v["availability_proposal"]["scenario"] in {"in_stock", "low_stock"} for v in variants)}
                         if family else availability(prepared["sku"])},
            "axes": axes, "variants": variants, "flags": flags,
            "preserve": ["sku", "source_product_id", "url_key", "category assignments", "frozen WANDS judgments"]}


def bundle_flags(product_class, allowed, price, option_prices):
    flags = []
    if not set(product_class.casefold().split("|")).intersection(c.casefold() for c in allowed):
        flags.append("Wrong exact product class")
    midpoint = median(option_prices)
    if midpoint > 0 and (price > midpoint * 2.5 or price < midpoint / 2.5):
        flags.append("Selection price outside 2.5x option median")
    return flags


def audit_bundles(bundles, sources, prepared, families):
    output = []
    by_sku = {r["sku"]: r for r in prepared.values()}
    for bundle in bundles:
        theme = bundle["categories"].rsplit("/", 1)[-1]
        if theme not in BUNDLE_DEFINITIONS:
            raise ValueError(f"Unknown bundle theme {theme}")
        rules = dict(BUNDLE_DEFINITIONS[theme])
        if theme == "Dining":
            rules["Serving Storage"] = ("sideboards & buffets", "bar cabinets")
            rules["Lighting"] = ("chandeliers", "pendant lights")
        grouped = defaultdict(list)
        for raw in bundle["bundle_values"].split("|"):
            fields = dict(item.split("=", 1) for item in raw.split(","))
            if fields["name"] not in rules or fields["sku"] not in by_sku:
                raise ValueError(f"Unresolved bundle selection: {raw}")
            grouped[fields["name"]].append(fields)
        if set(grouped) != set(rules):
            raise ValueError(f"Missing bundle options: {bundle['sku']}")
        options, risks = [], ["Palette and dimensions need cross-component verification; not an approved matched set"]
        if theme in {"Bedroom", "Nursery & Kids", "Bathroom", "Dining"}:
            risks.append("Hold every selectable combination for size/fit, counts and intended-use review")
        if theme == "Patio":
            risks.append("Require explicit outdoor suitability for every rug, fabric and finish")
        if theme == "Nursery & Kids":
            risks.append("Separate crib and older-child assortments; no infant sleep safety claims")
        for label, selections in grouped.items():
            option_prices = [float(by_sku[s["sku"]]["price"]) for s in selections]
            reviewed = []
            for selection in selections:
                product = by_sku[selection["sku"]]
                row = sources[product["wands_product_id"]]
                flags = bundle_flags(row["product_class"], rules[label], float(product["price"]), option_prices)
                if row["product_id"] in families:
                    flags.append("Selection is now a configurable parent")
                reviewed.append({"sku": product["sku"], "name": product["name"],
                                 "class": row["product_class"], "price": product["price"], "flags": flags})
            candidates = []
            if any(s["flags"] for s in reviewed):
                eligible = (r for r in sources.values() if r["product_id"] not in families and
                            set(r["product_class"].casefold().split("|")).intersection(c.casefold() for c in rules[label]) and
                            prepared[r["product_id"]]["sku"] not in {s["sku"] for s in reviewed})
                ranked = sorted(eligible, key=lambda r: (abs(float(prepared[r["product_id"]]["price"]) - median(option_prices)), r["product_id"]))
                candidates = [{"sku": prepared[r["product_id"]]["sku"], "name": r["product_name"],
                               "class": r["product_class"], "price": prepared[r["product_id"]]["price"],
                               "status": "candidate_only_fit_and_palette_unverified"} for r in ranked[:3]]
            options.append({"name": label, "selections": reviewed, "replacement_candidates": candidates})
        names = ", ".join(label.lower() for label in grouped)
        copy = f"<p>A {theme.lower()} collection with selectable {names}.</p><p>Choose one item from each option. The total is the sum of the selected components; each component retains its own specifications.</p>"
        output.append({"sku": bundle["sku"], "name": bundle["name"], "theme": theme, "status": "review_only",
                       "before_description": bundle["description"], "proposed_description": copy,
                       "options": options, "flags": risks,
                       "availability_rule": "Salable only if every required option has at least one salable selection; quantities and backorders need explicit policy"})
    return output


def image_briefs(products):
    result = []
    for product in products:
        if not product["variants"]:
            continue
        visual = {a["attribute"] for a in product["axes"]} & {"color", "wands_finish", "wands_material"}
        groups = defaultdict(list)
        geometry = {a["attribute"] for a in product["axes"]} - visual
        for variant in product["variants"]:
            # Different geometry/counts must never share a generated reference blindly.
            identity = tuple(sorted(variant["options"].items()))
            groups[identity].append(variant["sku"])
        for values, skus in sorted(groups.items()):
            result.append({"family_sku": product["sku"], "status": "blocked_pending_approved_reference",
                           "reference_image": None, "visual_options": {k: v for k, v in values if k in visual},
                           "geometry_options": {k: v for k, v in values if k in geometry}, "target_skus": skus,
                           "prompt": "Edit the approved family reference image. Preserve the same product geometry, construction, camera, lighting, background and included components. Change only: " +
                           (", ".join(f"{k}={v}" for k, v in values if k in visual) or "nothing; consider reference reuse only after geometry review") + ". Do not invent logos, extra pieces or structural details. If geometry options differ from the reference, hold this brief for a separate geometry-specific reference.",
                           "acceptance": ["Reference is approved and depicts the correct product", "Only requested appearance changes", "Do not reuse across shape, light-count, piece-count or geometry changes without review", "Human side-by-side check before replacing existing media"],
                           "geometry_review_required": bool(geometry)})
    return result


def render_review(products, bundles, summary):
    esc = lambda value: html.escape(str(value))
    blocks = ["<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>WANDS realism review</title>",
              "<style>body{font:16px/1.55 system-ui;max-width:1160px;margin:36px auto;padding:0 24px;color:#172433;background:#f4f6f8}article{background:white;border:1px solid #d6dde5;border-radius:10px;padding:24px;margin:24px 0}h1,h2,h3{line-height:1.2}small{color:#516174}table{border-collapse:collapse;width:100%}th,td{text-align:left;vertical-align:top;border-bottom:1px solid #dde4ea;padding:12px;width:50%}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}summary{cursor:pointer} .badge{color:#854500;background:#fff0ca;padding:8px;display:inline-block}</style>",
              "<h1>WANDS catalog realism review</h1><p class='badge'>Proposal only. Nothing imported or deployed.</p>",
              f"<p>{len(products)} products across {len({p['department'] for p in products})} departments plus {len(bundles)} bundles. Prices, options, inventory and proposed brands are synthetic lab data, not market evidence. Source facts with conflicts or missing units are withheld. Existing URLs, SKUs and frozen relevance judgments stay unchanged.</p>",
              "<p>Review order: names, copy, prices, image consistency, bundle compatibility, specifications, brand direction, inventory scenarios. Approving the sample is separate from approving a live import.</p>",
              "<details open><summary>Counts and gates</summary><pre>" + esc(json.dumps(summary, indent=2, ensure_ascii=False)) + "</pre></details>"]
    blocks.append("<p>Supporting artifacts: <a href='brand-directions.json'>fictional brand directions</a>, <a href='variant-image-briefs.jsonl'>reference-based image briefs</a>, <a href='rules.json'>rules</a>, <a href='manifest.json'>checksums and scope</a>.</p>")
    for p in products:
        before, proposed = p["before"], p["proposal"]
        blocks += [f"<article id='{esc(p['sku'])}'><small>{esc(p['sku'])} · {esc(p['department'])} · {esc(p['class'])}</small>",
                   f"<h2>{esc(proposed['name'])}</h2><table><tr><th>Before (local import artifact)</th><th>Proposal</th></tr>",
                   f"<tr><td>{esc(before['name'])}</td><td>{esc(proposed['name'])}</td></tr>",
                   f"<tr><td>${esc(before['price'])}</td><td>${esc(proposed['price']['amount'])} synthetic class anchor; family range {esc(proposed['parent_price_range'])}</td></tr>",
                   f"<tr><td>{esc(before['description'])}</td><td>{proposed['description']}</td></tr></table>",
                   "<h3>Review flags</h3><ul>" + "".join("<li>" + esc(f) + "</li>" for f in p["flags"]) + "</ul>",
                   "<details><summary>Specifications, variants, inventory and original evidence</summary><pre>" + esc(json.dumps(p, ensure_ascii=False, indent=2)) + "</pre></details></article>"]
    blocks.append("<h2>Bundle compatibility audit</h2>")
    for bundle in bundles:
        blocks.append("<article><h3>" + esc(bundle["sku"]) + " " + esc(bundle.get("name", "")) + "</h3>" +
                      "<ul>" + "".join("<li>" + esc(flag) + "</li>" for flag in bundle.get("flags", [])) + "</ul>" +
                      "<details><summary>Assortment, replacements and proposed copy</summary><pre>" +
                      esc(json.dumps(bundle, ensure_ascii=False, indent=2)) + "</pre></details></article>")
    return "\n".join(blocks) + "</html>\n"


def read_csv(path, delimiter=","):
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream, delimiter=delimiter))


def unique_index(rows, field):
    result = {r[field]: r for r in rows}
    if len(result) != len(rows) or "" in result:
        raise ValueError(f"Duplicate or empty {field}")
    return result


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def build(args):
    inputs = {"source": args.source_products, "prepared": args.prepared_products,
              "families": args.merchandising_dir / "configurable-families.jsonl",
              "bundles": args.merchandising_dir / "bundles.csv"}
    provenance = {key: {"path": str(path.resolve()), "sha256": sha256(path)} for key, path in inputs.items()}
    rows = read_csv(inputs["source"], "\t")
    source = unique_index(rows, "product_id")
    prepared = unique_index(read_csv(inputs["prepared"]), "wands_product_id")
    with inputs["families"].open(encoding="utf-8") as stream:
        families = unique_index([json.loads(line) for line in stream if line.strip()], "source_product_id")
    if not set(source) <= prepared.keys() or not set(families) <= source.keys():
        raise ValueError("Source, prepared and family identities do not match")
    selected = sample_products(rows, families)
    products = [product_review(row, families[row["product_id"]]["parent"] if row["product_id"] in families else prepared[row["product_id"]], families.get(row["product_id"])) for row in selected]
    names = Counter(p["proposal"]["name"].casefold() for p in products)
    for product in products:
        if names[product["proposal"]["name"].casefold()] > 1:
            product["flags"].append("Duplicate proposed title in sample: retain a source-grounded distinguishing detail")
    bundles = audit_bundles(read_csv(inputs["bundles"]), source, prepared, families)
    briefs = image_briefs(products)
    brands = {"status": "direction_only_no_assignments", "synthetic": True,
              "policy": "Do not replace real source brands. Review title/description/feature brand mentions first. Names are fictional proposals, not checked for uniqueness or trademark availability. No logos generated.",
              "proposals": [{"name": "Alder Cove Lab", "departments": ["Furniture", "Décor & Pillows"], "direction": "Warm natural finishes"},
                            {"name": "Morrow Grid Lab", "departments": ["Lighting", "Home Improvement", "Storage & Organization"], "direction": "Practical contemporary forms"},
                            {"name": "Field & Loom Lab", "departments": ["Rugs", "Bed & Bath"], "direction": "Textural everyday home textiles"}],
              "unassigned_departments": ["Kitchen & Tabletop", "Outdoor", "Baby & Kids"]}
    summary = {"version": VERSION, "review_only": True, "products": len(products),
               "department_counts": dict(Counter(p["department"] for p in products)),
               "configurable_families": sum(bool(p["variants"]) for p in products),
               "child_price_and_inventory_proposals": sum(len(p["variants"]) for p in products),
               "bundles_audited": len(bundles),
               "flagged_bundle_selections": sum(bool(s["flags"]) for b in bundles for o in b["options"] for s in o["selections"]),
               "bundles_with_selection_flags": sum(any(s["flags"] for o in b["options"] for s in o["selections"]) for b in bundles),
               "changed_titles": sum(p["before"]["name"] != p["proposal"]["name"] for p in products),
               "products_with_conflicting_features": sum(any(f.startswith("conflict:") for f in p["flags"]) for p in products),
               "products_with_unitless_dimensions": sum(any(f.startswith("missing unit:") for f in p["flags"]) for p in products),
               "image_briefs": len(briefs), "images_generated": 0, "brand_assignments": 0,
               "live_affected_products": 0, "input_artifacts_not_live_snapshot": True,
               "scale_gate": "Review 100-product sample, rules and flagged bundles; then approve expansion separately",
               "import_gate": "Fresh remote snapshot, dry-run diff/counts, backup and inverse operation, explicit approval, bounded import and live verification"}
    target = args.output_dir.resolve()
    if target.exists():
        raise ValueError("Review directory already exists; choose a new directory to preserve review evidence")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".realism-review-", dir=target.parent) as temp:
        stage = Path(temp) / "packet"
        stage.mkdir()
        write_jsonl(stage / "products.review.jsonl", products)
        write_jsonl(stage / "bundles.review.jsonl", bundles)
        write_jsonl(stage / "variant-image-briefs.jsonl", briefs)
        write_json(stage / "brand-directions.json", brands)
        (stage / "review.html").write_text(render_review(products, bundles, summary), encoding="utf-8")
        write_json(stage / "rules.json", {"version": VERSION, "class_profiles": PROFILES, "fact_keys": FACT_KEYS,
                                         "price_evidence": "Synthetic USD lab anchors only; pack/sale-unit review mandatory",
                                         "inventory_distribution": {"in_stock": .78, "low_stock": .12, "out_of_stock": .07, "backorder": .03},
                                         "implementation_sha256": sha256(Path(__file__))})
        if any(sha256(inputs[key]) != record["sha256"] for key, record in provenance.items()):
            raise ValueError("Input changed during build")
        manifest = {**summary, "inputs": provenance,
                    "outputs": {p.name: sha256(p) for p in sorted(stage.iterdir())}}
        write_json(stage / "manifest.json", manifest)
        stage.rename(target)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-products", type=Path, required=True)
    parser.add_argument("--prepared-products", type=Path, required=True)
    parser.add_argument("--merchandising-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True, help="New review directory; existing packets are never overwritten")
    parser.add_argument("--json", action="store_true", help="Opt in to stdout manifest; otherwise tail the sibling .log")
    args = parser.parse_args()
    log = args.output_dir.with_name(args.output_dir.name + ".log")
    log.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=log, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.info("Starting review-only build: %s", args.output_dir)
    try:
        manifest = build(args)
    except Exception:
        logging.exception("Review build failed; no live changes made")
        return 1
    logging.info("Complete: %s", json.dumps({k: v for k, v in manifest.items() if k not in {"inputs", "outputs"}}, sort_keys=True))
    if args.json:
        print(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
