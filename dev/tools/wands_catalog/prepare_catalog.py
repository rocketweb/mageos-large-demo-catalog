#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

SOURCE_REVISION = "3b74dcf4ba29ab8ff3e6a50b5b09fc627cb882b5"
PRICE_METHOD = "category-class-material-size-rating-deterministic"
PRICE_VERSION = "wands-heuristic-v2"

DEPARTMENT_BANDS: dict[str, tuple[float, float, float]] = {
    "Furniture": (45.0, 450.0, 4500.0),
    "Home Improvement": (8.0, 130.0, 2500.0),
    "Décor & Pillows": (6.0, 55.0, 1200.0),
    "Outdoor": (12.0, 180.0, 3500.0),
    "Storage & Organization": (8.0, 75.0, 950.0),
    "Lighting": (12.0, 120.0, 1800.0),
    "Rugs": (18.0, 190.0, 3200.0),
    "Bed & Bath": (5.0, 65.0, 1400.0),
    "Kitchen & Tabletop": (4.0, 85.0, 2200.0),
    "Baby & Kids": (6.0, 90.0, 1600.0),
    "Appliances": (35.0, 650.0, 5500.0),
    "Pet": (5.0, 70.0, 900.0),
    "Commercial Business Furniture": (50.0, 600.0, 6000.0),
}
DEFAULT_BAND = (5.0, 95.0, 2500.0)

KEYWORD_BASES: tuple[tuple[str, float], ...] = (
    ("sectional", 1650.0),
    ("sofa", 1100.0),
    ("loveseat", 750.0),
    ("mattress", 800.0),
    ("platform bed", 700.0),
    ("bed", 650.0),
    ("dining table", 750.0),
    ("coffee table", 350.0),
    ("desk", 450.0),
    ("dresser", 700.0),
    ("cabinet", 525.0),
    ("vanity", 850.0),
    ("recliner", 650.0),
    ("chair", 280.0),
    ("bookcase", 320.0),
    ("rug", 190.0),
    ("chandelier", 400.0),
    ("pendant", 180.0),
    ("lamp", 95.0),
    ("faucet", 175.0),
    ("slow cooker", 145.0),
    ("refrigerator", 1500.0),
    ("dishwasher", 850.0),
    ("washer", 950.0),
    ("dryer", 900.0),
    ("pillow", 38.0),
    ("throw blanket", 55.0),
    ("towel", 28.0),
    ("storage bin", 32.0),
    ("planter", 75.0),
    ("wall art", 85.0),
)

MATERIAL_MULTIPLIERS: tuple[tuple[str, float], ...] = (
    ("solid wood", 1.45),
    ("marble", 1.55),
    ("granite", 1.45),
    ("genuine leather", 1.55),
    ("leather", 1.35),
    ("brass", 1.25),
    ("stainless steel", 1.20),
    ("acacia", 1.25),
    ("oak", 1.22),
    ("walnut", 1.30),
    ("velvet", 1.18),
    ("engineered wood", 0.82),
    ("mdf", 0.75),
    ("particle board", 0.68),
    ("plastic", 0.72),
)

CSV_FIELDS = [
    "sku",
    "store_view_code",
    "attribute_set_code",
    "product_type",
    "categories",
    "product_websites",
    "name",
    "description",
    "short_description",
    "weight",
    "product_online",
    "tax_class_name",
    "visibility",
    "price",
    "url_key",
    "meta_title",
    "meta_description",
    "qty",
    "out_of_stock_qty",
    "use_config_min_qty",
    "is_in_stock",
    "manage_stock",
    "use_config_manage_stock",
    "wands_product_id",
    "wands_product_class",
    "wands_average_rating",
    "wands_review_count",
    "lab_price_method",
    "lab_price_version",
    "lab_price_synthetic",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare a deterministic Mage-OS catalog from Wayfair WANDS.")
    parser.add_argument("--input", required=True, type=Path, help="Pinned WANDS product.csv path.")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory for Magento CSV and image prompts.")
    parser.add_argument("--limit", type=int, default=None, help="Optional product limit for a validation import.")
    return parser.parse_args()


def normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def title_case(value: str) -> str:
    return normalized_text(value).title()


def slug(value: str) -> str:
    ascii_value = value.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")[:120]


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_features(value: str) -> dict[str, list[str]]:
    parsed: dict[str, list[str]] = {}
    for item in value.split("|"):
        key, separator, raw_value = item.partition(":")
        key = re.sub(r"[^a-z0-9]+", "", key.lower())
        feature_value = normalized_text(raw_value)
        if separator and key and feature_value:
            parsed.setdefault(key, []).append(feature_value)
    return parsed


def first_numeric(features: dict[str, list[str]], keys: tuple[str, ...], default: float) -> float:
    for key in keys:
        values = features.get(key, [])
        numbers = [safe_float(re.search(r"-?\d+(?:\.\d+)?", value).group()) for value in values if re.search(r"-?\d+(?:\.\d+)?", value)]
        if numbers:
            return max(numbers)
    return default


def stable_fraction(product_id: str, namespace: str) -> float:
    digest = hashlib.sha256(f"{namespace}:{product_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


def department(row: dict[str, str]) -> str:
    hierarchy = normalized_text(row.get("category hierarchy", ""))
    if not hierarchy:
        return "Uncategorized"
    return normalized_text(hierarchy.split("/", 1)[0])


def estimated_price(row: dict[str, str]) -> float:
    product_department = department(row)
    low, base, high = DEPARTMENT_BANDS.get(product_department, DEFAULT_BAND)
    product_identity = " ".join(
        [
            row.get("product_name", ""),
            row.get("product_class", ""),
        ]
    ).lower()

    for keyword, keyword_base in sorted(KEYWORD_BASES, key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", product_identity):
            base = keyword_base
            break

    feature_text = row.get("product_features", "").lower()
    material_multiplier = 1.0
    for material, multiplier in MATERIAL_MULTIPLIERS:
        if material in feature_text:
            material_multiplier = multiplier
            break

    features = parse_features(row.get("product_features", ""))
    width = first_numeric(features, ("overallwidthsidetoside", "width"), 30.0)
    size_multiplier = 1.0
    if width >= 84:
        size_multiplier = 1.35
    elif width >= 60:
        size_multiplier = 1.20
    elif width >= 42:
        size_multiplier = 1.10
    elif width <= 10:
        size_multiplier = 0.78

    rating = min(5.0, max(0.0, safe_float(row.get("average_rating"), 3.8)))
    rating_multiplier = 0.92 + (rating / 5.0) * 0.18
    reviews = max(0.0, safe_float(row.get("review_count"), 0.0))
    popularity_multiplier = 1.0 + min(0.12, math.log1p(reviews) / math.log(1001.0) * 0.12)
    jitter_multiplier = 0.88 + stable_fraction(row.get("product_id", "0"), PRICE_VERSION) * 0.24
    raw_price = base * material_multiplier * size_multiplier * rating_multiplier * popularity_multiplier * jitter_multiplier
    bounded = min(high, max(low, raw_price))

    if bounded < 50:
        return max(4.99, round(bounded) - 0.01)
    if bounded < 200:
        return round(bounded / 5.0) * 5.0 - 0.01
    if bounded < 1000:
        return round(bounded / 10.0) * 10.0 - 0.01
    return round(bounded / 25.0) * 25.0 - 0.01


def category_path(row: dict[str, str]) -> str:
    hierarchy = row.get("category hierarchy", "")
    segments = [normalized_text(segment).replace("|", "-")[:150] for segment in hierarchy.split("/")]
    segments = [segment for segment in segments if segment]
    if not segments:
        segments = ["Uncategorized"]
    return "/".join(["WANDS Catalog", *segments])


def feature_summary(features: dict[str, list[str]]) -> list[str]:
    preferred_keys = (
        "producttype",
        "color",
        "finish",
        "primarymaterial",
        "framematerial",
        "woodspecies",
        "upholsterymaterial",
        "overallwidthsidetoside",
        "overallheighttoptobottom",
        "overalldepthfronttoback",
    )
    summary: list[str] = []
    for key in preferred_keys:
        for value in features.get(key, [])[:2]:
            phrase = f"{key}: {value}"
            if phrase not in summary:
                summary.append(phrase)
            if len(summary) == 8:
                return summary
    return summary


def transform(row: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
    product_id = row["product_id"].strip()
    sku = f"WANDS-{int(product_id):06d}"
    source_name = title_case(row.get("product_name", "")) or f"WANDS Product {product_id}"
    name = source_name[:255].rstrip()
    description = normalized_text(row.get("product_description", ""))
    if not description:
        description = f"A realistic {name.lower()} selected for the WANDS product relevance laboratory."
    product_class = title_case(row.get("product_class", "")) or "Uncategorized"
    features = parse_features(row.get("product_features", ""))
    price = estimated_price(row)
    weight = first_numeric(features, ("overallproductweight", "weight"), 1.0)
    weight = min(5000.0, max(0.1, weight))
    quantity = 5 + int(stable_fraction(product_id, "inventory-v1") * 196)
    short_description = description[:237].rstrip() + ("..." if len(description) > 237 else "")
    meta_description = description[:255]
    product_row = {
        "sku": sku,
        "store_view_code": "",
        "attribute_set_code": "Default",
        "product_type": "simple",
        "categories": category_path(row),
        "product_websites": "wands",
        "name": name,
        "description": description,
        "short_description": short_description,
        "weight": f"{weight:.2f}",
        "product_online": "1",
        "tax_class_name": "Taxable Goods",
        "visibility": "Catalog, Search",
        "price": f"{price:.2f}",
        "url_key": f"wands-{product_id}-{slug(name)}",
        "meta_title": name[:255],
        "meta_description": meta_description,
        "qty": str(quantity),
        "out_of_stock_qty": "0",
        "use_config_min_qty": "1",
        "is_in_stock": "1",
        "manage_stock": "1",
        "use_config_manage_stock": "0",
        "wands_product_id": product_id,
        "wands_product_class": product_class,
        "wands_average_rating": f"{safe_float(row.get('average_rating')):.2f}",
        "wands_review_count": str(int(safe_float(row.get("review_count")))),
        "lab_price_method": PRICE_METHOD,
        "lab_price_version": PRICE_VERSION,
        "lab_price_synthetic": "Yes",
    }
    details = feature_summary(features)
    prompt = (
        f"Commercial ecommerce product photography of one {name}. "
        f"Product type: {product_class}. Category: {department(row)}. "
        + (f"Important product details: {'; '.join(details)}. " if details else "")
        + "Centered three-quarter view on a seamless warm-white studio background, soft natural shadow, "
        "realistic materials and proportions, sharp catalog photography. No people, no room scene, "
        "no packaging. No visible text, logos, watermarks, or duplicate objects."
    )
    prompt_row = {
        "product_id": product_id,
        "sku": sku,
        "title": name,
        "product_class": product_class,
        "category": category_path(row),
        "price": price,
        "seed": int(stable_fraction(product_id, "image-v1") * (2**31 - 1)),
        "prompt": prompt,
        "output_file": f"{sku}.jpg",
    }
    return product_row, prompt_row


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare(input_path: Path, output_dir: Path, limit: int | None) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    product_output = output_dir / "products.csv"
    prompt_output = output_dir / "image-prompts.jsonl"
    prices: list[float] = []
    classes: set[str] = set()
    departments: Counter[str] = Counter()
    count = 0

    with input_path.open("r", encoding="utf-8", newline="") as source, product_output.open(
        "w", encoding="utf-8", newline=""
    ) as product_stream, prompt_output.open("w", encoding="utf-8") as prompt_stream:
        reader = csv.DictReader(source, delimiter="\t")
        writer = csv.DictWriter(product_stream, fieldnames=CSV_FIELDS, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for source_row in reader:
            if limit is not None and count >= limit:
                break
            product_row, prompt_row = transform(source_row)
            writer.writerow(product_row)
            prompt_stream.write(json.dumps(prompt_row, ensure_ascii=False, sort_keys=True) + "\n")
            prices.append(float(product_row["price"]))
            classes.add(product_row["wands_product_class"])
            departments[department(source_row)] += 1
            count += 1

    manifest = {
        "schema_version": 1,
        "source": "Wayfair WANDS",
        "source_revision": SOURCE_REVISION,
        "source_file": str(input_path.resolve()),
        "source_sha256": sha256(input_path),
        "products": count,
        "product_classes": len(classes),
        "departments": dict(departments.most_common()),
        "price_method": PRICE_METHOD,
        "price_version": PRICE_VERSION,
        "price_min": min(prices),
        "price_median": statistics.median(prices),
        "price_max": max(prices),
        "products_csv_sha256": sha256(product_output),
        "image_prompts_sha256": sha256(prompt_output),
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    arguments = parse_args()
    manifest = prepare(arguments.input, arguments.output_dir, arguments.limit)
    print(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
