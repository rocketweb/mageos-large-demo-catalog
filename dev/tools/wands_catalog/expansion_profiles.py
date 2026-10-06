"""Authored synthetic design vocabulary for the approved 2026-09 expansion.

Numbers describe fictional product designs, never observed manufacturer facts.
Dimensions are width/depth/height in cm, and never enter the image prompt.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    key: str
    product_class: str
    subject: str
    materials: tuple[str, ...]
    designs: tuple[str, ...]
    dimensions: tuple[float, float, float]
    price: float
    category: str = ''


def profile(key, product_class, subject, materials, designs, dimensions, price, category=''):
    return Profile(key, product_class, subject, tuple(materials.split('|')),
                   tuple(designs.split('|')), dimensions, price, category)


EXISTING_QUOTAS = {
    'Furniture': (6500, 240), 'Kitchen & Tabletop': (3500, 130),
    'Bed & Bath': (3000, 110), 'Lighting': (2500, 100), 'Outdoor': (2500, 100),
    'Décor & Pillows': (2000, 80), 'Rugs': (2000, 80),
    'Storage & Organization': (2000, 70), 'Home Improvement': (2000, 60),
    'Baby & Kids': (1000, 30),
}

EXISTING = {
    'Furniture': [
        profile('armchair', 'Accent Chairs', 'upholstered armchair', 'Linen Blend|Velvet|Polyester', 'curved back and tapered legs|square arms and a loose seat cushion|rounded arms and a channelled back|wood-framed arms and an upholstered back', (82,85,88), 349),
        profile('coffee-table', 'Coffee & Cocktail Tables', 'coffee table', 'Solid Wood|Engineered Wood|Bamboo', 'slatted lower shelf and square legs|rounded top corners and splayed legs|solid panel sides and an open shelf|recessed apron and straight legs', (105,58,43), 229),
        profile('side-table', 'End Tables', 'side table', 'Solid Wood|Engineered Wood|Bamboo', 'open lower shelf and tapered legs|single drawer and straight legs|cross-braced sides and an open shelf|rounded corners and panel sides', (50,45,55), 129),
        profile('bookcase', 'Bookcases', 'freestanding bookcase', 'Solid Wood|Engineered Wood|Bamboo', 'open back and evenly spaced shelves|closed back and recessed shelves|alternating open compartments|arched top and open shelves', (80,30,155), 249),
        profile('desk', 'Desks', 'writing desk', 'Solid Wood|Engineered Wood|Bamboo', 'single shallow drawer and tapered legs|open side cubby and straight legs|rounded desktop corners and panel legs|recessed drawer and cross-braced legs', (120,60,75), 279),
        profile('nightstand', 'Nightstands', 'nightstand', 'Solid Wood|Engineered Wood|Bamboo', 'single drawer over an open shelf|two drawers with inset pulls|open cubby above a lower drawer|slatted door and short legs', (48,40,58), 159),
        profile('dining-chair', 'Dining Chairs', 'dining chair', 'Solid Wood|Bamboo|Metal', 'slatted back and flat seat|curved backrest and tapered legs|ladder back and straight legs|open geometric back and rounded seat', (48,54,86), 139),
        profile('bench', 'Benches', 'indoor bench', 'Solid Wood|Engineered Wood|Bamboo', 'slatted seat and straight legs|solid seat and splayed legs|open storage shelf below the seat|panel sides and rounded seat corners', (110,40,46), 179),
    ],
    'Kitchen & Tabletop': [
        profile('mug', 'Mugs & Teacups', 'single ceramic mug', 'Ceramic|Porcelain', 'rounded body and loop handle|straight-sided body and broad handle|tapered body and small foot|gently fluted body and curved handle', (12,9,10), 19),
        profile('bowl', 'Dining Bowls', 'single dining bowl', 'Ceramic|Porcelain|Bamboo', 'rounded sides and a low foot|wide rim and shallow body|steep sides and a narrow foot|subtle exterior fluting and smooth interior', (22,22,8), 24),
        profile('canister', 'Canisters & Jars', 'single storage canister with lid', 'Ceramic|Glass|Metal', 'straight-sided body and flat lid|ribbed sides and domed lid|rounded shoulders and inset lid|tapered body and loop-handled lid', (14,14,20), 32),
        profile('cutting-board', 'Cutting Boards', 'single cutting board', 'Solid Wood|Bamboo', 'rounded rectangular body with no handle|paddle form with an integral handle|rectangular body with recessed edge groove|rounded ends and a small hanging opening', (36,25,2.5), 29),
        profile('serving-tray', 'Serving Dishes & Platters', 'single serving tray', 'Solid Wood|Bamboo|Metal', 'raised rim and cutout handles|rounded corners and flat handles|low continuous rim with no handles|sloping sides and recessed handles', (40,28,5), 39),
        profile('cooking-spoon', 'Cooking Utensils', 'single cooking spoon', 'Solid Wood|Bamboo|Metal', 'rounded bowl and straight handle|oval bowl and curved handle|shallow bowl and broad handle|rounded bowl and tapered handle', (7,32,3), 15),
    ],
    'Bed & Bath': [
        profile('flat-sheet', 'Sheets And Sheet Sets', 'single flat bed sheet neatly draped over a plain low display stand', 'Cotton|Linen Blend|Polyester', 'broad plain hem|narrow stitched border|subtle woven stripe|plain weave with a contrasting edge', (200,240,0.2), 49),
        profile('bath-mat', 'Bath Rugs & Mats', 'single bath mat laid flat', 'Cotton|Polyester', 'raised border and plain center|parallel ribbed texture|subtle diamond texture|rounded corners and looped pile', (55,85,1.5), 29),
        profile('towel', 'Bath Towels', 'single bath towel neatly folded', 'Cotton|Linen Blend', 'broad woven end border|narrow ribbed end border|waffle weave throughout|soft looped surface and plain hems', (70,130,0.5), 25),
        profile('shower-curtain', 'Shower Curtains', 'single shower curtain hanging flat from a plain rod', 'Polyester|Cotton', 'narrow vertical woven stripes|broad horizontal color bands|subtle geometric pattern|plain textured fabric', (180,180,0.2), 39),
    ],
    'Lighting': [
        profile('table-lamp', 'Table Lamps', 'single table lamp with a plain fabric shade', 'Ceramic|Metal|Solid Wood', 'tapered base and drum shade|rounded base and conical shade|ribbed base and straight shade|slender stem and broad low base', (30,30,52), 99),
        profile('floor-lamp', 'Floor Lamps', 'single floor lamp with a plain fabric shade', 'Metal|Solid Wood|Bamboo', 'straight stem and drum shade|tripod legs and tapered shade|gently curved stem and bowl shade|column base and cylindrical shade', (40,40,160), 159),
        profile('pendant', 'Pendant Lights', 'single pendant light suspended from one plain cable', 'Metal|Glass|Bamboo', 'broad dome shade|tall bell shade|rounded globe shade|shallow bowl shade', (38,38,32), 119),
        profile('sconce', 'Wall Sconces', 'single wall sconce mounted on a plain wall', 'Metal|Ceramic|Glass', 'short arm and downward bell shade|rounded half-cylinder shade|straight arm and small drum shade|shallow curved shield shade', (20,23,30), 79),
    ],
    'Outdoor': [
        profile('patio-chair', 'Patio Lounge Chairs', 'single outdoor lounge chair', 'Metal|Solid Wood|Rattan', 'slatted back and broad arms|woven seat and rounded back|reclined back and straight arms|open geometric back and low seat', (72,80,84), 219),
        profile('planter', 'Planters', 'single empty planter', 'Ceramic|Metal|Plastic', 'tapered cylindrical body|rounded bowl body on a low foot|square body with recessed base|ribbed cylinder with a broad rim', (35,35,40), 59),
        profile('patio-table', 'Patio Tables', 'single patio table', 'Metal|Solid Wood|Bamboo', 'slatted top and straight legs|rounded top and splayed legs|solid top with cross-braced legs|panel sides and narrow slatted top', (100,65,74), 229),
        profile('deck-box', 'Deck Boxes', 'single closed outdoor storage box', 'Plastic|Solid Wood|Metal', 'horizontal slatted sides and flat lid|vertical panel sides and recessed handles|plain sides and raised lid rim|ribbed sides and overhanging lid', (110,55,58), 169),
    ],
    'Décor & Pillows': [
        profile('pillow', 'Accent Pillows', 'single filled accent pillow', 'Cotton|Linen Blend|Velvet', 'piped edges and plain face|subtle geometric embroidery|broad textured stripes|small woven diamond pattern', (45,45,14), 35),
        profile('vase', 'Vases, Urns, Jars, & Bottles', 'single empty decorative vase', 'Ceramic|Glass|Metal', 'rounded body and narrow neck|tall straight-sided body|ribbed body and flared rim|low wide body and short neck', (20,20,32), 39),
        profile('candle-holder', 'Candle Holders', 'single empty candle holder', 'Ceramic|Glass|Metal', 'slender stem and broad foot|short pedestal and shallow cup|ribbed cylindrical body|rounded base and narrow cup', (13,13,22), 25),
        profile('mirror', 'Wall & Accent Mirrors', 'single framed wall mirror', 'Solid Wood|Metal|Bamboo', 'rounded rectangular frame|oval frame|arched rectangular frame|rectangular frame with softened corners', (60,4,90), 99),
    ],
    'Rugs': [
        profile('area-rug', 'Area Rugs', 'single rectangular area rug laid flat', 'Wool|Cotton|Polypropylene', 'subtle diamond lattice|broad irregular color blocks|narrow repeating stripes|bordered field with small geometric motifs', (160,230,1), 149),
        profile('runner-rug', 'Area Rugs', 'single narrow runner rug laid flat', 'Wool|Cotton|Polypropylene', 'subtle diamond lattice|broad alternating bands|narrow repeating stripes|bordered field with small geometric motifs', (70,240,1), 89),
        profile('round-rug', 'Area Rugs', 'single round area rug laid flat', 'Wool|Cotton|Jute', 'concentric woven rings|subtle radial geometric pattern|plain textured center and broad border|interlaced braided surface', (150,150,1), 139),
        profile('outdoor-rug', 'Area Rugs', 'single rectangular outdoor rug laid flat', 'Polypropylene|Polyester', 'broad striped pattern|small geometric lattice|plain textured field and border|large stepped geometric pattern', (150,210,0.6), 99),
    ],
    'Storage & Organization': [
        profile('basket', 'Boxes, Bins, Baskets, & Buckets', 'single empty storage basket', 'Bamboo|Rattan|Plastic', 'open weave and cutout handles|tight weave and loop handles|ribbed sides and flat rim|rectangular body with rounded corners', (38,30,28), 35),
        profile('shelf', 'Wall Mounted Shelves', 'single wall-mounted shelf', 'Solid Wood|Engineered Wood|Metal', 'flat board and concealed support|raised back edge and open sides|low side rails and straight front|open cubby beneath a flat top', (75,22,18), 49),
        profile('garment-rack', 'Clothing & Garment Racks', 'single empty garment rack', 'Metal|Bamboo|Solid Wood', 'single hanging rail and lower shelf|hanging rail with side shelf tower|open A-frame and lower crossbar|straight frame and slatted bottom shelf', (95,45,150), 89),
        profile('hamper', 'Hampers & Baskets', 'single laundry hamper', 'Bamboo|Rattan|Plastic', 'slatted sides and flat lid|open weave with a hinged lid|ribbed body and lift-off lid|rounded corners and recessed handles', (42,35,60), 59),
    ],
    'Home Improvement': [
        profile('cabinet-pull', 'Cabinet and Drawer Pulls', 'single cabinet handle without packaging', 'Metal|Solid Wood|Ceramic', 'straight bar and short round posts|curved arch with concealed posts|rectangular bar and square posts|slim tapered bar and rounded posts', (16,3,3), 12),
        profile('cabinet-knob', 'Cabinet and Drawer Knobs', 'single cabinet knob without packaging', 'Metal|Solid Wood|Ceramic', 'round mushroom form|faceted round form|small square form with rounded edges|short cylindrical form with recessed face', (4,4,3), 9),
        profile('robe-hook', 'Towel & Robe Hooks', 'single wall-mounted robe hook', 'Metal|Solid Wood|Ceramic', 'curved single hook and round plate|angular hook and square plate|rounded peg and oval plate|broad curved hook and hidden plate', (8,7,10), 19),
        profile('tile', 'Floor & Wall Tile', 'single uninstalled square decorative tile', 'Ceramic|Porcelain|Stone', 'plain matte face|subtle linear relief|small geometric surface pattern|softly mottled surface', (30,30,1), 12),
    ],
    'Baby & Kids': [
        profile('kids-bookcase', 'Kids Bookcases', 'single low bookcase', 'Solid Wood|Engineered Wood|Bamboo', 'front-facing book ledges|open horizontal shelves|stepped open compartments|rounded top and open shelves', (75,30,85), 119),
        profile('kids-chair', 'Kids Chairs', 'single small chair', 'Solid Wood|Bamboo|Plastic', 'rounded back and straight legs|slatted back and tapered legs|curved back and broad seat|open geometric back and short legs', (36,38,55), 59),
        profile('toy-storage', 'Toy Boxes and Organizers', 'single low toy storage unit', 'Solid Wood|Engineered Wood|Bamboo', 'open cubbies and rounded corners|slanted open bins|flat lid and inset handles|open upper shelf and lower compartments', (80,35,65), 99),
        profile('kids-desk', 'Kids Desks', 'single small writing desk', 'Solid Wood|Engineered Wood|Bamboo', 'open side cubby and flat top|shallow drawer and straight legs|rounded corners and panel sides|slatted side panel and open shelf', (85,45,62), 139),
    ],
}

# area: (existing parent path, standalone quota, parent quota, new leaf profiles).
EXPANSIONS = {
    'office': ('Furniture/Office Furniture', 2480, 180, [
        profile('monitor-riser', 'Monitor Risers', 'desktop monitor riser', 'Solid Wood|Bamboo|Metal', 'open space beneath a flat top|shallow drawer beneath the top|side cubby and open center|rounded top corners and straight supports', (55,24,12), 49, 'Monitor Risers'),
        profile('desktop-shelf', 'Desktop Shelving', 'desktop shelving unit', 'Solid Wood|Engineered Wood|Metal', 'two open shelves|stepped open shelves|asymmetric open cubbies|arched sides and flat shelves', (60,20,45), 69, 'Desktop Shelving'),
        profile('desk-drawer', 'Under-Desk Drawers', 'under-desk drawer unit', 'Metal|Engineered Wood|Bamboo', 'single shallow drawer|two stacked shallow drawers|divided open-front drawer|recessed pull and rounded corners', (40,30,12), 59, 'Under-Desk Drawers'),
        profile('cable-tray', 'Desk Cable Trays', 'empty under-desk cable tray', 'Metal|Plastic', 'open wire sides|perforated solid sides|slatted base and raised edges|rounded basket form', (50,15,10), 29, 'Desk Cable Trays'),
    ]),
    'entryway': ('Furniture/Entry & Mudroom Furniture', 2040, 140, [
        profile('shoe-bench', 'Modular Shoe Benches', 'shoe storage bench', 'Solid Wood|Engineered Wood|Bamboo', 'open cubbies beneath a flat seat|slatted shoe shelves|vertical dividers beneath a rounded seat|open center and closed side cubby', (100,35,46), 159, 'Modular Shoe Benches'),
        profile('entry-cabinet', 'Wall-Mounted Entry Cabinets', 'wall-mounted entry cabinet', 'Solid Wood|Engineered Wood|Metal', 'two plain doors|slatted sliding doors|open cubby above a small door|recessed doors and rounded corners', (70,25,60), 149, 'Wall-Mounted Entry Cabinets'),
        profile('cubby-tower', 'Entryway Cubby Towers', 'narrow cubby tower', 'Solid Wood|Engineered Wood|Bamboo', 'evenly spaced open cubbies|alternating tall and short cubbies|open upper cubbies and lower drawer|slatted sides and open cubbies', (38,32,150), 179, 'Entryway Cubby Towers'),
        profile('entry-shelf', 'Entryway Organizer Shelves', 'wall-mounted entryway organizer shelf', 'Solid Wood|Bamboo|Metal', 'top shelf and rounded hooks|small open cubbies and hooks|slatted back and shallow shelf|side pocket and a row of hooks', (60,18,30), 69, 'Entryway Organizer Shelves'),
    ]),
    'laundry': ('Storage & Organization/Cleaning & Laundry Organization', 1920, 120, [
        profile('laundry-cabinet', 'Laundry Wall Cabinets', 'wall-mounted laundry cabinet', 'Engineered Wood|Metal|Solid Wood', 'two plain doors|slatted doors|open shelf beneath the doors|rounded corners and recessed pulls', (75,30,65), 179, 'Laundry Wall Cabinets'),
        profile('folding-counter', 'Laundry Folding Counters', 'freestanding laundry folding counter', 'Solid Wood|Bamboo|Engineered Wood', 'plain top and open legs|slatted lower shelf|side cubby and flat top|rounded corners and panel sides', (110,55,90), 189, 'Laundry Folding Counters'),
        profile('pullout-hamper', 'Pull-Out Hamper Units', 'freestanding pull-out hamper cabinet', 'Engineered Wood|Bamboo|Metal', 'single tilt-out front|two separate tilt-out fronts|upper drawer and lower pull-out bin|open shelf above a single hamper', (65,40,85), 149, 'Pull-Out Hamper Units'),
        profile('laundry-sorter', 'Modular Laundry Sorting Stations', 'laundry sorting station with plain removable bags', 'Metal|Bamboo|Solid Wood', 'two separate fabric bags|three separate fabric bags|two bags below a slatted shelf|three bags below a flat folding top', (90,40,85), 109, 'Modular Laundry Sorting Stations'),
    ]),
    'garage': ('Storage & Organization/Garage & Outdoor Storage & Organization', 2040, 140, [
        profile('workbench', 'Workbenches', 'empty workshop workbench', 'Metal|Solid Wood|Bamboo', 'flat top and lower shelf|flat top and shallow drawers|cross-braced legs and open base|flat top and one side cabinet', (140,65,90), 329, 'Workbenches'),
        profile('tool-wall', 'Modular Tool Walls', 'empty wall-mounted tool organizer panel', 'Metal|Plastic|Solid Wood', 'slotted panel with plain hooks|open rail with small trays|perforated panel with shelves|slatted panel with short brackets', (90,18,65), 99, 'Modular Tool Walls'),
        profile('parts-cabinet', 'Small-Parts Drawer Cabinets', 'small-parts storage drawer cabinet', 'Metal|Plastic|Engineered Wood', 'grid of equal small drawers|mixed small and wide drawers|wide shallow drawers|recessed drawers with plain pull tabs', (50,25,55), 119, 'Small-Parts Drawer Cabinets'),
        profile('work-cart', 'Rolling Work Carts', 'empty rolling workshop cart', 'Metal|Solid Wood|Engineered Wood', 'two open shelves and casters|three open shelves and casters|top drawer and lower shelf|raised top rim and lower cabinet', (80,45,85), 169, 'Rolling Work Carts'),
    ]),
    'pet': ('Pet', 2360, 160, [
        profile('litter-cabinet', 'Litter-Box Furniture', 'empty furniture-style litter enclosure', 'Engineered Wood|Solid Wood|Bamboo', 'side entrance and two front doors|arched front entrance and side cabinet|slatted front with side opening|rounded corners and large side entry', (85,50,55), 149, 'Litter-Box Furniture'),
        profile('cat-wall', 'Wall-Mounted Cat Furniture', 'single wall-mounted cat perch', 'Solid Wood|Bamboo|Engineered Wood', 'flat platform with raised back|curved shallow cradle|open box with a rounded entrance|platform with a soft inset pad', (55,30,20), 59, 'Wall-Mounted Cat Furniture'),
        profile('feeding-station', 'Pet Feeding Stations', 'pet feeding stand with two plain empty bowls', 'Solid Wood|Bamboo|Metal', 'flat top and open legs|raised sides and recessed bowls|open shelf beneath the bowls|rounded corners and panel supports', (50,25,22), 69, 'Pet Feeding Stations'),
        profile('pet-crate', 'Furniture-Style Pet Crates', 'empty furniture-style pet crate', 'Solid Wood|Engineered Wood|Metal', 'barred sides and flat tabletop|slatted sides and front door|rounded top corners and open bars|panel back and ventilated sides', (90,60,65), 249, 'Furniture-Style Pet Crates'),
    ]),
    'balcony': ('Outdoor/Small-Space Outdoor', 1800, 100, [
        profile('balcony-table', 'Balcony Tables', 'compact balcony table', 'Metal|Solid Wood|Bamboo', 'slatted rectangular top|rounded rectangular top|half-round top and straight legs|narrow top with folding legs', (65,45,74), 109, 'Balcony Tables'),
        profile('folding-chair', 'Folding Outdoor Seating', 'single folding outdoor chair', 'Metal|Solid Wood|Bamboo', 'slatted back and seat|woven seat and open back|solid rounded backrest|narrow slats and gently curved back', (46,55,82), 89, 'Folding Outdoor Seating'),
        profile('narrow-bench', 'Narrow Outdoor Storage Benches', 'narrow outdoor storage bench', 'Solid Wood|Metal|Plastic', 'slatted sides and flat seat lid|plain sides and inset handles|open lower shelf and flat seat|vertical panels and rounded corners', (100,32,48), 149, 'Narrow Outdoor Storage Benches'),
        profile('rail-planter', 'Railing Planters', 'single empty railing planter with integral brackets', 'Metal|Plastic|Ceramic', 'long shallow trough|rounded rectangular body|ribbed trough with flat rim|tapered body with broad top', (50,22,24), 39, 'Railing Planters'),
    ]),
    'garden': ('Outdoor/Garden', 1400, 100, [
        profile('raised-planter', 'Raised Planter Systems', 'single empty raised planter', 'Solid Wood|Metal|Plastic', 'rectangular box on straight legs|deep box with lower shelf|slatted sides and tapered legs|rounded corners and open base', (100,45,78), 139, 'Raised Planter Systems'),
        profile('seed-shelf', 'Seed-Starting Shelves', 'empty seed-starting shelving unit without lights', 'Metal|Bamboo|Solid Wood', 'three open flat shelves|four narrow shelves|stepped open shelves|slatted shelves and cross-braced sides', (80,40,140), 119, 'Seed-Starting Shelves'),
        profile('vertical-frame', 'Vertical Garden Frames', 'empty vertical garden frame', 'Metal|Solid Wood|Bamboo', 'stacked shallow planter troughs|grid of open planter holders|ladder form with attached boxes|slatted frame with staggered planters', (75,30,150), 149, 'Vertical Garden Frames'),
        profile('compost-bin', 'Compost Bins', 'closed garden compost bin', 'Plastic|Metal|Solid Wood', 'slatted sides and flat lid|ribbed sides and lift-off lid|ventilated panels and low access door|plain panels with narrow ventilation slots', (65,65,90), 109, 'Compost Bins'),
    ]),
    'pantry': ('Kitchen & Tabletop/Kitchen Organization', 804, 60, [
        profile('coffee-organizer', 'Coffee-Station Organizers', 'empty coffee-station organizer', 'Solid Wood|Bamboo|Metal', 'open trays and a shallow drawer|stepped open compartments|flat top and divided lower shelf|small cubbies beside a shallow tray', (40,25,25), 49, 'Coffee-Station Organizers'),
        profile('mug-insert', 'Mug-Storage Inserts', 'empty mug-storage cabinet insert', 'Solid Wood|Bamboo|Metal', 'two open shelf tiers|grid of open compartments|stepped shelves with rounded corners|open shelf and hanging hooks', (40,25,30), 39, 'Mug-Storage Inserts'),
        profile('pantry-insert', 'Pantry Drawer Inserts', 'empty pantry drawer organizer insert', 'Solid Wood|Bamboo|Plastic', 'parallel long compartments|mixed rectangular compartments|stepped shallow sections|rounded compartments and a flat border', (45,35,8), 35, 'Pantry Drawer Inserts'),
        profile('canister-rack', 'Modular Canister Racks', 'empty countertop canister rack', 'Metal|Bamboo|Solid Wood', 'two open tiers|three stepped shelves|side rails and two flat shelves|open cubbies and a flat top', (45,24,40), 49, 'Modular Canister Racks'),
    ]),
}

NAME_FIRST = 'Alder Ash Aspen Bay Birch Briar Brook Cedar Clay Cliff Cove Dawn Dune Elm Fern Field Flint Glen Harbor Hazel Heath Hill Holly Juniper Lake Laurel Linden Maple Meadow Moss Oak Olive Pine Reed Ridge River Rowan Sage Shore Slate Spruce Stone Summit Vale Willow Wren'.split()
NAME_LAST = 'Arc Bend Bluff Branch Bridge Brook Canyon Crest Crossing Dale Dell Edge Falls Field Fold Ford Gate Glen Grove Haven Heath Hollow Isle Knoll Lane Landing Leaf Ledge Loop Marsh Mill Moor Nest Park Pass Path Point Reach Ridge Rise Rock Row Run Shade Shore Spring Stone Strand Terrace Trace Trail Vale View Walk Way Well Wood Yard'.split()
