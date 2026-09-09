"""Explicit, deterministic lab-design assumptions, never recovered WANDS facts.

The profiles are authored fictional designs, not manufacturer specifications or
statistical estimates. Unknown classes, incompatible options and mixed kits fail
closed. Approval covers dimension proposals only, not image identity or imports.
"""
from __future__ import annotations

import copy
import math
import re
from fractions import Fraction

from prepare_catalog import stable_fraction, parse_features

VERSION = 'wands-synthetic-dimensions-v2'
SEED_VERSION = 'wands-synthetic-dimensions-v1'  # Preserve already-reviewed geometry.
LABEL = 'Synthetic lab dimension, not a manufacturer measurement'
ORIGIN = 'approved synthetic lab dimension'
PREFIX = 'lab_spec_'
COMPLETE_STATUSES = {'synthetic_design_complete','synthetic_components_complete'}
GEOMETRY_AXES = {'wands_size', 'wands_length', 'wands_seat_height',
                 'wands_seating_capacity', 'wands_piece_count', 'wands_pack_size', 'wands_light_count'}


def profile(scope, **dimensions):
    return {'scope': scope, 'dimensions': dimensions}


# Centimetre design anchors. Uniform family-level variation preserves proportions;
# selected numeric options override the relevant anchor exactly, without jitter.
PROFILES = {
    'rug': profile('one rug, laid flat', width=152.4, length=213.36, pile_height=0.8),
    'mat': profile('one mat, laid flat', width=45.72, length=76.2, pile_height=0.8),
    'tile': profile('one tile, not the pack', width=30.48, length=30.48, height=1),
    'pillow': profile('one pillow face, laid flat; thickness unspecified', width=45.72, length=45.72),
    'curtain': profile('one curtain panel, laid flat; not the whole window', width=132, length=213.36),
    'shower_curtain': profile('one curtain, laid flat; accessories excluded', width=180, length=180),
    'bedding': profile('primary duvet cover or comforter, laid flat; other set pieces unspecified', width=228.6, length=233.68),
    'bed': profile('assumed assembled bed-frame envelope; not mattress fit or clearance', width=160.4, length=215.2, height=100),
    'bed_base': profile('assumed bed base in flat position; not mattress fit or moving clearance', width=156.4, length=207.2, height=38),
    'headboard': profile('headboard envelope; mounting and mattress fit unspecified', width=160.4, depth=10, height=125),
    'armchair': profile('one chair in upright position', width=82, depth=85, height=88, seat_width=54, seat_depth=52, seat_height=45),
    'dining_chair': profile('one chair', width=50, depth=57, height=88, seat_width=44, seat_depth=43, seat_height=46),
    'office_chair': profile('one chair at an assumed fixed adjustment', width=65, depth=66, height=112, seat_width=49, seat_depth=47, seat_height=47),
    'stool': profile('one stool at the selected seat height', width=46, depth=46, height=91, seat_width=36, seat_depth=36, seat_height=66),
    'kids_chair': profile('one fictional child-sized chair; no age or safety suitability claim', width=50, depth=55, height=58, seat_width=35, seat_depth=34, seat_height=30),
    'kids_sofa': profile('one fictional child-sized sofa; no age or safety suitability claim', width=82, depth=55, height=58, seat_width=67, seat_depth=34, seat_height=30),
    'floor_chair': profile('one floor chair in an assumed upright position', width=55, depth=75, height=65, seat_width=45, seat_depth=48, seat_height=15),
    'bench': profile('one bench', width=110, depth=42, height=48),
    'ottoman': profile('one ottoman', width=65, depth=55, height=43),
    'coffee_table': profile('one table', width=105, depth=58, height=43),
    'console': profile('one table', width=110, depth=35, height=78),
    'side_table': profile('one table', width=50, depth=50, height=55),
    'bar_table': profile('one table', width=70, depth=70, height=105),
    'patio_table': profile('one table', width=110, depth=70, height=75),
    'desk': profile('desk envelope; chair and installation clearances unspecified', width=110, depth=55, height=75),
    'kids_desk': profile('desk envelope only; no age or safety suitability claim', width=90, depth=48, height=65),
    'nightstand': profile('one cabinet', width=50, depth=40, height=60),
    'dresser': profile('assembled cabinet envelope; drawer clearance unspecified', width=100, depth=45, height=95),
    'kids_dresser': profile('assembled cabinet envelope; no age or safety suitability claim', width=85, depth=42, height=85),
    'cabinet': profile('assembled cabinet envelope; installation and opening clearances unspecified', width=90, depth=42, height=110),
    'bookcase': profile('assembled shelf unit envelope; load rating unspecified', width=80, depth=30, height=155),
    'tv_stand': profile('assembled cabinet envelope; TV compatibility unspecified', width=110, depth=40, height=55),
    'shelf': profile('one shelf board; mounting and load rating unspecified', width=75, depth=22, height=4),
    'wall_storage': profile('assembled wall storage envelope; mounting and load rating unspecified', width=65, depth=23, height=65),
    'wardrobe': profile('assembled cabinet envelope; opening clearance unspecified', width=80, depth=50, height=165),
    'pantry': profile('assembled cabinet envelope; opening clearance unspecified', width=75, depth=40, height=150),
    'trunk': profile('closed trunk envelope', width=80, depth=40, height=45),
    'deck_box': profile('closed deck box envelope', width=110, depth=55, height=60),
    'patio_chair': profile('one chair in upright position', width=72, depth=80, height=85, seat_width=52, seat_depth=50, seat_height=43),
    'patio_chaise': profile('one chaise at an assumed fixed recline; moving clearance unspecified', width=68, depth=195, height=85, seat_width=55, seat_depth=110, seat_height=35),
    'patio_sofa': profile('one sofa', width=180, depth=82, height=82, seat_width=150, seat_depth=56, seat_height=43),
    'planter': profile('one planter exterior; capacity and drainage unspecified', width=30, depth=30, height=35),
    'floor_lamp': profile('one lamp exterior; electrical and installation specifications excluded', width=30, depth=30, height=165),
    'table_lamp': profile('one lamp exterior; electrical specifications excluded', width=30, depth=30, height=52),
    'chandelier': profile('fixture body only; suspension, wiring and installation clearance excluded', width=55, depth=55, height=50),
    'pendant': profile('fixture body only; suspension, wiring and installation clearance excluded', width=40, depth=40, height=35),
    'linear_pendant': profile('fixture body only; suspension, wiring and installation clearance excluded', width=100, depth=24, height=30),
    'sconce': profile('fixture body only; wiring and installation clearance excluded', width=30, depth=22, height=30),
    'hanger': profile('one hanger, not a multipack', width=43, depth=1, height=23),
    'mug': profile('one mug including handle; capacity unspecified', width=12, depth=9, height=10),
    'bowl': profile('one bowl exterior; capacity unspecified', width=28, depth=28, height=12),
    'roaster': profile('one pan including handles; usable cooking area and capacity unspecified', width=42, depth=30, height=9),
    'dutch_oven': profile('one pot including handles and closed lid; capacity unspecified', width=32, depth=25, height=18),
    'stock_pot': profile('one pot including handles and closed lid; capacity unspecified', width=32, depth=28, height=26),
    'grill_pan': profile('one pan including handle; cooking area unspecified', width=45, depth=28, height=6),
    'wok': profile('one pan including handles; capacity unspecified', width=48, depth=35, height=13),
    'coffee_maker': profile('countertop appliance exterior; electrical, capacity and clearance specifications excluded', width=25, depth=29, height=36),
    'coffee_grinder': profile('countertop appliance exterior; electrical and capacity specifications excluded', width=13, depth=18, height=27),
    'hand_frother': profile('one handheld tool including whisk; electrical specifications excluded', width=4, depth=4, height=24),
    'canister': profile('one closed canister; capacity unspecified', width=13, depth=13, height=19),
    'runner': profile('one table runner, laid flat', width=35, length=180),
    'towel': profile('one towel, laid flat', width=40, length=65),
    'paper_towel_holder': profile('one freestanding holder; roll compatibility unspecified', width=17, depth=17, height=33),
    'utensil_crock': profile('one crock exterior; capacity unspecified', width=14, depth=14, height=18),
    'spice_rack': profile('one rack in an assumed closed position; container compatibility unspecified', width=33, depth=24, height=9),
    'knife': profile('one serving knife including handle', width=3, length=30, height=1),
    'cushion': profile('one chair cushion; chair fit unspecified', width=42, depth=42, height=5),
    'wine_rack': profile('one assembled rack exterior; bottle fit and load rating unspecified', width=48, depth=32, height=90),
    'tool_chest': profile('closed chest exterior; drawer clearance and load rating unspecified', width=52, depth=30, height=38),
    'beverage_fridge': profile('closed appliance exterior; installation, ventilation, capacity and electrical specifications excluded', width=60, depth=60, height=85),
    'pasta_attachment': profile('attachment exterior; mixer fit, capacity and moving clearance unspecified', width=10, depth=18, height=22),
    'vanity': profile('assembled vanity exterior; sink cutouts, plumbing and installation clearances excluded', width=76, depth=51, height=86),
    'vanity_top': profile('top and basin exterior; cutouts, plumbing and installation clearances excluded', width=64, depth=56, height=17),
    'wall_panel': profile('one panel exterior; joint overlap and installation coverage excluded', width=63, length=124, height=1),
    'shower_enclosure': profile('closed enclosure exterior; door swing, plumbing and installation clearances excluded', width=117, depth=88, height=183),
    'towel_warmer': profile('closed freestanding warmer exterior; capacity, electrical and installation specifications excluded', width=30, depth=30, height=54),
    'camping_fan': profile('one fan housing including handle; electrical specifications excluded', width=16, depth=16, height=19),
    'air_pump': profile('primary pump housing only; adapters, capacity and electrical specifications excluded', width=12, depth=14, height=12),
    'robe_hook': profile('one hook exterior; fasteners, load rating and installation dimensions excluded', width=9, depth=12, height=7),
    'bathtub': profile('primary tub exterior only; faucet, drain, plumbing and installation clearances excluded', width=76, length=140, height=58),
    'bidet_faucet': profile('faucet body exterior only; handle spacing, plumbing and installation dimensions excluded', width=20, depth=15, height=12),
    'shower_riser': profile('riser exterior only; not a grab-bar load rating or installation specification', width=20, depth=10, height=157),
    'doorbell_button': profile('one push-button exterior; fasteners, wiring and installation dimensions excluded', width=10, depth=2, height=10),
    'rain_barrel': profile('barrel exterior only; spigot projection, capacity and installation dimensions excluded', width=60, depth=55, height=95),
    'grill_cover': profile('assumed draped cover exterior; not verification of the named grill compatibility', width=168, depth=62, height=112),
    'shower_rod': profile('one curved rod at an assumed fixed extension; mounting and installation dimensions excluded', width=152, depth=20, height=3),
    'platform_riser': profile('one riser at an assumed closed extension; load rating unspecified', width=38, depth=16, height=12),
    'safe': profile('closed safe exterior; usable interior, security rating and mounting dimensions excluded', width=40, depth=35, height=30),
    'shed': profile('closed shed exterior; foundation, door swing and installation clearances excluded', width=183, depth=92, height=201),
    'jewelry_organizer': profile('one hanging organizer exterior; pocket sizes and jewelry fit unspecified', width=44, depth=1, height=84),
    'closet_shelf_unit': profile('assembled shelf unit exterior; mounting and load rating unspecified', width=66, depth=30, height=33),
    'shoe_organizer': profile('one overdoor organizer exterior; shoe fit, door fit and load rating unspecified', width=56, depth=21, height=150),
    'fitted_sheet': profile('one primary fitted sheet surface and assumed pocket depth; not a mattress-fit guarantee', width=152.4, length=203.2, height=30),
    'bunk_frame': profile('assembled bunk-frame exterior; sleeping areas, mattress fit, guardrails, ladders, load ratings and safety clearances excluded', width=150, length=210, height=185),
    'trundle_frame': profile('bed-frame exterior with trundle stowed; extension, mattress fit, load rating and safety clearances excluded', width=150, length=210, height=100),
    'hanging_daybed': profile('daybed frame body only; suspension, mattress fit, load rating and safety clearances excluded', width=150, length=210, height=60),
    'bed_package': profile('base and mattress exterior in assumed flat position; articulation, mattress fit, load rating and safety clearances excluded', width=157, length=208, height=63),
    'mortar': profile('one mortar exterior; cavity and capacity unspecified', width=11, depth=11, height=10),
    'pestle': profile('one pestle exterior', width=3, length=15, height=3),
    'shaker': profile('one shaker exterior; capacity unspecified', width=8, depth=7, height=9),
    'mixing_bowl': profile('one bowl exterior; capacity unspecified', width=22, depth=22, height=11),
    'bowl_lid': profile('one lid exterior; seal and fit not independently verified', width=22, depth=22, height=1),
    'serving_fork': profile('one serving fork including handle', width=4, length=25, height=2),
    'cake_server': profile('one cake server including handle', width=6, length=25, height=2),
    'spreader': profile('one spreader including handle', width=2, length=18, height=0.7),
    'steak_knife': profile('one steak knife including handle', width=2, length=23, height=0.7),
    'salon_chair': profile('one chair at an assumed upright fixed adjustment; moving clearance and treatment claims excluded', width=68, depth=75, height=105, seat_width=50, seat_depth=48, seat_height=53),
    'contour_mat': profile('one contour mat, laid flat; toilet fit and cutout dimensions unspecified', width=45, length=50, pile_height=0.8),
    'curtain_hook': profile('one curtain hook exterior; attachment fit unspecified', width=4, depth=1, height=6),
}

CLASS_PROFILES = {
    'area rugs':'rug', 'doormats':'mat', 'bath rugs & mats':'mat', 'kitchen mats':'mat',
    'floor & wall tile':'tile', 'outdoor deck tiles':'tile', 'accent pillows':'pillow',
    'curtains & drapes':'curtain', 'shower curtains':'shower_curtain', 'bedding sets':'bedding',
    'comforters & duvet fills':'bedding', 'beds':'bed', 'kids beds':'bed', 'teen beds':'bed',
    'adjustable beds':'bed_base', 'bed frames':'bed_base', 'headboards':'headboard', 'teens headboards':'headboard',
    'office chairs':'office_chair', 'teen desk chairs':'office_chair', 'dining chairs':'dining_chair',
    'stackable chairs':'dining_chair', 'accent chairs':'armchair', 'bar stools':'stool', 'office stools':'stool',
    'kids chairs':'kids_chair', 'soft seating':'kids_chair', 'game chairs':'floor_chair',
    'benches':'bench', 'ottomans':'ottoman', 'coffee & cocktail tables':'coffee_table',
    'sofa & console tables':'console', 'makeup vanities':'desk', 'desks':'desk', 'kids desks':'kids_desk',
    'nightstands':'nightstand', 'teen nightstands':'nightstand', 'end tables':'side_table',
    'kids dressers & chests':'kids_dresser', 'teen dressers':'kids_dresser', 'dressers & chests':'dresser',
    'accent chests / cabinets':'dresser', 'bathroom storage':'cabinet', 'office storage cabinets':'cabinet',
    'storage drawers':'cabinet', 'bookcases':'bookcase', 'kids bookcases':'bookcase',
    'wall mounted shelves':'shelf', 'armoires & wardrobes':'wardrobe', 'garage storage cabinets':'wardrobe',
    'pantry cabinets':'pantry', 'trunks':'trunk', 'deck boxes':'deck_box', 'patio lounge chairs':'patio_chair',
    'patio rockers & gliders':'patio_chair', 'patio chaise lounges':'patio_chaise', 'patio sofas':'patio_sofa',
    'patio tables':'patio_table', 'planters':'planter', 'floor lamps':'floor_lamp', 'table lamps':'table_lamp',
    'chandeliers':'chandelier', 'pendant lights':'pendant', 'wall sconces':'sconce', 'vanity lighting':'sconce',
    'hangers':'hanger',
    'mugs & teacups':'mug', 'dining bowls':'bowl', 'serving bowls':'bowl',
    'roasting pans':'roaster', 'dutch ovens & braisers':'dutch_oven',
    'stock pots, soup pots and multi-pots':'stock_pot', 'grill pans & griddles':'grill_pan', 'woks':'wok',
    'coffee makers':'coffee_maker', 'coffee grinders':'coffee_grinder', 'kitchen towels':'towel',
    'furniture cushions':'cushion', 'wine racks':'wine_rack', 'tool cabinets':'tool_chest',
    'beverage refrigerators & coolers':'beverage_fridge', 'wine refrigerators':'beverage_fridge',
    'vanities':'vanity', 'vanity tops':'vanity_top', 'shower and bathtub enclosures':'shower_enclosure',
    'towel & robe hooks':'robe_hook', 'tubs and whirlpools':'bathtub', 'bidet faucets':'bidet_faucet',
    'rain barrels':'rain_barrel', 'shower curtain rods':'shower_rod', 'safes':'safe', 'sheds':'shed',
}
SCALED_PROFILES = {'kids_chair', 'kids_sofa', 'kids_desk', 'kids_dresser', 'bookcase', 'shelf',
                   'patio_chair', 'patio_chaise', 'patio_sofa', 'patio_table', 'coffee_table',
                   'side_table', 'bar_table', 'planter'}
WIDTH_PROFILES = {'coffee_table', 'console', 'side_table', 'desk', 'nightstand', 'dresser',
                  'cabinet', 'bookcase', 'tv_stand', 'shelf', 'wall_storage', 'vanity'}
SIZE_SCALE = {'Small': .85, 'Medium': 1, 'Large': 1.15, 'Extra Large': 1.3}
# Fictional nominal design anchors, not a fit table or promise of standard compliance.
BED_ANCHORS = {'Toddler': (71, 133), 'Twin': (99, 190.5), 'Full': (137.2, 190.5),
               'Queen': (152.4, 203.2), 'King': (193, 203.2)}
COVER_ANCHORS = {'Twin': (172.72, 218.44), 'Full': (203.2, 218.44),
                 'Queen': (228.6, 233.68), 'King': (264.16, 233.68)}
TITLE_CONSTRAINED_PROFILES = {'vanity','vanity_top','wall_panel','shower_enclosure','bathtub','shed','closet_shelf_unit','shower_rod'}
CONTEXT_KEYS = {'producttype','settype','piecesincluded','productsincluded','numberofitemsincluded',
                'numberofpiecesincluded','totalnumberofpiecesincluded','totalnumberofpieces',
                'fittedsheetincluded','flatsheetincluded','pillowcaseincluded','numberofshelves',
                'numberoflidsincluded','numberofhooksincluded','numberofchairsincluded','numberoftablesincluded',
                'tableincluded','ottomanincluded','mattressincluded','pillowcasetype','cribsizeshape'}


def source_context(row):
    features = parse_features(row.get('product_features',''))
    return {'source_name':row.get('product_name',''),
            'features':{k:features[k] for k in sorted(CONTEXT_KEYS & features.keys())}}


def context_is(record, key, value):
    values = record.get('design_context',{}).get('features',{}).get(key,[])
    return {v.strip().casefold() for v in values} == {value}


def choose_profile(record):
    classes = {c.strip().casefold() for c in record['source_class'].split('|')}
    name = record['name'].casefold()
    if 'fabric' in classes:
        return None, 'sale_unit_requires_definition'
    if 'sheets and sheet sets' in classes and context_is(record,'fittedsheetincluded','yes') and context_is(record,'flatsheetincluded','no') and context_is(record,'pillowcaseincluded','no') and 'pillowcase' not in name:
        return 'fitted_sheet', None
    if classes & {'crib bedding sets', 'sheets and sheet sets', 'valances & kitchen curtains'}:
        return None, 'option_class_or_component_mismatch'
    if classes & {'outdoor conversation sets', 'patio dining sets'} or 'wands_piece_count' in record.get('axis_codes', []):
        return None, 'assortment_requires_component_dimensions'
    if classes & {'bakeware sets', 'flatware & silverware sets', 'mixing bowls'}:
        return None, 'assortment_requires_component_dimensions'
    if 'kitchen gadgets' in classes and re.search(r'\bset\b',name):
        return None, 'assortment_requires_component_dimensions'
    if {'bath rugs & mats','shower curtains'} <= classes and context_is(record,'productsincluded','liner'):
        return None, 'option_class_or_component_mismatch'
    if {'bath rugs & mats', 'shower curtains'} <= classes or {'floor lamps', 'table lamps'} <= classes:
        return None, 'mixed_product_classes_require_component_dimensions'
    size = record['variant_options'].get('wands_size','')
    if classes & {'beds','kids beds','teen beds','daybeds & guest beds','adjustable beds'}:
        if 'triple' in name: return None, 'bed_level_options_require_definition'
        if 'bunk' in name:
            return ('bunk_frame',None) if re.fullmatch(r'(Twin|Twin XL|Full) over (Twin|Full|Queen)',size) else (None,'bed_level_options_require_definition')
        if 'trundle' in name:
            return ('trundle_frame',None) if size in {'Twin','Full','Queen'} else (None,'option_class_or_component_mismatch')
        if 'hanging daybed' in name: return 'hanging_daybed',None
        if 'base and mattress' in name: return 'bed_package',None
    if re.search(r'\bbunk\b|\btrundle\b|\bhanging daybed\b|\btriple bed\b|\bwith ottoman\b|\bbase and mattress\b', name):
        return None, 'moving_or_multiple_components_require_design'
    if 'toddler' in name and any(v != 'Toddler' for k, v in record['variant_options'].items() if k == 'wands_size'):
        return None, 'option_class_or_component_mismatch'
    # Exact class mappings have precedence for mixed classifications; title only
    # selects a fictional subtype and is recorded as design evidence, not fact.
    matches = [v for k, v in CLASS_PROFILES.items() if k in classes]
    # Heterogeneous accessory classes require a recognizable named subtype.
    for cls, pattern, subtype in [
        ('milk frothers', r'\bhandheld\b', 'hand_frother'),
        ('coffee & espresso accessories', r'\bcanister\b', 'canister'),
        ('dining linens', r'\btable runner\b', 'runner'),
        ('napkin holders & paper towel holders', r'\bpaper towel holder\b', 'paper_towel_holder'),
        ('utensil crocks, caddies, chests and spoon rests', r'\butensil crock\b', 'utensil_crock'),
        ('spice jars & racks', r'\bspice rack\b', 'spice_rack'),
        ('flatware & silverware serving pieces', r'\bknife\b', 'knife'),
        ('mixers & mixer accessories', r'\bpasta extruder attachment\b', 'pasta_attachment'),
        ('wall paneling', r'\bwall panel', 'wall_panel'),
        ('towel warmers', r'\bfree ?standing\b', 'towel_warmer'),
        ('portable fans', r'\bcamping\b', 'camping_fan'),
        ('air treatment accessories', r'\bpump\b', 'air_pump'),
        ('grab bars', r'\bshower riser\b', 'shower_riser'),
        ('door bells & chimes', r'\bpush button\b', 'doorbell_button'),
        ('covers & carry bags', r'\bgrill cover\b', 'grill_cover'),
        ('laundry accessories', r'\bplatform riser\b', 'platform_riser'),
        ('closet organizer accessories', r'\bhanging jewelry organizer\b', 'jewelry_organizer'),
        ('closet storage & organization', r'\bshelf\b', 'closet_shelf_unit'),
        ('shoe storage', r'\boverdoor\b', 'shoe_organizer'),
    ]:
        if cls in classes and re.search(pattern, name): matches.append(subtype)
    if not matches:
        return None, 'no_class_profile'
    key = matches[0]
    if 'dining_chair' in matches and re.search(r'\bparsons\b|\bdining chair\b', name):
        key = 'dining_chair'
    if 'shelf' in matches:
        if re.search(r'\b[2-9]\s*(?:piece|layer)|\bquadruple\b', name) and not (context_is(record,'totalnumberofpiecesincluded','1') and 'piece' not in name):
            return None, 'assortment_requires_component_dimensions'
        key = 'shelf' if re.search(r'\bfloating\b|\bbracket shelf\b', name) else 'wall_storage'
    if key == 'bookcase' and 'tv stand' in name:
        key = 'tv_stand'
    if key == 'bookcase' and 'floating shelf' in name:
        key = 'shelf'
    if key == 'kids_chair' and 'sofa' in name:
        key = 'kids_sofa'
    if key == 'patio_table':
        if 'coffee table' in name: key = 'coffee_table'
        elif 'side table' in name: key = 'side_table'
        elif 'bar table' in name: key = 'bar_table'
    if key in {'pendant', 'chandelier'} and ('linear' in name or 'kitchen island' in name):
        key = 'linear_pendant'
    return key, None


def option_cm(value):
    match = re.fullmatch(r'(\d+(?:\.\d+)?) (in|ft)', value)
    if not match:
        raise ValueError('unsupported_numeric_option')
    return round(float(match[1]) * {'in': 2.54, 'ft': 30.48}[match[2]], 4)


def title_constraints(name):
    """Constrain fictional exterior geometry; never promote text into source facts."""
    number = r'(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)'
    pattern = rf'(?<![\w./-])({number})\s*(inches|inch|in\b|ft\b|feet|cm\b|mm\b|\x22|″|\x27\x27)\s*\.?\s*(wide|width|w|deep|depth|d|height|high|tall|h|length|long|l)\b'
    found = {}
    axes = {'w':'width','wide':'width','width':'width','d':'depth','deep':'depth','depth':'depth',
            'h':'height','height':'height','high':'height','tall':'height','l':'length','length':'length','long':'length'}
    factors = {'inches':2.54,'inch':2.54,'in':2.54,'ft':30.48,'feet':30.48,'cm':1,'mm':.1,'"':2.54,'″':2.54,"''":2.54}
    for match in re.finditer(pattern,name,re.I):
        axis = axes[match[3].casefold()]
        value = round(sum(float(Fraction(part)) for part in match[1].split()) * factors[match[2].casefold()],4)
        found.setdefault(axis,[]).append((value,match[0]))
    return {axis:rows[0] for axis,rows in found.items() if len({v for v,_ in rows})==1}


def propose(record, key):
    design = PROFILES[key]
    factor = .94 + .12 * stable_fraction(record['source_product_id'], SEED_VERSION)
    values = {k: round(v * factor, 1) for k, v in design['dimensions'].items()}
    options = record['variant_options']
    used = {}
    allowed = set()
    if key in TITLE_CONSTRAINED_PROFILES and not (set(record.get('axis_codes',[])) & GEOMETRY_AXES):
        for axis,(value,evidence) in title_constraints(record.get('design_context',{}).get('source_name',record['name'])).items():
            if axis in values:
                values[axis] = value
                used['title_design_constraint:'+axis] = evidence
    if key in {'rug', 'mat', 'tile', 'pillow'}:
        allowed.add('wands_size')
        if key == 'tile': allowed.add('wands_pack_size')
        if 'wands_size' in options:
            parts = options['wands_size'].split(' x ')
            if len(parts) != 2: raise ValueError('unsupported_size_option')
            values['width'], values['length'] = map(option_cm, parts)
            used['wands_size'] = options['wands_size']
    elif key in {'bunk_frame','trundle_frame','hanging_daybed','bed_package'}:
        allowed.add('wands_size')
        size=options.get('wands_size','')
        sizes=size.split(' over ')
        anchors={**BED_ANCHORS,'Twin XL':(99,203.2)}
        if not sizes or any(s not in anchors for s in sizes): raise ValueError('unsupported_bed_size_or_components')
        padding=4 if key=='bed_package' else 16
        values['width']=round(max(anchors[s][0] for s in sizes)+padding,4)
        values['length']=round(max(anchors[s][1] for s in sizes)+padding,4)
        used['wands_size']=size
    elif key in {'bed', 'bed_base', 'headboard', 'bedding', 'fitted_sheet'}:
        allowed.add('wands_size')
        if 'wands_size' in options:
            size = options['wands_size']; anchors = COVER_ANCHORS if key == 'bedding' else BED_ANCHORS
            if size not in anchors: raise ValueError('unsupported_bed_size_or_components')
            width, length = anchors[size]
            values['width'] = round(width + (0 if key in {'bedding','fitted_sheet'} else 4 if key == 'bed_base' else 8), 4)
            if key != 'headboard': values['length'] = round(length + (0 if key in {'bedding','fitted_sheet'} else 4 if key == 'bed_base' else 12), 4)
            used['wands_size'] = size
    elif key in SCALED_PROFILES:
        allowed.add('wands_size')
        if 'wands_size' in options:
            size = options['wands_size']
            if size not in SIZE_SCALE: raise ValueError('unsupported_size_option')
            # Furniture height changes less than the footprint. All remain
            # monotonic, including seat heights, without giant bar-height tables.
            values = {k: round(v * (1 + (SIZE_SCALE[size] - 1) * (.35 if 'height' in k else 1)), 1) for k, v in values.items()}
            used['wands_size'] = size
    if key in WIDTH_PROFILES | {'curtain', 'shower_curtain'}:
        allowed.add('wands_length')
        if 'wands_length' in options:
            axis = 'length' if key in {'curtain', 'shower_curtain'} else 'width'
            values[axis] = option_cm(options['wands_length'])
            if key == 'nightstand' and values['width'] > 90:
                raise ValueError('oversized_nightstand_option_requires_review')
            used['wands_length'] = options['wands_length']
    if key == 'stool':
        allowed.add('wands_seat_height')
        if 'wands_seat_height' in options:
            values['seat_height'] = option_cm(options['wands_seat_height'])
            values['height'] = round(values['seat_height'] + (0 if 'backless' in record['name'].casefold() else 25), 4)
            used['wands_seat_height'] = options['wands_seat_height']
    if key in {'chandelier', 'pendant', 'linear_pendant', 'sconce'}:
        allowed.add('wands_light_count')
        if 'wands_light_count' in options:
            match = re.fullmatch(r'([1-8]) Lights?', options['wands_light_count'])
            if not match: raise ValueError('unsupported_light_count')
            count = int(match[1])
            values['width'] = (20 + 22 * count if key == 'linear_pendant' else 8 + 14 * count if key == 'sconce' else 24 + 8 * count)
            if key in {'chandelier', 'pendant'}: values['depth'] = values['width']
            used['wands_light_count'] = options['wands_light_count']
    if (set(record.get('axis_codes', [])) & GEOMETRY_AXES) - allowed:
        raise ValueError('geometry_axis_has_no_class_mapping')
    shape = record['specifications'].get('lab_spec_shape', {}).get('value')
    # Source "shape" can describe the body, not handles, arms or a lamp base.
    # Only these profiles give it an unambiguous footprint meaning.
    if shape in {'Round', 'Square'} and key in {'rug','mat','tile','pillow','coffee_table',
            'side_table','bar_table','patio_table','planter','ottoman'}:
        axis = 'length' if key in {'rug', 'mat', 'tile', 'pillow'} else 'depth'
        if axis in values:
            if 'wands_size' in used and ' x ' in used['wands_size'] and values['width'] != values[axis]:
                raise ValueError('shape_option_conflict')
            values[axis] = values['width']
    return values, used


def dimensions(record):
    return {k: f for k, f in record['specifications'].items() if k.endswith('_cm')}


def dimension_fact(record, key, value, used, extra_evidence=()):
    evidence=[{'key':'synthetic_profile','raw':key}, {'key':'family_seed','raw':record['source_product_id']},
              {'key':'design_class','raw':record['source_class']}]
    evidence += [{'key':k,'raw':v} for k,v in sorted(used.items())] + list(extra_evidence)
    return {'value':value,'synthetic':True,'origin':ORIGIN,'rule_version':VERSION,'profile':key,
            'display_label':LABEL,'scope':PROFILES[key]['scope'],'evidence':copy.deepcopy(evidence)}


def component_plan(record):
    """Interpret only bounded, explicit assortments; never invent a set's contents."""
    classes={c.strip().casefold() for c in record['source_class'].split('|')}
    name=record.get('design_context',{}).get('source_name',record['name']).casefold()
    features=record.get('design_context',{}).get('features',{})
    bath_set = {'bath rugs & mats','shower curtains'} <= classes and {'bath mat/rug','contour mat','shower curtain','hooks'} == {v.strip().casefold() for v in features.get('productsincluded',[])}
    chair_set = bool(classes & {'massage chairs','recliners'}) and 'with ottoman' in name
    recognized = ('kitchen gadgets' in classes and 'mortar and pestle' in name or
        'salt and pepper shakers / grinders (mills)' in classes and 'salt and pepper' in name or
        'mixing bowls' in classes or 'flatware & silverware sets' in classes or
        'wall mounted shelves' in classes and re.search(r'\b[2-9]\s*piece\b',name) or bath_set or chair_set)
    if not recognized: return None
    if (set(record.get('axis_codes',[])) & GEOMETRY_AXES) - ({'wands_size'} if bath_set else {'wands_length'}):
        raise ValueError('assortment_option_mapping_requires_definition')
    evidence=[{'key':'source_product_name','raw':name}]
    counts=set()
    for key in ('numberofitemsincluded','numberofpiecesincluded','totalnumberofpiecesincluded','totalnumberofpieces'):
        for raw in features.get(key,[]):
            if not re.fullmatch(r'[1-9]\d*',raw.strip()): raise ValueError('ambiguous_component_count')
            counts.add(int(raw)); evidence.append({'key':key,'raw':raw})
    counts.update(int(v) for v in re.findall(r'\b(\d+)\s*piece\b',name))
    counts.update(int(v) for v in features.get('piecesincluded',[]) if re.fullmatch(r'[1-9]\d*',v.strip()))
    if len(counts)>1: raise ValueError('conflicting_component_counts')
    count=next(iter(counts)) if counts else None
    # id, label, profile, relative size. Each role is one physical item.
    roles=[]
    quantities={}
    if bath_set:
        if not context_is(record,'numberofhooksincluded','12') or count!=15:
            raise ValueError('component_quantities_require_definition')
        evidence += [{'key':'productsincluded','raw':v} for v in sorted(features['productsincluded'])]
        evidence.append({'key':'numberofhooksincluded','raw':'12'})
        roles=[('curtain','Shower curtain','shower_curtain',1),('bath-mat','Bath mat','mat',1),
               ('contour-mat','Contour mat','contour_mat',1),('hooks','Curtain hooks','curtain_hook',1)]
        quantities['hooks']=12
    elif chair_set:
        if not context_is(record,'ottomanincluded','yes') or count not in {None,2}:
            raise ValueError('component_inclusion_requires_confirmation')
        evidence.append({'key':'ottomanincluded','raw':'yes'})
        roles=[('chair','Chair','salon_chair',1),('ottoman','Ottoman','ottoman',1)]
    elif 'kitchen gadgets' in classes and 'mortar and pestle' in name:
        if count not in {None,2}: raise ValueError('conflicting_component_counts')
        roles=[('mortar','Mortar','mortar',1),('pestle','Pestle','pestle',1)]
    elif 'salt and pepper shakers / grinders (mills)' in classes:
        if count != 2: raise ValueError('component_quantities_require_definition')
        roles=[('salt-shaker','Salt shaker','shaker',1),('pepper-shaker','Pepper shaker','shaker',1)]
    elif 'mixing bowls' in classes:
        lids={int(v) for v in features.get('numberoflidsincluded',[]) if re.fullmatch(r'[1-9]\d*',v.strip())}
        if len(lids)!=1 or count != 2*next(iter(lids)) or not 2 <= next(iter(lids)) <= 6:
            raise ValueError('component_quantities_require_definition')
        n=next(iter(lids)); evidence.append({'key':'numberoflidsincluded','raw':str(n)})
        for i in range(n):
            scale=.65 + .18*i
            roles += [(f'bowl-{i+1}',f'Bowl {i+1}','mixing_bowl',scale),(f'lid-{i+1}',f'Lid {i+1}','bowl_lid',scale)]
    elif 'flatware & silverware sets' in classes:
        role_map={'serving fork':('serving-fork','serving_fork'),'cake/pastry server':('cake-server','cake_server'),
                  'spreader':('spreader','spreader'),'steak knife':('steak-knife','steak_knife')}
        pieces={v.strip().casefold() for v in features.get('piecesincluded',[])}
        if not pieces or len(pieces)!=count or not pieces <= role_map.keys():
            raise ValueError('component_quantities_require_definition')
        evidence += [{'key':'piecesincluded','raw':v} for v in sorted(pieces)]
        roles=[(role_map[v][0],v.title(),role_map[v][1],1) for v in sorted(pieces)]
    elif 'wall mounted shelves' in classes:
        if count is None or not 2 <= count <= 6 or not context_is(record,'numberofshelves',str(count)):
            raise ValueError('component_quantities_require_definition')
        evidence.append({'key':'numberofshelves','raw':str(count)})
        roles=[(f'shelf-{i+1}',f'Shelf {i+1}','shelf',(.4+.6*i/(count-1))) for i in range(count)]
    components=[]
    if count is not None and sum(quantities.get(role[0],1) for role in roles)!=count:
        raise ValueError('component_total_mismatch')
    if 'wands_length' in record.get('axis_codes',[]) and any(role[2]!='shelf' for role in roles):
        raise ValueError('assortment_option_mapping_requires_definition')
    for identifier,label,key,scale in roles:
        part=copy.deepcopy(record)
        part['variant_options']={k:v for k,v in record['variant_options'].items() if k not in GEOMETRY_AXES or key=='shelf' and k=='wands_length' or bath_set and key=='mat' and k=='wands_size'}
        part['axis_codes']=list(part['variant_options'])
        part['specifications']={}
        values,used=propose(part,key)
        for axis in values:
            if key in {'mixing_bowl','bowl_lid'} and axis in {'width','depth'} or key=='shelf' and axis=='width':
                values[axis]=round(values[axis]*scale,4)
        component_evidence=evidence+[{'key':'component_role','raw':identifier}]
        facts={PREFIX+axis+'_cm':dimension_fact(record,key,value,used,component_evidence) for axis,value in values.items()}
        components.append({'component_id':identifier,'label':label,'quantity':quantities.get(identifier,1),'profile':key,'scope':PROFILES[key]['scope'],
                           'specifications':facts,'composition_evidence':copy.deepcopy(evidence),
                           'composition_basis':'bounded interpretation of named source components; not independently verified'})
    return components


def validate_dimensions(record):
    facts = dimensions(record)
    for code, fact in facts.items():
        value = fact['value']
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 10000:
            raise ValueError('invalid_dimension: ' + code)
        if fact.get('synthetic') and (fact.get('origin') != ORIGIN or not fact.get('rule_version')
                or not fact.get('evidence') or fact.get('display_label') != LABEL or not fact.get('scope')):
            raise ValueError('synthetic_dimension_missing_provenance: ' + code)
    for seat, overall in [('seat_width', 'width'), ('seat_depth', 'depth'), ('seat_height', 'height')]:
        a, b = facts.get(PREFIX + seat + '_cm'), facts.get(PREFIX + overall + '_cm')
        if a and b and a['value'] > b['value']:
            raise ValueError('seat_outside_overall_envelope: ' + seat)
    design = record.get('dimension_design', {})
    components=design.get('components',[])
    if components:
        ids=[c['component_id'] for c in components]
        if len(ids)!=len(set(ids)): raise ValueError('duplicate_component_identity')
        if design.get('total_component_quantity')!=sum(c['quantity'] for c in components):
            raise ValueError('component_total_mismatch')
        for component in components:
            if type(component['quantity']) is not int or component['quantity']<=0 or not component['composition_evidence'] or len(component['specifications'])<2:
                raise ValueError('invalid_component_definition')
            validate_dimensions({'specifications':component['specifications'],
                'dimension_design':{'profile':component['profile'],'status':'synthetic_design_complete'}})
    if design.get('status')=='synthetic_components_complete' and not components:
        raise ValueError('missing_component_dimensions')
    if design.get('profile') in PROFILES and design.get('status') == 'synthetic_design_complete':
        for axis, anchor in PROFILES[design['profile']]['dimensions'].items():
            if PREFIX + axis + '_cm' not in facts:
                raise ValueError('incomplete_profile_dimension: ' + axis)
            ceiling = 120 if design['profile'] == 'sconce' and axis == 'width' else anchor * 3
            if not anchor * .35 <= facts[PREFIX + axis + '_cm']['value'] <= ceiling:
                raise ValueError('dimension_outside_design_bounds: ' + axis)


def add_dimensions(record):
    result = copy.deepcopy(record)
    key, issue = choose_profile(record)
    result['dimension_design'] = {'rule_version': VERSION, 'profile': key, 'display_label': LABEL,
                                  'status': 'needs_identity_or_component_review', 'issues': [],
                                  'source_verified': False, 'scope': PROFILES[key]['scope'] if key else None}
    try:
        components=component_plan(record)
        if components:
            result['dimension_design'].update({'profile':None,'components':components,'status':'synthetic_components_complete',
                'scope':'Individual components only, not an installed span or a single set-wide dimension',
                'total_component_quantity':sum(c['quantity'] for c in components)})
            validate_dimensions(result)
            return result
        if issue: raise ValueError(issue)
        values, used = propose(record, key)
        for axis, value in values.items():
            code = PREFIX + axis + '_cm'
            if code not in result['specifications']:
                result['specifications'][code] = dimension_fact(record,key,value,used)
        result['dimension_design']['status'] = 'synthetic_design_complete'
        validate_dimensions(result)
    except ValueError as error:
        result['specifications'] = copy.deepcopy(record['specifications'])
        result['dimension_design']['status'] = 'needs_identity_or_component_review'
        result['dimension_design'].pop('components',None)
        result['dimension_design'].pop('total_component_quantity',None)
        result['dimension_design']['issues'].append(str(error))
    return result


def repair_proposals(records):
    """Read-only, exact-target work queue. No SKU, option or assortment mutations."""
    roots={r['sku']:r for r in records if not r.get('parent_sku')}
    groups={}
    for r in records:
        if r.get('dimension_design',{}).get('issues'):
            groups.setdefault(r.get('parent_sku',r['sku']),[]).append(r)
    proposals=[]
    for sku,affected in sorted(groups.items()):
        root=roots[sku]
        issues=sorted({i for r in affected for i in r['dimension_design']['issues']})
        if 'conflicting_component_counts' in issues:
            scope='source_conflict'
            action='Resolve the disagreement between the product title and component counts before defining dimensions; do not pick the convenient count.'
        elif 'sale_unit_requires_definition' in issues:
            scope='sale_unit_definition'
            action='Define the purchasable fabric cut or roll and its unit explicitly before adding a length. Do not infer a yard from unitless source numbers.'
        elif any('option' in i for i in issues):
            scope='catalog_option_definition'
            action='Prepare a separate family-option correction with a child-SKU mapping, collision check and before/after review. Keep this packet unchanged.'
            if 'nightstand' in root['source_class'].casefold():
                action+=' Replace oversized width choices with explicitly synthetic nightstand-scale choices.'
            elif 'crib bedding' in root['source_class'].casefold():
                action+=' Remove adult-bed size choices from crib-only designs and preserve the actual component assortment.'
            elif 'pillowcase' in root['name'].casefold():
                action+=' Use pillowcase dimensions or a confirmed body-pillow size, not unrelated mattress size labels.'
            elif 'curtain' in root['source_class'].casefold():
                action+=' Distinguish cafe curtains, valances and shower liners from bath mats and full-length drapes.'
            elif 'triple' in root['name'].casefold():
                action+=' Define all three bed levels explicitly instead of interpreting a single size as a complete bunk arrangement.'
            elif 'toddler' in root['name'].casefold():
                action+=' Retain toddler sizing for a toddler-only design instead of treating adult-bed labels as dimensions of it.'
            elif 'trundle' in root['name'].casefold():
                action+=' Remove the toddler option from the twin/full trundle family rather than inventing a toddler trundle design.'
        elif 'no_class_profile' in issues:
            scope='dimension_profile'
            action='Add a bounded class/subtype profile with tests; do not use a department-wide default.'
        else:
            scope='assortment_definition'
            action='Resolve exact included component roles and quantities for every option combination before designing their dimensions. Piece count alone is insufficient.'
        proposals.append({'root_sku':sku,'name':root['name'],'resolution_scope':scope,'recommended_action':action,
            'issues':issues,'current_axes':copy.deepcopy(root.get('axes',[])),'source_context':copy.deepcopy(root.get('design_context',{})),
            'affected_record_count':len(affected),'affected_skus':sorted(r['sku'] for r in affected),
            'affected_children':sum(bool(r.get('parent_sku')) for r in affected),
            'current_records':[{'sku':r['sku'],'options':copy.deepcopy(r['variant_options']),'issues':r['dimension_design']['issues']} for r in sorted(affected,key=lambda r:r['sku'])],
            'executable':False,'changes_applied':0,'publication_approval':False})
    return proposals


def summarize_family(parent, children):
    result = copy.deepcopy(parent)
    complete = [c for c in children if c['dimension_design']['status'] in COMPLETE_STATUSES]
    ranges = {}
    for code in sorted({k for c in complete for k in dimensions(c)}):
        values = [dimensions(c)[code]['value'] for c in complete if code in dimensions(c)]
        ranges[code] = {'min': min(values), 'max': max(values), 'covered_children': len(values),
                        'total_children': len(children), 'synthetic': any(dimensions(c).get(code, {}).get('synthetic') for c in complete)}
        # A configurable has no single varying size. Promote only common facts
        # across a fully covered family; partial ranges remain review metadata.
        if len(values) == len(children) and min(values) == max(values):
            result['specifications'].setdefault(code, copy.deepcopy(complete[0]['specifications'][code]))
    component_children=[c for c in complete if c['dimension_design']['status']=='synthetic_components_complete']
    component_ranges=[]
    if component_children:
        first=component_children[0]['dimension_design']['components']
        for component in first:
            matches=[part for c in component_children for part in c['dimension_design']['components'] if part['component_id']==component['component_id']]
            component_ranges.append({'component_id':component['component_id'],'label':component['label'],
                'quantity_per_design':sorted({part['quantity'] for part in matches}),
                'dimensions_cm':{code:{'min':min(part['specifications'][code]['value'] for part in matches),
                    'max':max(part['specifications'][code]['value'] for part in matches),
                    'covered_children':len(matches),'total_children':len(children)} for code in component['specifications']}})
    result['dimension_design'] = {'rule_version': VERSION, 'display_label': LABEL,
        'status': 'synthetic_family_complete' if len(complete) == len(children) and children else 'synthetic_family_partial' if complete else 'needs_identity_or_component_review',
        'ranges_cm': ranges, 'covered_children': len(complete), 'total_children': len(children),
        'component_children':len(component_children),'component_ranges':component_ranges,
        'issues': sorted({i for c in children for i in c['dimension_design']['issues']}),
        'source_verified': False, 'scope': 'Child-specific designs; varying dimensions are ranges, not parent scalar values'}
    return result
