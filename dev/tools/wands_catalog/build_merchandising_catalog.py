#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from prepare_catalog import CSV_FIELDS as BASE_CSV_FIELDS
from prepare_catalog import normalized_text, parse_features, sha256, slug, stable_fraction

SCHEMA_VERSION = 1
PLAN_VERSION = "wands-merchandising-v1"

ATTRIBUTE_LABELS = {
    "color": "Color",
    "wands_size": "Size",
    "wands_finish": "Finish",
    "wands_material": "Material",
    "wands_length": "Length / Width",
    "wands_seat_height": "Seat Height",
    "wands_seating_capacity": "Seating Capacity",
    "wands_piece_count": "Piece Count",
    "wands_pack_size": "Pack Size",
    "wands_light_count": "Light Count",
}

ATTRIBUTE_OPTIONS = {
    "color": [
        "Beige", "Black", "Blue", "Brown", "Cream", "Gray", "Green", "Ivory",
        "Navy", "Natural", "Red", "Terracotta", "White",
    ],
    "wands_size": [
        "Small", "Medium", "Large", "Extra Large", "Twin", "Full", "Queen", "King",
        "2 ft x 3 ft", "5 ft x 7 ft", "8 ft x 10 ft", "9 ft x 12 ft",
        "16 in x 16 in", "18 in x 18 in", "20 in x 20 in", "22 in x 22 in",
        "12 in x 12 in", "24 in x 24 in", "18 in x 30 in", "24 in x 36 in",
        "30 in x 48 in", "36 in x 60 in", "Toddler",
        "6 in x 6 in", "Twin over Twin", "Twin over Full", "Full over Full", "Twin XL over Queen",
    ],
    "wands_finish": [
        "Natural", "Walnut", "Oak", "Espresso", "Black", "White", "Brass", "Chrome",
        "Brushed Nickel", "Matte Black", "Bronze", "Cream",
    ],
    "wands_material": [
        "Cotton", "Engineered Wood", "Faux Leather", "Leather", "Linen Blend", "Metal",
        "Polyester", "Solid Wood", "Velvet", "Wool",
    ],
    "wands_length": [
        "24 in", "30 in", "36 in", "42 in", "48 in", "60 in", "63 in", "72 in",
        "84 in", "95 in", "108 in",
    ],
    "wands_seat_height": ["18 in", "24 in", "26 in", "30 in", "32 in"],
    "wands_seating_capacity": ["Seats 2", "Seats 4", "Seats 6", "Seats 8"],
    "wands_piece_count": ["2 Pieces", "3 Pieces", "4 Pieces", "5 Pieces", "7 Pieces"],
    "wands_pack_size": ["Pack of 4", "Pack of 6", "Pack of 8", "Pack of 10", "Pack of 12"],
    "wands_light_count": ["1 Light", "3 Lights", "4 Lights", "6 Lights", "8 Lights"],
}

CONFIGURABLE_CSV_FIELDS = [
    *BASE_CSV_FIELDS,
    *ATTRIBUTE_LABELS,
    "configurable_variations",
    "configurable_variation_labels",
]

BUNDLE_CSV_FIELDS = [
    *BASE_CSV_FIELDS,
    "bundle_price_type",
    "bundle_sku_type",
    "bundle_price_view",
    "bundle_weight_type",
    "bundle_shipment_type",
    "bundle_values",
]

DEFAULT_GROUP_QUOTAS = {
    "rugs_mats": 300,
    "beds_bedding": 350,
    "chairs_stools": 400,
    "curtains_pillows": 250,
    "casegoods": 350,
    "tile_lighting": 180,
    "outdoor": 90,
    "baby_pet": 80,
}

DEFAULT_ONE_AXIS_QUOTAS = {
    "rugs_mats": 90,
    "beds_bedding": 105,
    "chairs_stools": 120,
    "curtains_pillows": 75,
    "casegoods": 105,
    "tile_lighting": 54,
    "outdoor": 27,
    "baby_pet": 24,
}

DEFAULT_BUNDLE_THEMES = {
    "Living Room": 5,
    "Bedroom": 5,
    "Dining": 5,
    "Home Office": 5,
    "Patio": 5,
    "Bathroom": 5,
    "Nursery & Kids": 5,
    "Entryway": 5,
    "Reading Nook": 5,
    "Pet Corner": 5,
}

GROUP_CANDIDATE_TERMS = {
    "rugs_mats": ("area rugs", "doormats", "kitchen mats", "bath rugs & mats"),
    "beds_bedding": (
        "beds", "bedding sets", "sheets and sheet sets", "headboards", "bed frames",
        "daybeds & guest beds", "mattresses", "comforters & duvet fills",
    ),
    "chairs_stools": (
        "accent chairs", "bar stools", "dining chairs", "recliners", "office chairs",
        "office stools", "ottomans", "stackable chairs", "game chairs",
    ),
    "curtains_pillows": (
        "accent pillows", "curtains & drapes", "shower curtains", "valances & kitchen curtains",
    ),
    "casegoods": (
        "coffee & cocktail tables", "end tables", "dining tables", "desks", "sofa & console tables",
        "dressers & chests", "vanities", "nightstands", "accent chests / cabinets",
        "office storage cabinets", "bookcases", "bathroom storage", "sideboards", "buffets",
    ),
    "tile_lighting": (
        "floor & wall tile", "accent tiles", "chandeliers", "wall sconces", "flush mount lighting",
        "pendant lights", "floor lamps", "table lamps", "outdoor wall lights",
    ),
    "outdoor": (
        "outdoor conversation sets", "patio sofas", "patio tables", "patio dining sets",
        "patio lounge chairs", "patio rockers & gliders", "patio chaise lounges", "planters",
    ),
    "baby_pet": (
        "kids beds", "kids chairs", "kids dressers & chests", "kids desks", "kids bookcases",
        "crib bedding sets", "cribs", "dog beds & mats", "cat beds", "pet gates",
        "dog and cat bowls, feeders & accessories", "cat condos & cat trees",
    ),
}

BUNDLE_DEFINITIONS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "Living Room": (
        ("Seating", ("sofas", "sectionals", "loveseats")),
        ("Coffee Table", ("coffee & cocktail tables", "coffee tables")),
        ("Accent Seating", ("accent chairs", "ottomans")),
        ("Area Rug", ("area rugs",)),
    ),
    "Bedroom": (
        ("Bed", ("beds", "kids beds")),
        ("Bedding", ("bedding sets",)),
        ("Nightstand", ("nightstands",)),
        ("Storage", ("dressers & chests",)),
    ),
    "Dining": (
        ("Dining Table", ("dining tables",)),
        ("Dining Chairs", ("dining chairs",)),
        ("Serving Storage", ("sideboards", "buffets", "bar cabinets")),
        ("Lighting", ("chandeliers", "pendant lighting")),
    ),
    "Home Office": (
        ("Desk", ("desks",)),
        ("Office Chair", ("office chairs",)),
        ("Bookcase", ("bookcases",)),
        ("Task Light", ("table lamps", "floor lamps")),
    ),
    "Patio": (
        ("Outdoor Seating", ("outdoor conversation sets", "patio sofas", "patio lounge chairs")),
        ("Patio Table", ("patio tables",)),
        ("Outdoor Rug", ("outdoor rugs", "area rugs")),
        ("Planter", ("planters",)),
    ),
    "Bathroom": (
        ("Vanity", ("vanities", "vanity bases")),
        ("Mirror", ("wall & accent mirrors",)),
        ("Faucet", ("bathroom sink faucets",)),
        ("Bath Mat", ("bath rugs & mats",)),
    ),
    "Nursery & Kids": (
        ("Bed", ("kids beds", "cribs")),
        ("Bedding", ("crib bedding sets", "bedding sets")),
        ("Storage", ("kids dressers & chests", "dressers & chests")),
        ("Chair", ("kids chairs",)),
    ),
    "Entryway": (
        ("Console", ("sofa & console tables",)),
        ("Bench", ("benches",)),
        ("Mirror", ("wall & accent mirrors",)),
        ("Organization", ("coat racks and hooks", "hall trees")),
    ),
    "Reading Nook": (
        ("Chair", ("accent chairs",)),
        ("Ottoman", ("ottomans",)),
        ("Floor Lamp", ("floor lamps",)),
        ("Bookcase", ("bookcases",)),
        ("Pillow", ("accent pillows",)),
    ),
    "Pet Corner": (
        ("Pet Bed", ("dog beds & mats", "cat beds")),
        ("Feeding", ("dog and cat bowls, feeders & accessories",)),
        ("Gate", ("pet gates",)),
        ("Storage", ("hampers & baskets", "boxes, bins, baskets, & buckets", "toy boxes and organizers")),
    ),
}


@dataclass(frozen=True)
class PlanConfig:
    group_quotas: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_GROUP_QUOTAS))
    one_axis_quotas: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_ONE_AXIS_QUOTAS))
    bundle_themes: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_BUNDLE_THEMES))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build deterministic configurable and bundle WANDS manifests.")
    parser.add_argument("--source-products", required=True, type=Path, help="Pinned WANDS TSV product file.")
    parser.add_argument("--prepared-products", required=True, type=Path, help="Prepared Magento products CSV.")
    parser.add_argument("--output-dir", required=True, type=Path, help="Output directory for reviewable manifests.")
    parser.add_argument("--configurable-count", type=int, default=2000)
    parser.add_argument("--bundle-count", type=int, default=50)
    return parser.parse_args()


def stable_key(value: str, namespace: str) -> tuple[str, str]:
    return hashlib.sha256(f"{namespace}:{value}".encode()).hexdigest(), value


def normalized_class(row: dict[str, str]) -> str:
    return normalized_text(row.get("product_class", "")).lower()


def product_group(row: dict[str, str]) -> str | None:
    product_class = normalized_class(row)
    hierarchy = normalized_text(row.get("category hierarchy", "")).lower()
    department = hierarchy.split("/", 1)[0].strip()
    if department == "outdoor" or any(term in product_class for term in ("patio", "outdoor", "planter")):
        return "outdoor"
    if department in {"baby & kids", "pet"} or any(
        term in product_class for term in ("baby", "kids", "crib", "pet ", "dog ", "cat ")
    ):
        return "baby_pet"
    if department == "rugs" or "rug" in product_class or any(
        term in product_class for term in ("doormat", "kitchen mats", "bath mats")
    ):
        return "rugs_mats"
    if any(term in product_class for term in ("bed", "bedding", "mattress", "headboard")) or (
        "sheets and sheet sets" in product_class
    ):
        return "beds_bedding"
    if any(term in product_class for term in ("chair", "stool", "recliner", "ottoman")):
        return "chairs_stools"
    if any(term in product_class for term in ("curtain", "pillow", "throw blanket")):
        return "curtains_pillows"
    if any(term in product_class for term in ("tile", "light", "lamp", "chandelier", "pendant", "sconce")):
        return "tile_lighting"
    if any(
        term in product_class
        for term in ("desk", "table", "vanit", "dresser", "nightstand", "bookcase", "cabinet", "storage", "shelf")
    ):
        return "casegoods"
    return None


def is_merchandising_candidate(row: dict[str, str], group: str) -> bool:
    product_class = normalized_class(row)
    if product_class == "uncategorized" or "accessor" in product_class or "hardware" in product_class:
        return False
    return any(term in product_class for term in GROUP_CANDIDATE_TERMS[group])


def candidate_name_penalty(row: dict[str, str]) -> int:
    name = normalized_text(row.get("product_name", "")).lower()
    dimension = bool(re.search(r"\b\d+(?:\.\d+)?\s*(?:in|inch|ft|foot|'|\")", name))
    explicit_color = bool(re.search(
        r"\b(?:beige|black|blue|brown|cream|gray|grey|green|ivory|navy|natural|red|terracotta|white)\b",
        name,
    ))
    return int(dimension) + int(explicit_color)


def rotated(values: list[str], product_id: str, namespace: str, count: int) -> list[str]:
    offset = int(stable_fraction(product_id, namespace) * len(values)) % len(values)
    ordered = values[offset:] + values[:offset]
    return ordered[:count]


def feature_values(features: dict[str, list[str]], keys: Iterable[str]) -> list[str]:
    values: list[str] = []
    for key in keys:
        values.extend(features.get(key, []))
    return values


def preferred_option(options: list[str], raw_values: Iterable[str]) -> str | None:
    raw = " ".join(raw_values).lower()
    aliases = {
        "Gray": ("gray", "grey"),
        "Natural": ("natural",),
        "Navy": ("navy",),
        "Terracotta": ("terracotta", "rust"),
        "Brushed Nickel": ("brushed nickel", "nickel"),
        "Matte Black": ("matte black",),
        "Linen Blend": ("linen",),
        "Faux Leather": ("faux leather",),
        "Solid Wood": ("solid wood",),
        "Engineered Wood": ("engineered wood", "manufactured wood", "mdf"),
    }
    for option in options:
        needles = aliases.get(option, (option.lower(),))
        if any(needle in raw for needle in needles):
            return option
    return None


def option_values(
    attribute: str,
    product_id: str,
    count: int,
    raw_values: Iterable[str] = (),
    restricted: list[str] | None = None,
) -> list[str]:
    choices = restricted or ATTRIBUTE_OPTIONS[attribute]
    ordered_attributes = {
        "wands_size", "wands_length", "wands_seat_height", "wands_seating_capacity",
        "wands_piece_count", "wands_pack_size", "wands_light_count",
    }
    selected = choices[:count] if restricted is not None or attribute in ordered_attributes else rotated(
        choices,
        product_id,
        attribute,
        count,
    )
    preferred = preferred_option(choices, raw_values)
    if preferred is not None and preferred not in selected:
        selected[-1] = preferred
    return selected


def axis_profile(row: dict[str, str], one_axis: bool) -> list[dict[str, Any]]:
    product_id = row["product_id"].strip()
    product_class = normalized_class(row)
    features = parse_features(row.get("product_features", ""))
    colors = feature_values(features, ("color", "primarycolor", "upholsterycolor", "seatcolor", "maincolor"))
    finishes = feature_values(features, ("finish", "basefinish", "topfinish", "basecolor", "topcolor"))
    materials = feature_values(
        features,
        ("material", "primarymaterial", "framematerial", "upholsterymaterial", "mainmaterial", "topmaterial"),
    )

    group = product_group(row)
    if group == "rugs_mats" and any(term in product_class for term in ("doormat", "kitchen mats", "bath rugs")):
        specs = [
            ("wands_size", ["18 in x 30 in", "24 in x 36 in", "30 in x 48 in", "36 in x 60 in"], ()),
            ("color", None, colors),
        ]
    elif group == "rugs_mats":
        specs = [
            ("wands_size", ["2 ft x 3 ft", "5 ft x 7 ft", "8 ft x 10 ft", "9 ft x 12 ft"], ()),
            ("color", None, colors),
        ]
    elif group == "beds_bedding":
        specs = [
            ("wands_size", ["Twin", "Full", "Queen", "King"], feature_values(features, ("mattresssize", "size"))),
            ("color", None, colors),
        ]
    elif group == "chairs_stools" and "stool" in product_class:
        specs = [
            ("wands_seat_height", ["18 in", "24 in", "26 in", "30 in"], feature_values(features, ("seatheightfloortoseat",))),
            ("color", None, colors),
        ]
    elif group == "chairs_stools":
        specs = [("color", None, colors), ("wands_material", None, materials)]
    elif group == "curtains_pillows" and "curtain" in product_class:
        specs = [
            ("wands_length", ["63 in", "84 in", "95 in", "108 in"], feature_values(features, ("overalllengthendtoend", "panelheight"))),
            ("color", None, colors),
        ]
    elif group == "curtains_pillows":
        specs = [
            ("wands_size", ["16 in x 16 in", "18 in x 18 in", "20 in x 20 in", "22 in x 22 in"], ()),
            ("color", None, colors),
        ]
    elif group == "casegoods" and "dining table" in product_class:
        specs = [
            ("wands_seating_capacity", None, feature_values(features, ("seatingcapacity",))),
            ("wands_finish", None, finishes),
        ]
    elif group == "casegoods":
        specs = [
            ("wands_length", ["30 in", "36 in", "48 in", "60 in"], feature_values(features, ("overallwidthsidetoside", "overalllengthendtoend"))),
            ("wands_finish", None, finishes),
        ]
    elif group == "tile_lighting" and "tile" in product_class:
        specs = [
            ("wands_size", ["6 in x 6 in", "12 in x 12 in", "18 in x 18 in", "24 in x 24 in"], ()),
            ("wands_pack_size", None, feature_values(features, ("piecespercarton", "piecesincluded"))),
        ]
    elif group == "tile_lighting" and "lamp" in product_class:
        specs = [("wands_finish", None, finishes), ("color", None, colors)]
    elif group == "tile_lighting":
        specs = [
            ("wands_light_count", None, feature_values(features, ("numberoflights",))),
            ("wands_finish", None, finishes),
        ]
    elif group == "outdoor" and "set" in product_class:
        specs = [
            ("wands_piece_count", None, feature_values(features, ("numberofpiecesincluded", "piecesincluded"))),
            ("color", None, colors),
        ]
    elif group == "outdoor":
        specs = [
            ("wands_size", ["Small", "Medium", "Large", "Extra Large"], ()),
            ("color", None, colors),
        ]
    elif group == "baby_pet" and "bunk" in row.get("product_name", "").lower():
        specs = [
            ("wands_size", ["Twin over Twin", "Twin over Full", "Full over Full", "Twin XL over Queen"], ()),
            ("color", None, colors),
        ]
    elif group == "baby_pet" and any(term in product_class for term in ("bed", "bedding", "crib")):
        specs = [
            ("wands_size", ["Toddler", "Twin", "Full", "Queen"], feature_values(features, ("mattresssize", "size"))),
            ("color", None, colors),
        ]
    else:
        specs = [("wands_size", ["Small", "Medium", "Large", "Extra Large"], ()), ("color", None, colors)]

    axes: list[dict[str, Any]] = []
    for index, (attribute, restricted, raw_values) in enumerate(specs[: 1 if one_axis else 2]):
        count = 4 if one_axis else (3 if index == 0 else 2)
        axes.append(
            {
                "attribute": attribute,
                "label": ATTRIBUTE_LABELS[attribute],
                "values": option_values(attribute, product_id, count, raw_values, restricted),
            }
        )
    return axes


def clean_name(value: str) -> str:
    return normalized_text(value).strip(" .")[:255]


def family_name(value: str, axes: list[dict[str, Any]]) -> str:
    name = clean_name(value)
    attributes = {axis["attribute"] for axis in axes}
    if attributes & {"wands_size", "wands_length"}:
        name = re.sub(
            r"\b\d+(?:\.\d+)?\s*(?:''|\"|in\.?|inches?)\s*(?:wide|high|tall|long)?\b",
            "",
            name,
            flags=re.IGNORECASE,
        )
        name = re.sub(r"\s+[xX]\s+(?=[,;])", " ", name)
    if "wands_seat_height" in attributes:
        name = re.sub(
            r"\b\d+(?:\.\d+)?\s*(?:''|\"|in\.?|inches?)\s*(?:seat height|high|tall)?\b",
            "",
            name,
            flags=re.IGNORECASE,
        )
    if "wands_light_count" in attributes:
        name = re.sub(r"\b\d+\s*-?\s*light\b", "", name, flags=re.IGNORECASE)
    if "wands_piece_count" in attributes:
        name = re.sub(r"\b\d+\s*-?\s*piece\b", "", name, flags=re.IGNORECASE)
    if "wands_seating_capacity" in attributes:
        name = re.sub(r"\b\d+\s*-?\s*(?:person|seat)\b", "", name, flags=re.IGNORECASE)
    if "wands_pack_size" in attributes:
        name = re.sub(r"\bpack of \d+\b", "", name, flags=re.IGNORECASE)
    if "color" in attributes:
        color_pattern = "|".join(re.escape(color) for color in ATTRIBUTE_OPTIONS["color"])
        name = re.sub(
            rf"(?:\s+in|\s*[,/-])\s*(?:{color_pattern}|multicolor)\s*$",
            "",
            name,
            flags=re.IGNORECASE,
        )
    name = re.sub(r"\s+([,;])", r"\1", name)
    name = re.sub(r"([,;])(?:\s*[,;])+", r"\1", name)
    return clean_name(name) or clean_name(value)


def room_name(row: dict[str, str]) -> str:
    hierarchy = normalized_text(row.get("category hierarchy", ""))
    department = hierarchy.split("/", 1)[0].strip().lower()
    mapping = {
        "furniture": "your home",
        "rugs": "your room",
        "bed & bath": "your bedroom or bath",
        "outdoor": "your outdoor space",
        "lighting": "your room",
        "baby & kids": "a child-friendly space",
        "pet": "your pet area",
        "home improvement": "your project",
    }
    return mapping.get(department, "your space")


def parent_description(row: dict[str, str], axes: list[dict[str, Any]], name: str) -> str:
    product_class = clean_name(row.get("product_class", "product")).replace("|", " / ").lower()
    labels = [axis["label"].lower() for axis in axes]
    choices = labels[0] if len(labels) == 1 else f"{labels[0]} and {labels[1]}"
    templates = (
        f"<p>{name} brings a considered profile to {room_name(row)}. This product family is part of the {product_class} category. Choose {choices} to fit your layout and palette.</p>",
        f"<p>Build {name} around the needs of {room_name(row)}. Choose {choices} while keeping a consistent design across this {product_class} product family.</p>",
        f"<p>{name} is a flexible product family in the {product_class} category. Choose {choices} for a combination suited to your space.</p>",
        f"<p>Give {room_name(row)} a coordinated foundation with {name}. Choose {choices} to select the right {product_class} variation for the project.</p>",
    )
    selected = templates[int(stable_fraction(row["product_id"], "parent-copy-v1") * len(templates)) % len(templates)]
    option_summary = "; ".join(f"{axis['label']}: {', '.join(axis['values'])}" for axis in axes)
    return selected + f"<p>Available options include {option_summary}. Review the selected configuration for its exact option values.</p>"


def child_description(parent_name: str, product_class: str, options: dict[str, str]) -> str:
    option_text = ", ".join(f"{ATTRIBUTE_LABELS[attribute].lower()} {value}" for attribute, value in options.items())
    return (
        f"<p>{parent_name} in {option_text}. This selectable {product_class.lower()} variation keeps the "
        "family's coordinated design while reflecting the chosen options.</p>"
    )


def option_price_multiplier(attribute: str, value: str, position: int, total: int) -> float:
    if attribute in {"color", "wands_finish"}:
        return 1.0
    if attribute == "wands_material":
        return {
            "Cotton": 0.95,
            "Engineered Wood": 0.90,
            "Faux Leather": 1.00,
            "Leather": 1.25,
            "Linen Blend": 1.05,
            "Metal": 1.05,
            "Polyester": 0.95,
            "Solid Wood": 1.20,
            "Velvet": 1.10,
            "Wool": 1.15,
        }.get(value, 1.0)
    centered = position - (total - 1) / 2
    step = {
        "wands_size": 0.10,
        "wands_length": 0.08,
        "wands_seat_height": 0.05,
        "wands_seating_capacity": 0.12,
        "wands_piece_count": 0.15,
        "wands_pack_size": 0.10,
        "wands_light_count": 0.10,
        "wands_material": 0.08,
    }.get(attribute, 0.05)
    return 1.0 + centered * step


def retail_price(value: float) -> str:
    bounded = max(4.99, value)
    if bounded < 50:
        return f"{max(4.99, round(bounded) - 0.01):.2f}"
    if bounded < 200:
        return f"{round(bounded / 5.0) * 5.0 - 0.01:.2f}"
    if bounded < 1000:
        return f"{round(bounded / 10.0) * 10.0 - 0.01:.2f}"
    return f"{round(bounded / 25.0) * 25.0 - 0.01:.2f}"


def child_sku(parent_sku: str, options: dict[str, str]) -> str:
    suffix = "-".join(
        f"{slug(value).upper()[:16]}-{hashlib.sha256(value.encode()).hexdigest()[:4].upper()}"
        for value in options.values()
    )
    return f"{parent_sku}-{suffix}"[:64].rstrip("-")


def plan_family(source: dict[str, str], prepared: dict[str, str], one_axis: bool) -> dict[str, Any]:
    axes = axis_profile(source, one_axis)
    combinations = list(itertools.product(*(axis["values"] for axis in axes)))
    parent_name = family_name(prepared["name"], axes)
    original_parent = {field: prepared.get(field, "") for field in BASE_CSV_FIELDS}
    parent = {field: prepared.get(field, "") for field in BASE_CSV_FIELDS}
    parent.update(
        {
            "product_type": "configurable",
            "name": parent_name,
            "description": parent_description(source, axes, parent_name),
            "short_description": (
                f"Choose {' and '.join(axis['label'].lower() for axis in axes)} for "
                f"{parent_name}."
            ),
            "meta_description": (
                f"Explore {parent_name} in selectable "
                f"{' and '.join(axis['label'].lower() for axis in axes)}."
            )[:255],
            "meta_title": parent_name[:255],
            "price": "",
            "weight": "",
            "qty": "0",
            "manage_stock": "0",
            "use_config_manage_stock": "1",
        }
    )
    variants: list[dict[str, Any]] = []
    base_price = float(prepared["price"])
    base_qty = max(1, int(float(prepared.get("qty", "10") or 10)))
    for combination in combinations:
        options = {axis["attribute"]: value for axis, value in zip(axes, combination, strict=True)}
        multiplier = 1.0
        for axis, value in zip(axes, combination, strict=True):
            position = axis["values"].index(value)
            multiplier *= option_price_multiplier(axis["attribute"], value, position, len(axis["values"]))
        sku = child_sku(prepared["sku"], options)
        name_suffix = " / ".join(combination)
        variant = {field: prepared.get(field, "") for field in BASE_CSV_FIELDS}
        variant.update(
            {
                "sku": sku,
                "product_type": "simple",
                "categories": "",
                "name": f"{parent_name} - {name_suffix}"[:255],
                "description": child_description(parent_name, source["product_class"], options),
                "short_description": f"{parent_name} in {name_suffix}."[:255],
                "visibility": "Not Visible Individually",
                "price": retail_price(base_price * multiplier),
                "url_key": f"{prepared['url_key']}-{slug(name_suffix)}"[:255],
                "meta_title": f"{parent_name} - {name_suffix}"[:255],
                "meta_description": f"{parent_name} in {name_suffix}."[:255],
                "qty": str(max(1, round(base_qty / len(combinations)))),
                "wands_product_id": "",
            }
        )
        variant.update({attribute: "" for attribute in ATTRIBUTE_LABELS})
        variant.update(options)
        variant["options"] = options
        variants.append(variant)
    parent.update({attribute: "" for attribute in ATTRIBUTE_LABELS})
    return {
        "plan_version": PLAN_VERSION,
        "group": product_group(source),
        "source_product_id": source["product_id"],
        "one_axis": one_axis,
        "axes": axes,
        "original_parent": original_parent,
        "parent": parent,
        "variants": variants,
    }


def deduplicate_family_names(families: list[dict[str, Any]]) -> None:
    by_name: dict[str, list[dict[str, Any]]] = {}
    for family in families:
        by_name.setdefault(family["parent"]["name"], []).append(family)
    collection_names = (
        "Alder", "Beacon", "Cove", "Dover", "Elm", "Fieldstone", "Grove", "Harbor",
        "Juniper", "Linden", "Meadow", "Northstar", "Oakmont", "Parkside", "Ridge",
        "Summit", "Terrace", "Vale", "Willow", "York",
    )
    for original_name, duplicate_families in by_name.items():
        if len(duplicate_families) == 1:
            continue
        duplicate_families.sort(key=lambda family: int(family["source_product_id"]))
        for index, family in enumerate(duplicate_families):
            replacement = f"{original_name} - {collection_names[index]} Collection"[:255]
            parent = family["parent"]
            parent["name"] = replacement
            parent["meta_title"] = replacement
            parent["description"] = parent["description"].replace(original_name, replacement)
            parent["short_description"] = parent["short_description"].replace(original_name, replacement)
            parent["meta_description"] = parent["meta_description"].replace(original_name, replacement)[:255]
            for variant in family["variants"]:
                variant["name"] = variant["name"].replace(original_name, replacement)[:255]
                variant["description"] = variant["description"].replace(original_name, replacement)
                variant["short_description"] = variant["short_description"].replace(original_name, replacement)[:255]
                variant["meta_title"] = variant["meta_title"].replace(original_name, replacement)[:255]
                variant["meta_description"] = variant["meta_description"].replace(original_name, replacement)[:255]


def class_matches(row: dict[str, str], terms: tuple[str, ...]) -> bool:
    product_class = normalized_class(row)
    return any(product_class == term or term in product_class for term in terms)


def bundle_palette(theme: str, index: int) -> tuple[str, str]:
    palettes = (
        ("Warm Natural", "natural wood and warm neutral tones"),
        ("Modern Contrast", "black, white, and clean modern finishes"),
        ("Soft Coastal", "light neutrals and relaxed blue accents"),
        ("Rich Walnut", "walnut-inspired finishes and grounded colors"),
        ("Quiet Neutral", "soft gray, cream, and natural textures"),
    )
    offset = int(stable_fraction(str(index), f"bundle-palette:{theme}") * len(palettes)) % len(palettes)
    return palettes[offset]


def component_score(row: dict[str, str], prepared: dict[str, str], palette: str, theme: str, index: int) -> tuple[Any, ...]:
    text = f"{row.get('product_features', '')} {row.get('product_name', '')}".lower()
    palette_tokens = {token for token in re.split(r"[^a-z]+", palette.lower()) if len(token) >= 4}
    palette_match = -sum(token in text for token in palette_tokens)
    price = float(prepared.get("price", "0") or 0)
    price_tier = (index % 5 + 1) / 6
    price_distance = abs(stable_fraction(row["product_id"], f"bundle-price:{theme}") - price_tier)
    return palette_match, price_distance, stable_key(row["product_id"], f"bundle:{theme}:{index}"), price


def build_bundles(
    source_rows: list[dict[str, str]],
    prepared_by_id: dict[str, dict[str, str]],
    excluded_skus: set[str],
    themes: dict[str, int],
) -> list[dict[str, Any]]:
    eligible = [row for row in source_rows if prepared_by_id[row["product_id"]]["sku"] not in excluded_skus]
    bundles: list[dict[str, Any]] = []
    for theme, count in themes.items():
        if theme not in BUNDLE_DEFINITIONS:
            raise ValueError(f"Unknown bundle theme: {theme}")
        for index in range(count):
            palette_name, palette_description = bundle_palette(theme, index)
            options: list[dict[str, Any]] = []
            for option_name, terms in BUNDLE_DEFINITIONS[theme]:
                candidates = [row for row in eligible if class_matches(row, terms)]
                if not candidates:
                    raise ValueError(f"No eligible products for {theme} bundle option {option_name}")
                candidates.sort(
                    key=lambda row: component_score(
                        row,
                        prepared_by_id[row["product_id"]],
                        palette_description,
                        theme,
                        index,
                    )
                )
                selections = []
                for row in candidates[: min(3, len(candidates))]:
                    prepared = prepared_by_id[row["product_id"]]
                    selections.append(
                        {
                            "sku": prepared["sku"],
                            "name": prepared["name"],
                            "price": prepared["price"],
                            "source_product_id": row["product_id"],
                        }
                    )
                options.append({"name": option_name, "required": True, "type": "dropdown", "selections": selections})
            bundle_number = len(bundles) + 1
            series = ("Essentials", "Edit", "Suite", "Gathering", "Select")[index % 5]
            name = f"{palette_name} {theme} {series}"
            bundle_sku = f"WANDS-BUNDLE-{bundle_number:03d}"
            option_names = ", ".join(option["name"].lower() for option in options)
            description = (
                f"<p>{name} brings together {palette_description} for a cohesive {theme.lower()} setup. "
                f"Choose a {option_names} to tailor the collection to your room.</p>"
                "<p>Each selection is an existing catalog product with its own price and product details. "
                "The collection price updates from the components selected.</p>"
            )
            bundles.append(
                {
                    "sku": bundle_sku,
                    "name": name,
                    "theme": theme,
                    "palette": palette_name,
                    "description": description,
                    "short_description": f"A configurable {theme.lower()} collection in {palette_description}.",
                    "url_key": f"wands-bundle-{bundle_number:03d}-{slug(name)}",
                    "options": options,
                }
            )
    return bundles


def build_plan(
    source_rows: list[dict[str, str]],
    prepared_rows: list[dict[str, str]],
    config: PlanConfig | None = None,
) -> dict[str, Any]:
    config = config or PlanConfig()
    prepared_by_id = {row["wands_product_id"]: row for row in prepared_rows}
    if len(prepared_by_id) != len(prepared_rows):
        raise ValueError("Prepared product IDs are not unique")
    source_ids = {row["product_id"] for row in source_rows}
    missing = source_ids - prepared_by_id.keys()
    if missing:
        raise ValueError(f"Prepared catalog is missing {len(missing)} source product IDs")

    candidates: dict[str, list[dict[str, str]]] = {group: [] for group in config.group_quotas}
    for row in source_rows:
        group = product_group(row)
        if group in candidates and is_merchandising_candidate(row, group):
            candidates[group].append(row)

    families: list[dict[str, Any]] = []
    for group, quota in config.group_quotas.items():
        group_candidates = candidates[group]
        group_candidates.sort(key=lambda row: (
            candidate_name_penalty(row),
            stable_key(row["product_id"], f"candidate:{group}:{PLAN_VERSION}"),
        ))
        if len(group_candidates) < quota:
            raise ValueError(f"Group {group} has {len(group_candidates)} candidates but needs {quota}")
        one_axis_quota = config.one_axis_quotas.get(group, 0)
        if one_axis_quota > quota:
            raise ValueError(f"One-axis quota exceeds total quota for {group}")
        for position, source in enumerate(group_candidates[:quota]):
            families.append(plan_family(source, prepared_by_id[source["product_id"]], position < one_axis_quota))

    deduplicate_family_names(families)

    existing_skus = {row["sku"] for row in prepared_rows}
    parent_skus = {family["parent"]["sku"] for family in families}
    child_skus = [variant["sku"] for family in families for variant in family["variants"]]
    if len(child_skus) != len(set(child_skus)):
        raise ValueError("Generated configurable child SKUs are not unique")
    if existing_skus & set(child_skus):
        raise ValueError("Generated configurable child SKUs collide with existing SKUs")

    bundles = build_bundles(source_rows, prepared_by_id, parent_skus, config.bundle_themes)
    bundle_skus = {bundle["sku"] for bundle in bundles}
    if existing_skus & bundle_skus or set(child_skus) & bundle_skus:
        raise ValueError("Generated bundle SKUs collide with another product")

    return {
        "schema_version": SCHEMA_VERSION,
        "plan_version": PLAN_VERSION,
        "families": families,
        "bundles": bundles,
        "attribute_options": ATTRIBUTE_OPTIONS,
    }


def csv_row(values: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    return {field: values.get(field, "") for field in fields}


def write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for row in rows:
            writer.writerow(csv_row(row, fields))


def configurable_parent_row(family: dict[str, Any]) -> dict[str, Any]:
    parent = dict(family["parent"])
    variations = []
    for variant in family["variants"]:
        pairs = [f"sku={variant['sku']}"]
        pairs.extend(f"{attribute}={value}" for attribute, value in variant["options"].items())
        variations.append(",".join(pairs))
    parent["configurable_variations"] = "|".join(variations)
    parent["configurable_variation_labels"] = ",".join(
        f"{axis['attribute']}={axis['label']}" for axis in family["axes"]
    )
    return parent


def bundle_csv_row(bundle: dict[str, Any]) -> dict[str, Any]:
    values = []
    for option in bundle["options"]:
        for position, selection in enumerate(option["selections"]):
            values.append(
                ",".join(
                    (
                        f"name={option['name']}",
                        f"type={option['type']}",
                        f"required={1 if option['required'] else 0}",
                        f"sku={selection['sku']}",
                        "price=0",
                        f"default={1 if position == 0 else 0}",
                        "default_qty=1",
                        "price_type=fixed",
                        "can_change_qty=0",
                    )
                )
            )
    return {
        "sku": bundle["sku"],
        "store_view_code": "",
        "attribute_set_code": "Default",
        "product_type": "bundle",
        "categories": f"WANDS Catalog/Room Bundles/{bundle['theme']}",
        "product_websites": "wands",
        "name": bundle["name"],
        "description": bundle["description"],
        "short_description": bundle["short_description"],
        "weight": "",
        "product_online": "1",
        "tax_class_name": "Taxable Goods",
        "visibility": "Catalog, Search",
        "price": "",
        "url_key": bundle["url_key"],
        "meta_title": bundle["name"][:255],
        "meta_description": re.sub(r"<[^>]+>", " ", bundle["short_description"])[:255],
        "qty": "0",
        "out_of_stock_qty": "0",
        "use_config_min_qty": "1",
        "is_in_stock": "1",
        "manage_stock": "0",
        "use_config_manage_stock": "1",
        "wands_product_id": "",
        "wands_product_class": "Room Bundle",
        "wands_average_rating": "",
        "wands_review_count": "",
        "lab_price_method": "dynamic-component-sum",
        "lab_price_version": PLAN_VERSION,
        "lab_price_synthetic": "Yes",
        "bundle_price_type": "dynamic",
        "bundle_sku_type": "dynamic",
        "bundle_price_view": "Price range",
        "bundle_weight_type": "dynamic",
        "bundle_shipment_type": "together",
        "bundle_values": "|".join(values),
    }


def image_prompts(plan: dict[str, Any]) -> Iterable[dict[str, Any]]:
    visual_attributes = {"color", "wands_finish", "wands_material"}
    for family in plan["families"]:
        visual_axis = next((axis for axis in family["axes"] if axis["attribute"] in visual_attributes), None)
        if visual_axis is None:
            continue
        parent = family["parent"]
        for value in visual_axis["values"]:
            output_stem = f"{parent['sku']}-{slug(value).upper()[:20]}"
            skus = [
                variant["sku"]
                for variant in family["variants"]
                if variant["options"].get(visual_axis["attribute"]) == value
            ]
            yield {
                "sku": skus[0],
                "skus": skus,
                "parent_sku": parent["sku"],
                "attribute": visual_axis["attribute"],
                "value": value,
                "title": parent["name"],
                "seed": int(stable_fraction(parent["sku"], f"variant-image:{value}") * (2**31 - 1)),
                "prompt": (
                    f"Commercial ecommerce product photography of one {parent['name']} in {value}. "
                    "Centered three-quarter view on a seamless warm-white studio background, soft natural shadow, "
                    "realistic materials and proportions, sharp catalog photography. No people, no room scene, "
                    "no packaging. No visible text, logos, watermarks, or duplicate objects."
                ),
                "output_file": f"{output_stem}.jpg",
            }


def parent_image_reuse_rows(plan: dict[str, Any]) -> Iterable[dict[str, str]]:
    visual_attributes = {"color", "wands_finish", "wands_material"}
    for family in plan["families"]:
        if any(axis["attribute"] in visual_attributes for axis in family["axes"]):
            continue
        source_path = f"/wands/{family['parent']['sku']}.jpg"
        for variant in family["variants"]:
            yield {
                "sku": variant["sku"],
                "base_image": source_path,
                "small_image": source_path,
                "thumbnail": source_path,
            }


def description_prompts(plan: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for family in plan["families"]:
        axes = ", ".join(f"{axis['label']}: {', '.join(axis['values'])}" for axis in family["axes"])
        yield {
            "id": family["parent"]["sku"],
            "kind": "configurable_parent",
            "current_description": family["parent"]["description"],
            "prompt": (
                f"Write an original ecommerce product description for {family['parent']['name']}. "
                f"Product class: {family['parent']['wands_product_class']}. Options: {axes}. "
                "Use only these facts. Return one short HTML description with two paragraphs. "
                "Do not invent certifications, compatibility, construction details, warranties, or performance claims."
            ),
        }
    for bundle in plan["bundles"]:
        groups = ", ".join(option["name"] for option in bundle["options"])
        yield {
            "id": bundle["sku"],
            "kind": "bundle",
            "current_description": bundle["description"],
            "prompt": (
                f"Write an original ecommerce description for {bundle['name']}. Theme: {bundle['theme']}. "
                f"Palette: {bundle['palette']}. Component groups: {groups}. Return two short HTML paragraphs. "
                "State that selections determine the final price. Do not invent product specifications or claims."
            ),
        }


def validate_plan(plan: dict[str, Any]) -> None:
    parents = [family["parent"]["sku"] for family in plan["families"]]
    children = [variant["sku"] for family in plan["families"] for variant in family["variants"]]
    bundles = [bundle["sku"] for bundle in plan["bundles"]]
    all_generated = parents + children + bundles
    if len(all_generated) != len(set(all_generated)):
        raise ValueError("Plan contains duplicate product SKUs")
    for family in plan["families"]:
        expected = 4 if family["one_axis"] else 6
        if len(family["variants"]) != expected:
            raise ValueError(f"{family['parent']['sku']} has {len(family['variants'])} variants, expected {expected}")
        combinations = [tuple(variant["options"].items()) for variant in family["variants"]]
        if len(combinations) != len(set(combinations)):
            raise ValueError(f"{family['parent']['sku']} has duplicate option combinations")
        for variant in family["variants"]:
            for attribute, value in variant["options"].items():
                if value not in ATTRIBUTE_OPTIONS[attribute]:
                    raise ValueError(f"Unknown option {attribute}={value}")
    parent_set = set(parents)
    child_set = set(children)
    for bundle in plan["bundles"]:
        if not 3 <= len(bundle["options"]) <= 5:
            raise ValueError(f"{bundle['sku']} must have 3 to 5 option groups")
        selections = {
            selection["sku"]
            for option in bundle["options"]
            for selection in option["selections"]
        }
        if selections & (parent_set | child_set):
            raise ValueError(f"{bundle['sku']} references a configurable parent or generated child")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def conversion_record(family: dict[str, Any]) -> dict[str, Any]:
    return {
        "sku": family["parent"]["sku"],
        "source_product_id": family["source_product_id"],
        "expected_type": "simple",
        "target_type": "configurable",
        "child_skus": [variant["sku"] for variant in family["variants"]],
    }


def select_pilot_families(families: list[dict[str, Any]], limit: int = 25) -> list[dict[str, Any]]:
    if len(families) <= limit:
        return list(families)

    selected: list[dict[str, Any]] = []
    selected_skus: set[str] = set()
    seen_two_axis_signatures: set[tuple[str, tuple[str, ...]]] = set()
    group_order = list(dict.fromkeys(family["group"] for family in families))

    for family in families:
        if family["one_axis"]:
            continue
        signature = (
            family["group"],
            tuple(axis["attribute"] for axis in family["axes"]),
        )
        if signature in seen_two_axis_signatures:
            continue
        seen_two_axis_signatures.add(signature)
        selected.append(family)
        selected_skus.add(family["parent"]["sku"])
        if len(selected) == limit:
            return selected

    for group in group_order:
        family = next(
            (
                candidate
                for candidate in families
                if candidate["group"] == group
                and candidate["one_axis"]
                and candidate["parent"]["sku"] not in selected_skus
            ),
            None,
        )
        if family is None:
            continue
        selected.append(family)
        selected_skus.add(family["parent"]["sku"])
        if len(selected) == limit:
            return selected

    remaining_by_group = {
        group: [
            family
            for family in families
            if family["group"] == group and family["parent"]["sku"] not in selected_skus
        ]
        for group in group_order
    }
    while len(selected) < limit:
        added = False
        for group in group_order:
            if not remaining_by_group[group]:
                continue
            family = remaining_by_group[group].pop(0)
            selected.append(family)
            selected_skus.add(family["parent"]["sku"])
            added = True
            if len(selected) == limit:
                break
        if not added:
            break

    return selected


def write_pilot(plan: dict[str, Any], batch_root: Path, output_dir: Path) -> dict[str, Any]:
    pilot_root = batch_root / "pilot"
    configurable_root = pilot_root / "configurables"
    configurable_root.mkdir(parents=True, exist_ok=True)
    pilot_families = select_pilot_families(plan["families"])
    pilot_bundles = plan["bundles"][:5]
    pilot_plan = {"families": pilot_families}

    children_path = configurable_root / "children.csv"
    parents_path = configurable_root / "parents.csv"
    conversions_path = configurable_root / "parent-type-conversions.jsonl"
    image_prompts_path = configurable_root / "image-prompts.jsonl"
    reuse_media_path = configurable_root / "reuse-parent-media.csv"
    bundles_path = pilot_root / "bundles.csv"

    write_csv(
        children_path,
        CONFIGURABLE_CSV_FIELDS,
        (variant for family in pilot_families for variant in family["variants"]),
    )
    write_csv(
        parents_path,
        CONFIGURABLE_CSV_FIELDS,
        (configurable_parent_row(family) for family in pilot_families),
    )
    write_jsonl(conversions_path, (conversion_record(family) for family in pilot_families))
    write_jsonl(image_prompts_path, image_prompts(pilot_plan))
    write_csv(
        reuse_media_path,
        ["sku", "base_image", "small_image", "thumbnail"],
        parent_image_reuse_rows(pilot_plan),
    )
    write_csv(bundles_path, BUNDLE_CSV_FIELDS, (bundle_csv_row(bundle) for bundle in pilot_bundles))

    pilot_manifest = {
        "schema_version": SCHEMA_VERSION,
        "families": len(pilot_families),
        "children": sum(len(family["variants"]) for family in pilot_families),
        "bundles": len(pilot_bundles),
    }
    for key, path in (
        ("children_csv", children_path),
        ("parents_csv", parents_path),
        ("conversions_jsonl", conversions_path),
        ("image_prompts_jsonl", image_prompts_path),
        ("reuse_parent_media_csv", reuse_media_path),
        ("bundles_csv", bundles_path),
    ):
        pilot_manifest[key] = str(path.relative_to(output_dir))
        pilot_manifest[f"{key}_sha256"] = sha256(path)

    manifest_path = pilot_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(pilot_manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "manifest": str(manifest_path.relative_to(output_dir)),
        "manifest_sha256": sha256(manifest_path),
        **pilot_manifest,
    }


def write_batches(plan: dict[str, Any], output_dir: Path, family_batch_size: int = 100) -> dict[str, Any]:
    batch_root = output_dir / "batches"
    pilot = write_pilot(plan, batch_root, output_dir)
    configurable_manifests: list[dict[str, Any]] = []
    families = plan["families"]
    for batch_number, start in enumerate(range(0, len(families), family_batch_size), start=1):
        batch_families = families[start : start + family_batch_size]
        batch_dir = batch_root / "configurables" / f"batch-{batch_number:03d}"
        batch_dir.mkdir(parents=True, exist_ok=True)
        children_path = batch_dir / "children.csv"
        parents_path = batch_dir / "parents.csv"
        conversions_path = batch_dir / "parent-type-conversions.jsonl"
        write_csv(
            children_path,
            CONFIGURABLE_CSV_FIELDS,
            (variant for family in batch_families for variant in family["variants"]),
        )
        write_csv(
            parents_path,
            CONFIGURABLE_CSV_FIELDS,
            (configurable_parent_row(family) for family in batch_families),
        )
        write_jsonl(conversions_path, (conversion_record(family) for family in batch_families))
        configurable_manifests.append(
            {
                "batch": batch_number,
                "family_offset": start,
                "families": len(batch_families),
                "children": sum(len(family["variants"]) for family in batch_families),
                "children_csv": str(children_path.relative_to(output_dir)),
                "children_csv_sha256": sha256(children_path),
                "parents_csv": str(parents_path.relative_to(output_dir)),
                "parents_csv_sha256": sha256(parents_path),
                "conversions_jsonl": str(conversions_path.relative_to(output_dir)),
                "conversions_jsonl_sha256": sha256(conversions_path),
            }
        )

    bundle_manifests: list[dict[str, Any]] = []
    bundles_by_theme: dict[str, list[dict[str, Any]]] = {}
    for bundle in plan["bundles"]:
        bundles_by_theme.setdefault(bundle["theme"], []).append(bundle)
    for batch_number, (theme, bundles) in enumerate(bundles_by_theme.items(), start=1):
        path = batch_root / "bundles" / f"batch-{batch_number:03d}-{slug(theme)}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        write_csv(path, BUNDLE_CSV_FIELDS, (bundle_csv_row(bundle) for bundle in bundles))
        bundle_manifests.append(
            {
                "batch": batch_number,
                "theme": theme,
                "bundles": len(bundles),
                "csv": str(path.relative_to(output_dir)),
                "csv_sha256": sha256(path),
            }
        )

    batch_manifest = {
        "schema_version": SCHEMA_VERSION,
        "family_batch_size": family_batch_size,
        "pilot": pilot,
        "configurable_batches": configurable_manifests,
        "bundle_batches": bundle_manifests,
    }
    batch_manifest_path = batch_root / "manifest.json"
    batch_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    batch_manifest_path.write_text(
        json.dumps(batch_manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "configurable_batches": len(configurable_manifests),
        "bundle_batches": len(bundle_manifests),
        "pilot_families": pilot["families"],
        "pilot_children": pilot["children"],
        "pilot_bundles": pilot["bundles"],
        "pilot_manifest": pilot["manifest"],
        "pilot_manifest_sha256": pilot["manifest_sha256"],
        "batch_manifest": str(batch_manifest_path.relative_to(output_dir)),
        "batch_manifest_sha256": sha256(batch_manifest_path),
    }


def write_plan(
    plan: dict[str, Any],
    output_dir: Path,
    source_path: Path | None = None,
    prepared_path: Path | None = None,
) -> dict[str, Any]:
    validate_plan(plan)
    output_dir.mkdir(parents=True, exist_ok=True)
    families_path = output_dir / "configurable-families.jsonl"
    conversions_path = output_dir / "parent-type-conversions.jsonl"
    children_path = output_dir / "configurable-children.csv"
    parents_path = output_dir / "configurable-parents.csv"
    bundles_path = output_dir / "bundles.csv"
    image_prompts_path = output_dir / "image-prompts.jsonl"
    description_prompts_path = output_dir / "description-prompts.jsonl"
    rollback_parents_path = output_dir / "rollback-parents.csv"
    rollback_bundles_path = output_dir / "rollback-disable-bundles.csv"
    parent_image_reuse_path = output_dir / "reuse-parent-media.csv"

    write_jsonl(families_path, plan["families"])
    write_jsonl(
        conversions_path,
        (conversion_record(family) for family in plan["families"]),
    )
    write_csv(
        children_path,
        CONFIGURABLE_CSV_FIELDS,
        (variant for family in plan["families"] for variant in family["variants"]),
    )
    write_csv(parents_path, CONFIGURABLE_CSV_FIELDS, (configurable_parent_row(family) for family in plan["families"]))
    write_csv(bundles_path, BUNDLE_CSV_FIELDS, (bundle_csv_row(bundle) for bundle in plan["bundles"]))
    write_jsonl(image_prompts_path, image_prompts(plan))
    write_jsonl(description_prompts_path, description_prompts(plan))
    write_csv(
        parent_image_reuse_path,
        ["sku", "base_image", "small_image", "thumbnail"],
        parent_image_reuse_rows(plan),
    )
    write_csv(
        rollback_parents_path,
        CONFIGURABLE_CSV_FIELDS,
        (
            {
                **family["original_parent"],
                **{attribute: "" for attribute in ATTRIBUTE_LABELS},
                "configurable_variations": "",
                "configurable_variation_labels": "",
            }
            for family in plan["families"]
        ),
    )
    batch_summary = write_batches(plan, output_dir)
    write_csv(
        rollback_bundles_path,
        BUNDLE_CSV_FIELDS,
        (
            {
                **bundle_csv_row(bundle),
                "product_online": "0",
                "visibility": "Not Visible Individually",
            }
            for bundle in plan["bundles"]
        ),
    )

    group_counts = Counter(family["group"] for family in plan["families"])
    one_axis = sum(family["one_axis"] for family in plan["families"])
    child_count = sum(len(family["variants"]) for family in plan["families"])
    image_count = sum(1 for _ in image_prompts(plan))
    parent_image_reuse_count = sum(1 for _ in parent_image_reuse_rows(plan))
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "plan_version": PLAN_VERSION,
        "source_products": str(source_path.resolve()) if source_path else None,
        "prepared_products": str(prepared_path.resolve()) if prepared_path else None,
        "configurable_parents": len(plan["families"]),
        "one_axis_parents": one_axis,
        "two_axis_parents": len(plan["families"]) - one_axis,
        "simple_children": child_count,
        "bundle_products": len(plan["bundles"]),
        "variant_image_prompts": image_count,
        "children_reusing_parent_image": parent_image_reuse_count,
        "visible_products_after_apply": 42994 + len(plan["bundles"]),
        "total_product_entities_after_apply": 42994 + child_count + len(plan["bundles"]),
        "group_counts": dict(group_counts),
        "bundle_theme_counts": dict(Counter(bundle["theme"] for bundle in plan["bundles"])),
        "attribute_options": plan["attribute_options"],
        **batch_summary,
    }
    if source_path:
        manifest["source_products_sha256"] = sha256(source_path)
    if prepared_path:
        manifest["prepared_products_sha256"] = sha256(prepared_path)
    for key, path in (
        ("configurable_families_jsonl_sha256", families_path),
        ("parent_type_conversions_jsonl_sha256", conversions_path),
        ("configurable_children_csv_sha256", children_path),
        ("configurable_parents_csv_sha256", parents_path),
        ("bundles_csv_sha256", bundles_path),
        ("image_prompts_jsonl_sha256", image_prompts_path),
        ("description_prompts_jsonl_sha256", description_prompts_path),
        ("rollback_parents_csv_sha256", rollback_parents_path),
        ("rollback_disable_bundles_csv_sha256", rollback_bundles_path),
        ("reuse_parent_media_csv_sha256", parent_image_reuse_path),
    ):
        manifest[key] = sha256(path)
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def scaled_config(configurable_count: int, bundle_count: int) -> PlanConfig:
    if configurable_count != sum(DEFAULT_GROUP_QUOTAS.values()):
        raise ValueError("Only the reviewed 2,000-parent distribution is supported")
    if bundle_count != sum(DEFAULT_BUNDLE_THEMES.values()):
        raise ValueError("Only the reviewed 50-bundle distribution is supported")
    return PlanConfig()


def read_rows(path: Path, delimiter: str) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter=delimiter))


def main() -> int:
    arguments = parse_args()
    config = scaled_config(arguments.configurable_count, arguments.bundle_count)
    source_rows = read_rows(arguments.source_products, "\t")
    prepared_rows = read_rows(arguments.prepared_products, ",")
    plan = build_plan(source_rows, prepared_rows, config)
    manifest = write_plan(plan, arguments.output_dir, arguments.source_products, arguments.prepared_products)
    print(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
