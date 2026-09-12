"""Versioned synthetic lab rules. No market-price or manufacturer claims."""
import re
from build_realism_review import PROFILES, clean_title
from prepare_catalog import department, parse_features, stable_fraction, normalized_text

VERSION = "wands-realism-v2"
ANCHORS = {key.casefold(): value[1] for key, value in PROFILES.items()}
ANCHORS.update({
    "sofas": 950, "sectionals": 1600, "loveseats": 650, "recliners": 550,
    "dining chairs": 150, "dining table sets": 900, "sofa & console tables": 250,
    "dressers & chests": 550, "nightstands": 170, "bookcases": 240,
    "sideboards & buffets": 600, "accent chests / cabinets": 300, "bar cabinets": 400,
    "office storage cabinets": 280, "tv stands & entertainment centers": 320,
    "headboards": 240, "bed frames": 160, "daybeds & guest beds": 480,
    "foam and latex mattresses": 550, "innerspring mattresses": 650, "adjustable beds": 1000,
    "mattress toppers and pads": 80, "standard bed pillows": 30,
    "ottomans": 140, "benches": 200, "living room sets": 1800,
    "living room table sets": 450, "indoor chaise lounges": 400,
    "armoires & wardrobes": 600, "kitchen islands": 500, "pantry cabinets": 280,
    "patio dining sets": 1000, "patio tables": 230, "patio bar stools": 170,
    "patio chaise lounges": 320, "patio rockers & gliders": 250,
    "patio benches": 240, "outdoor rugs": 120, "deck boxes": 140,
    "sheds": 1100, "greenhouses": 500, "pergolas": 1100, "awnings": 350,
    "outdoor fireplaces": 350, "fountains": 220, "garden accents": 45,
    "planter accessories": 25, "patio umbrella stands & bases": 60,
    "wall clocks": 50, "faux florals": 35, "faux plants and trees": 80,
    "picture frames": 25, "candle holders": 25, "wall stickers": 25,
    "furniture cushions": 55, "furniture covers": 60,
    "floor lamps": 130, "pendant lights": 160, "flush mount lighting": 100,
    "outdoor wall lights": 90, "landscape lighting": 60, "under cabinet lighting": 40,
    "ceiling fans": 200, "lighting shades": 40, "fixture parts and components": 25,
    "outdoor lanterns & lamps": 50, "cabinet lighting": 35,
    "bath rugs & mats": 30, "vanity bases": 500, "bathroom sinks": 160,
    "kitchen sinks": 250, "kitchen faucets": 180, "shower faucets & systems": 240,
    "shower heads": 65, "shower & tub doors": 550, "tubs and whirlpools": 1100,
    "shower & tub accessories": 35, "toilet paper holders": 25, "towel & robe hooks": 20,
    "towel bars, racks, and stands": 45, "molding & millwork": 35, "wall paneling": 80,
    "door levers": 40, "barn door hardware": 120, "mailboxes": 80,
    "canisters & jars": 30, "mugs & teacups": 20, "cooking utensils": 15,
    "dining linens": 35, "strainers, colanders, & salad spinners": 25,
    "flatware & silverware serving pieces": 20, "specialty serving": 35,
    "refrigerators": 1000, "range hoods": 320,
    "coat racks and hooks": 60, "hall trees": 240, "shelving & racks": 100,
    "carts & stands": 90, "clothing & garment racks": 65,
    "trash cans & recycling": 55, "closet storage & organization": 90,
    "bike and sport racks": 90, "jewelry boxes": 45, "safes": 150,
    "kids dressers & chests": 320, "kids bookcases": 130,
    "toy boxes and organizers": 70, "cribs": 280, "cat beds": 55,
    "dog beds & mats": 65, "pet gates": 75, "bird cages": 120,
    "dog and cat bowls, feeders & accessories": 30, "cat condos & cat trees": 95,
})
DEPT_BASE = {"Furniture": 250, "Kitchen & Tabletop": 35, "Home Improvement": 65,
             "Décor & Pillows": 45, "Outdoor": 110, "Storage & Organization": 65,
             "Bed & Bath": 45, "Baby & Kids": 65, "Lighting": 100, "Rugs": 100,
             "Appliances": 300, "Pet": 50, "Commercial Business Furniture": 300}
CLASS_FAMILIES = [
    (r"accessories|parts|hardware|hooks|holders|knobs|pulls|replacement", 25),
    (r"sets", 160), (r"sofas|sectionals", 1000), (r"mattresses", 500),
    (r"chairs|stools", 180), (r"tables|desks", 250), (r"cabinets|dressers|wardrobes", 350),
    (r"beds|daybeds", 450), (r"rugs|carpets", 120), (r"pillows|cushions|covers", 35),
    (r"lamps|lights|lighting|sconces", 95), (r"storage|shelves|racks|organizers", 65),
    (r"curtains|drapes|bedding|sheets|blankets|quilts", 55),
    (r"art|decor|décor|statues|sculptures|ornaments", 45),
    (r"plates|bowls|cups|mugs|utensils|pans|dishes|bottles", 25),
]
COLLECTIONS = {
    "Furniture": ("Alder Cove", "Warm contemporary furniture"),
    "Décor & Pillows": ("Alder Cove", "Warm contemporary accents"),
    "Lighting": ("Morrow Grid", "Practical contemporary lighting"),
    "Home Improvement": ("Morrow Grid", "Everyday fixtures and finishes"),
    "Storage & Organization": ("Morrow Grid", "Practical home organization"),
    "Rugs": ("Field & Loom", "Textured home textiles"),
    "Bed & Bath": ("Field & Loom", "Everyday bed and bath"),
    "Kitchen & Tabletop": ("Hearth & Table", "Everyday kitchen and dining"),
    "Outdoor": ("Openstead", "Outdoor living"),
    "Baby & Kids": ("Little Grove", "Children's spaces"),
    "Pet": ("Pawstead", "Pet home essentials"),
    "Appliances": ("Morrow Grid", "Home appliances"),
    "Commercial Business Furniture": ("Morrow Grid", "Workspace essentials"),
}
COLORS = "beige black blue brown cream gray grey green ivory navy natural red terracotta white silver plum yellow orange pink purple gold teal charcoal burgundy taupe espresso walnut oak bronze brass chrome".split()


def class_tokens(value):
    return {v.strip().casefold() for v in value.split("|") if v.strip()}


def price(row):
    classes = [v.strip().casefold() for v in row.get("product_class", "").split("|") if v.strip()]
    taxonomy = [v.strip().casefold() for v in row.get("category hierarchy", "").split("/")][::-1]
    matched = next((c for c in classes if c in ANCHORS), None)
    basis, flags = "class", []
    if matched is None:
        matched = next((c for c in taxonomy if c in ANCHORS), None)
        basis = "taxonomy"
    if matched:
        anchor = ANCHORS[matched]
    else:
        family = next(((pattern, value) for pattern, value in CLASS_FAMILIES if any(re.search(r"\b(?:" + pattern + r")\b", c) for c in (classes or taxonomy[:1]))), None)
        anchor = family[1] if family else DEPT_BASE.get(department(row), 65)
        matched = family[0] if family else department(row)
        basis = "class_family" if family else "department"
        flags.append("broad_synthetic_anchor")
    name = row.get("product_name", "").casefold()
    # Subtypes are considered only inside their class, never across unrelated classes.
    if "sheets and sheet sets" in classes and "pillowcase" in name:
        anchor, matched = 20, "pillowcase within Sheets And Sheet Sets"
    if "accent pillows" in classes and "cover" in name:
        anchor, matched = 22, "pillow cover within Accent Pillows"
    features = parse_features(row.get("product_features", ""))
    title_counts = [int(n) for n in re.findall(r"(?:pack|set) of (\d+)\b", name)]
    title_counts += [int(n) for n in re.findall(r"\b(\d+)[ -]+(?:pack|piece)\b", name)]
    feature_counts = [int(v) for v in features.get("numberofpiecesincluded", []) if v.isdigit()]
    counts = set(title_counts + feature_counts)
    qty = next(iter(counts)) if len(counts) == 1 and 1 <= next(iter(counts)) <= 100 else 1
    # Per-piece classes only. Furniture/bedding/room sets already have a set anchor.
    per_piece = bool(set(classes) & {"cabinet and drawer knobs", "cabinet and drawer pulls", "light bulbs", "dining chairs", "bar stools", "plates & saucers", "dining bowls", "mugs & teacups"})
    if len(counts) > 1:
        flags.append("sale_quantity_conflict" if per_piece else "composition_conflict_withheld")
    quantity_multiplier = qty * (1 if qty == 1 else .9) if per_piece else 1
    material_values = {v.casefold() for key in ("primarymaterial", "material", "framematerial") for v in features.get(key, [])}
    premium = 1
    if len(material_values) == 1:
        material = next(iter(material_values))
        premium = {"solid wood": 1.2, "genuine leather": 1.3, "marble": 1.3, "manufactured wood": .85}.get(material, 1)
    amount = anchor * quantity_multiplier * premium * (.92 + .16 * stable_fraction(row["product_id"], VERSION + ":price"))
    step = 1 if amount < 50 else 5 if amount < 200 else 10 if amount < 1000 else 25
    amount = max(4.99, round(amount / step) * step - .01)
    return {"amount": round(amount, 2), "anchor": anchor, "basis": basis, "rule": matched,
            "sale_quantity": qty, "sale_unit": "pack" if per_piece and qty > 1 else "catalog item",
            "quantity_priced": per_piece, "synthetic": True, "currency": "USD", "flags": flags}


def brand(row):
    features = parse_features(row.get("product_features", ""))
    explicit = {v for key in ("brand", "manufacturer", "brandname") for v in features.get(key, [])}
    collection, direction = COLLECTIONS.get(department(row), ("Morrow Grid", "Everyday home essentials"))
    return {"collection": collection, "direction": direction, "fictional_collection": True,
            "source_brand": next(iter(explicit)) if len(explicit) == 1 else None,
            "policy": "Fictional lab collection only; source brand and manufacturer are not replaced"}


def stock(sku):
    n = stable_fraction(sku, VERSION + ":stock")
    scenario = "in_stock" if n < .80 else "low_stock" if n < .92 else "out_of_stock"
    qty = 12 + int(n * 70) if scenario == "in_stock" else 1 + int(n * 3) if scenario == "low_stock" else 0
    return {"scenario": scenario, "qty": str(qty), "is_in_stock": str(int(qty > 0)),
            "manage_stock": "1", "use_config_manage_stock": "0", "backorders": "0",
            "use_config_backorders": "0", "synthetic": True,
            "clearance": qty > 0 and stable_fraction(sku, VERSION + ":clearance") < .08}


def title(row, axes, facts):
    value = clean_title(row, facts)
    if axes & {"color", "wands_finish"}:
        value = re.sub(r"\b(?:" + "|".join(COLORS) + r")\b", "", value, flags=re.I)
        value = re.sub(r"\s*/\s*(?=\s|$)|(?<=\s)/\s*", " ", value)
    if "wands_material" in axes:
        value = re.sub(r"\b(?:solid wood|engineered wood|faux leather|leather|velvet|cotton|polyester|wool|linen blend)\b", "", value, flags=re.I)
    if "wands_size" in axes:
        value = re.sub(r"\b(?:twin|full|queen|king|small|medium|large|extra large)\b", "", value, flags=re.I)
    if axes & {"wands_length", "wands_size", "wands_seat_height"}:
        value = re.sub(r"\b\d+(?:\.\d+)?\s*(?:inches|inch|in\b|ft\b|cm\b|mm\b|''|\")", "", value, flags=re.I)
    value = normalized_text(value).strip(" /,-")
    return value or normalized_text(row["product_name"]).title()


def bundle_eligible(row, theme, option, allowed):
    classes = class_tokens(row["product_class"])
    if not classes.intersection(c.casefold() for c in allowed):
        return False
    combined = " ".join(classes)
    if theme in {"Home Office", "Living Room", "Dining", "Reading Nook"} and re.search(r"\bkids|\bcrib|\bpatio|\boutdoor", combined):
        return False
    if theme == "Patio" and option == "Outdoor Rug":
        values = parse_features(row.get("product_features", ""))
        evidence = " ".join(values.get("indooroutdooruse", []) + values.get("location", []))
        if "outdoor" not in combined and "outdoor" not in evidence.casefold():
            return False
    if theme == "Pet Corner" and option == "Pet Bed" and re.search(r"ottoman|wooden bed|dog house", row["product_name"], re.I):
        return False
    return True
