"""Exact remaining-queue resolutions approved for synthetic local lab designs.

Source evidence remains immutable. These choices do not establish manufacturer
assortments, safety, fit, live inventory transfers or permission to import.
"""
import copy
import re

from repair_designs import axis, part
from synthetic_dimensions import option_cm

VERSION = 'wands-definition-resolutions-v1'
APPROVAL = 'User approved coherent synthetic definitions with conflicting WANDS evidence retained.'


def profile(scope, **dimensions):
    return {'scope':scope,'dimensions':dimensions}


RESOLUTION_PROFILES = {
    'rail_cover':profile('one decorative textile laid flat; no rail fit or infant-safety claim',width=30,length=130),
    'changing_cover':profile('one fictional cover exterior; no pad fit or infant-use claim',width=45,length=82,height=10),
    'decorative_mobile':profile('one decorative mobile displayed separately; installation and infant use excluded',width=30,depth=30,height=45),
    'bake_pan':profile('one pan exterior; cooking area, food capacity and temperature rating unspecified',width=30,depth=25,height=6),
    'flat_tray':profile('one baking tray or cooling rack exterior; usable area and heat rating unspecified',width=40,depth=30,height=2),
    'pan_lid':profile('fictional lid exterior paired with its named pan; sealing and temperature ratings unspecified',width=33,depth=23,height=1),
    'flatware_piece':profile('one utensil including its handle; no safety or performance claim',width=3,length=20,height=1),
    'burger_press':profile('one assembled burger press, closed; food capacity and moving clearance unspecified',width=12,depth=12,height=10),
    'fry_cutter':profile('one assembled fry cutter, closed; blade opening and capacity unspecified',width=26,depth=13,height=12),
}


def remaining_rules():
    result={}
    def add(pid,kind,basis,**rule):
        result[f'WANDS-{pid:06d}']={**rule,'resolution_kind':kind,'scope':'remaining_definition_resolution',
            'source_resolution':{'version':VERSION,'approval':APPROVAL,'basis':basis,'original_evidence_retained':True},
            'rationale':basis+' Geometry and changed options are explicit synthetic lab designs.'}
    def textile(identifier,label,key,quantity=1):
        return part(identifier,label,key,quantity)
    def nursery(pid,name,components):
        count=sum(p['quantity'] for p in components)
        add(pid,'nursery_assortment','Use the source-named component roles and quantities; remove generated adult-bed sizes.',
            name=name,drop_axes=['wands_size'],design={'components':components},expected_component_count=count,
            sale_unit=f'{count} listed nursery-decor pieces',
            copy='A coordinated nursery-decor assortment with each included item listed below. Dimensions describe the separate pieces. Display the assortment laid out, not in use with an infant. Mattresses, cribs and unlisted accessories are excluded.')
    quilt=lambda:textile('quilt','Nursery quilt','nursery_cover')
    blanket=lambda:textile('blanket','Decorative blanket','nursery_cover')
    sheets=lambda n=1:textile('sheets','Fitted crib sheet','crib_sheet',n)
    skirt=lambda:textile('skirt','Crib skirt','crib_skirt')
    diaper=lambda:textile('diaper-stacker','Diaper stacker','fabric_bag')
    rail=lambda:textile('rail-cover','Decorative rail cover','rail_cover')
    nursery(56,'Ocean Baby Three-Piece Nursery Decor Set',[quilt(),sheets(),skirt()])
    nursery(3817,'Pink Chocolate Four-Piece Nursery Decor Set',[quilt(),rail(),sheets(),skirt()])
    nursery(13613,'Amey Woodland Eight-Piece Nursery Decor Set',[
        textile('comforter','Comforter','nursery_cover'),sheets(2),skirt(),textile('pillow','Decorative pillow','pillow'),
        diaper(),blanket(),textile('changing-cover','Changing-pad cover','changing_cover')])
    nursery(17413,'Bainter Ten-Piece Nursery Decor Set',[
        textile('comforter','Comforter','nursery_cover'),sheets(2),skirt(),diaper(),textile('valance','Valance','valance'),
        textile('mobile','Decorative mobile','decorative_mobile'),textile('wall-hangings','Wall hanging','wall_decor',3)])
    for pid,name in [(20998,'Watercolor Floral Five-Piece Nursery Decor Set'),(21006,'Ruched Diamond Five-Piece Nursery Decor Set')]:
        nursery(pid,name,[blanket(),sheets(),skirt(),rail(),diaper()])
    nursery(21081,'Woodsy Eleven-Piece Nursery Decor Set',[blanket(),skirt(),sheets(),
        textile('toy-bag','Toy bag','fabric_bag'),textile('pillow','Decorative pillow','pillow'),diaper(),
        textile('wall-hangings','Wall hanging','wall_decor',3),textile('valances','Valance','valance',2)])
    nursery(30143,'Lewis Penguin Five-Piece Nursery Decor Set',[quilt(),textile('valance','Valance','valance'),
        sheets(),textile('pillow','Decorative pillow','pillow'),skirt()])
    nursery(35175,'Dreamit Muslin Three-Piece Nursery Decor Set',[blanket(),skirt(),sheets()])
    add(18889,'toddler_bed','The title and description identify a toddler frame, not adult-bed variants.',
        name='Clarkson Toddler Bed Frame',drop_axes=['wands_size'],
        design={'profile':'bed','fixed_bed_size':'Toddler','dimensions':{'height':65}},
        sale_unit='1 toddler bed-frame assembly; mattress and bedding excluded',
        copy='A low-profile toddler bed-frame design with a choice of color. There are no twin or full-size versions in this family. The measurements describe the exterior frame, not mattress fit or an age or safety rating.')

    widths=['30 in','36 in','48 in','60 in']
    for pid,name,shape in [(1731,'Hugh Square End Table with Storage','square'),
        (20322,'Morrissey Round Glass-Top End Table','round'),(20551,'Dawson Camden Round End Table','round'),
        (27653,'Paralimni End Table','rectangular'),(42337,'Maison Cross-Leg End Table with Storage','rectangular')]:
        descriptor={'profile':'side_table','bindings':{'wands_length':'width'}}
        if shape in {'round','square'}: descriptor['depth_matches_width']=True
        else: descriptor['dimensions']={'depth':40}
        add(pid,'side_table','Retain end-table identity despite the mixed Nightstands classification. Keep a compact, shape-consistent footprint.',
            name=name,axis=axis('wands_length','Top diameter' if shape=='round' else 'Overall width',widths,['16 in','20 in','24 in','26 in']),
            design=descriptor,design_shape=shape,sale_unit='1 end table',
            copy=f'A {shape} end-table design for use beside seating. The selected measurement describes '+
                ('the top diameter.' if shape=='round' else 'the overall width.')+' Interior storage and clearance dimensions are not specified.')
    add(22607,'plastic_nightstand','Retain the source plastic/PMMA identity; replace incompatible wood-finish labels with Clear and Black.',
        name='Ghost Buster Plastic Nightstand',axis_changes=[
            axis('wands_length','Overall width',widths[:3],['18 in','22 in','26 in']),
            axis('wands_finish','Plastic finish',['Walnut','Oak'],['Clear','Black'])],
        design={'profile':'nightstand','bindings':{'wands_length':'width'},'dimensions':{'depth':40,'height':55}},
        sale_unit='1 plastic nightstand',
        copy='A compact plastic nightstand with a choice of a clear or black finish. The selected width defines the cabinet exterior. Neither option represents a wood species or wood construction.')

    for pid,name,count,old in [
        (2739,'Plaid Pillow Sham',1,['Twin','Full','King']),
        (33289,'Cobleskill Microfiber Pillowcase Pair',2,['Twin','Full','Queen']),
        (34345,'Keratin Krew Pillowcase',1,['Twin','Full','Queen','King'])]:
        lengths=[26,30,36] if len(old)==3 else [26,28,30,36]
        leaf={'profile':'pillowcase','rectangle_axis':'wands_size'}
        descriptor=leaf if count==1 else {'components':[{**part('pillowcases','Pillowcase','pillowcase',2),'rectangle_axis':'wands_size'}]}
        basis={2739:'Choose one sham as the synthetic sale unit, consistent with the singular description; preserve conflicting one/two quantity fields.',
            33289:'Use the explicit numberofpillowcasesincluded=2 field. Missing generic total count does not negate the specific count.',
            34345:'Keep the title-led pillowcase identity as approved; retain the conflicting fitted-sheet source type as evidence.'}[pid]
        add(pid,'pillowcase',basis,name=name,axis=axis('wands_size','Each cover width x length',old,[f'20 in x {n} in' for n in lengths]),
            design=descriptor,sale_unit=f'{count} pillowcase'+('s' if count>1 else '')+'; inserts and sheets excluded',
            copy='A pillow-cover design with explicit laid-flat dimensions for each cover. The size choices describe the cover itself, not a mattress or fitted sheet.')

    # Furniture assemblies are counted separately from fitted upholstery and
    # explicitly listed loose pillows. Variants add named seating roles only.
    chair=lambda n=1,label='Cushioned lounge chair':part('chairs',label,'patio_chair',n)
    sofa=lambda n=1:part('sofas','Cushioned sofa','patio_sofa',n)
    loveseat=lambda n=1:part('loveseats','Cushioned loveseat','patio_sofa',n,width=140,seat_width=110)
    table=lambda n=1:part('tables','Coffee table','coffee_table',n)
    ottoman=lambda n=1:part('ottomans','Cushioned ottoman','ottoman',n)
    armless=lambda n=1:part('armless','Cushioned armless seating module','patio_chair',n)
    corners=lambda n=1:part('corners','Cushioned corner seating module','patio_chair',n)
    pillows=lambda n=2:{**part('pillows','Decorative pillow','pillow',n),'counts_as_furniture':False}
    def outdoor(pid,name,components,variable_role,basis):
        base=sum(c['quantity'] for c in components if c.get('counts_as_furniture',True))
        variants={}
        for extra in range(4):
            parts=copy.deepcopy(components)
            next(c for c in parts if c['id']==variable_role)['quantity']+=extra
            variants[f'{base+extra} Pieces']={'components':parts}
        add(pid,'outdoor_assortment',basis,name=name,
            axis=axis('wands_piece_count','Furniture pieces',['2 Pieces','3 Pieces','4 Pieces','5 Pieces'],list(variants)),
            design_axis='wands_piece_count',design_variants=variants,
            sale_unit='the listed furniture assemblies; fitted cushions belong to their seats, and loose decorative pillows are included only where listed',
            copy='A coordinated outdoor furniture assortment with every furniture role and quantity named for the selected option. Larger assortments add the specified seating module. The furniture-piece count excludes upholstery cushions and separately listed decorative pillows.')
    outdoor(1200,'Breccan Modular Outdoor Seating Set',[table(),armless(4),corners(2)],'armless',
        'Use the explicit one-table, four-chair and two-corner list as seven furniture assemblies; treat the chairs as armless sectional modules. Conflicting role flags remain in source evidence.')
    outdoor(3695,'Safira Outdoor Loveseat and Chair Set',[chair(4),loveseat(2),table(2)],'chairs',
        'The source list and description agree on four armchairs, two loveseats and two coffee tables.')
    for pid,name in [(7609,'Winston Porter Outdoor Loveseat Set'),(14666,'Silke Outdoor Loveseat Set'),(26191,'Theodore Outdoor Loveseat Set')]:
        outdoor(pid,name,[chair(2),loveseat(),table()],'chairs',
            'Use two chairs, one loveseat and one coffee table. Do not repeat unsupported or conflicting teak/acacia construction claims.')
    outdoor(40330,'Kalmanovitz Outdoor Sofa Set',[sofa(),chair(2),table()],'chairs',
        'Use the source-named sofa, two chairs and table as four furniture assemblies.')
    outdoor(8500,'Eckfried Modular Outdoor Seating Set',[armless(),corners(2),ottoman(),table(),pillows()],'armless',
        'Use the description-named armless module, two corner modules, ottoman and table; two named loose pillows are accessories, not furniture pieces.')
    outdoor(14542,'Merlyn Outdoor Sofa and Ottoman Set',[sofa(),chair(),ottoman(),table(),pillows()],'chairs',
        'Resolve the six-item label as four named furniture assemblies plus two decorative pillows. Larger synthetic options add lounge chairs.')
    outdoor(14655,'Gleisner Modular Outdoor Seating Set',[
        part('club-chairs','Cushioned club chair','patio_chair',2),part('right-arms','Right-arm seating module','patio_chair',2),
        part('left-arms','Left-arm seating module','patio_chair',2),table(),armless(2)],'armless',
        'Choose the explicit nine-piece list and matching title over the conflicting generic five-item field.')
    outdoor(15293,'Handrahan Outdoor Chair and Table Set',[chair(4),table(),part('side-tables','Side table','side_table',2)],'chairs',
        'Preserve the source count of four chairs and three tables; explicitly design the tables as one coffee table and two side tables.')
    outdoor(29757,'Karma Outdoor Sofa and Ottoman Set',[sofa(),chair(2),ottoman(2),pillows()],'chairs',
        'Use the named sofa, two chairs and two ottomans as five furniture assemblies; preserve two decorative pillows as accessories. No table is included.')
    outdoor(30336,'Merlyn Corner Seating and Ottoman Set',[corners(2),armless(2),ottoman(),table()],'armless',
        'Retain the four seating-unit, one-ottoman, one-table count; explicitly choose a synthetic split of two corner and two armless modules.')
    outdoor(30675,'Steward Compact Corner Seating Set',[
        part('two-seat-module','Two-seat corner module','patio_sofa',width=140,seat_width=110),armless(),table()],'armless',
        'Choose the named two-seat sofa, companion seating module and table as three furniture assemblies, resolving the conflicting four-piece title.')
    outdoor(38841,'Billie-Anne Modular Outdoor Seating Set',[
        part('left-arm','Left-arm seating module','patio_chair'),part('right-arm','Right-arm seating module','patio_chair'),
        armless(),part('chaise-ottoman','Chaise ottoman','ottoman',depth=90),table(),
        part('club-chairs','Cushioned club chair','patio_chair',2),ottoman(2),part('accent-table','Accent table','side_table')],'armless',
        'Use the ten roles/counts supported by the source list and description. No sectional parent is counted again on top of its modules.')
    for pid,name,shape,rocking,cushioned in [
        (8443,'Naczi Folding Bistro Set','round',False,False),(14683,'Forbus Half-Round Bistro Set','half-round',False,False),
        (22104,'Folding Steel Bistro Set','round',False,False),(40234,'Dereham Bistro Set','round',False,True),
        (11422,'Swanley Rocking Chair and Table Set','rectangular',True,False),
        (15421,'Beauman Rocking Chair and Table Set','rectangular',True,True),
        (41115,'Faithe Lounge Chair and Table Set','rectangular',False,True)]:
        variants={}
        for chairs in range(2,6):
            width=70+10*(chairs-2)
            depth=width if shape=='round' else width/2 if shape=='half-round' else 50
            label=('Cushioned ' if cushioned else '')+('rocking chair' if rocking else 'bistro chair' if pid in [8443,14683,22104,40234] else 'lounge chair')
            variants[f'{chairs+1} Pieces']={'components':[
                part('table',shape.title()+' table','patio_table' if pid in [8443,14683,22104,40234] else 'side_table',width=width,depth=depth),
                part('chairs',label,'patio_chair' if rocking or pid==41115 else 'dining_chair',chairs)]}
        add(pid,'outdoor_assortment','The source identifies one table and two chairs. Expanded synthetic assortments retain one table and explicitly add chairs.',
            name=name,axis=axis('wands_piece_count','Furniture pieces',['2 Pieces','3 Pieces','4 Pieces','5 Pieces'],list(variants)),
            design_axis='wands_piece_count',design_variants=variants,
            sale_unit='1 table and the listed chairs'+('; fitted seat cushions included' if cushioned else '; loose cushions excluded'),
            copy='A coordinated table-and-chair assortment. The selected furniture count includes one table, with every remaining furniture piece a chair. Dimensions apply to individual pieces, not an installed arrangement.')
    add(42749,'outdoor_assortment','Approved synthetic resolution: one table and four chairs, consistent with the five-piece title and four-person field; conflicting five-chair/six-piece fields remain in evidence.',
        name='Abe Five-Piece Patio Dining Set',drop_axes=['wands_piece_count'],expected_component_count=5,
        design={'components':[part('table','Round dining table','patio_table',width=110,depth=110),part('chairs','Dining chair','dining_chair',4)]},
        sale_unit='1 table and 4 chairs; cushions excluded',
        copy='A five-piece patio dining assortment with one round table and four matching chairs. Select the color; the assortment quantity stays fixed.')

    add(3897,'bakeware','Approved synthetic ten-piece allocation: two round cake pans, one square cake pan, one rectangular cake pan and its lid, one loaf pan, one muffin pan, one cooling rack and two baking sheets.',
        name='Copper-Finish Ten-Piece Bakeware Set',expected_component_count=10,
        design={'components':[part('round-pans','Round cake pan','bake_pan',2,width=23,depth=23,height=5),
            part('square-pan','Square cake pan','bake_pan',width=23,depth=23,height=5),
            part('rectangular-pan','Rectangular cake pan','bake_pan',width=33,depth=23,height=5),
            part('lid','Lid for the rectangular pan','pan_lid'),part('loaf-pan','Loaf pan','bake_pan',width=26,depth=13,height=8),
            part('muffin-pan','Muffin pan','bake_pan',width=35,depth=26,height=4),
            part('rack','Cooling rack','flat_tray'),part('sheets','Baking sheet','flat_tray',2)]},
        sale_unit='10 listed pieces, including the rectangular-pan lid',
        copy='A coordinated bakeware assortment with every pan, tray, rack and lid counted separately. The lid is paired only with the rectangular pan. No oven-temperature, nonstick-performance, sealing or food-capacity claim is made.')
    flatware=[part('teaspoons','Teaspoon','flatware_piece',8,length=14),part('dinner-forks','Dinner fork','flatware_piece',8),
        part('dinner-knives','Dinner knife','flatware_piece',8,width=2,length=23),
        part('salad-forks','Salad fork','flatware_piece',8,length=17),part('tablespoons','Tablespoon','flatware_piece',8,width=4),
        part('slotted-spoon','Slotted serving spoon','flatware_piece',width=5,length=25),
        part('spreader','Spreader','spreader'),part('serving-fork','Serving fork','serving_fork'),
        part('cake-server','Cake server','cake_server'),part('serving-spoon','Serving spoon','flatware_piece',width=5,length=25)]
    add(17842,'flatware','Approved synthetic allocation: eight five-piece place settings and one each of five named serving utensils; conflicting serving-item flags remain in evidence.',
        name='Skaneateles Forty-Five-Piece Flatware Set',design={'components':flatware},expected_component_count=45,
        sale_unit='8 five-piece place settings plus 5 serving utensils',
        copy='A 45-piece flatware assortment. Each place setting contains a teaspoon, dinner fork, dinner knife, salad fork and tablespoon. The five serving utensils are listed separately below.')
    add(22642,'kitchen_tools','Approved title/description-led resolution: two assembled tools, not five unidentified removable parts.',
        name='Kitchenworthy Burger Press and Fry Cutter Set',expected_component_count=2,
        design={'components':[part('burger-press','Assembled burger press','burger_press'),part('fry-cutter','Assembled fry cutter','fry_cutter')]},
        sale_unit='1 assembled burger press and 1 assembled fry cutter',
        copy='A two-tool kitchen assortment with a burger press and a fry cutter. Each tool is counted as one assembled unit; internal parts are not additional products. Food capacity, blade dimensions and replacement-part compatibility are unspecified.')
    return result


def validate_resolved_definition(root, children, issues):
    """Check candidate semantics independently of whether a repair flag exists."""
    axes={a['attribute']:a['values'] for a in root['axes']}
    subjects=children or [root]
    for issue in issues:
        if issue=='crib_set_has_bed_size_axis' and 'wands_size' in axes:
            raise ValueError('Crib assortment still has a bed-size axis')
        if issue=='toddler_product_has_non_toddler_sizes' and set(axes.get('wands_size',[]))-{'Toddler'}:
            raise ValueError('Toddler product still offers non-toddler sizes')
        if issue=='toddler_trundle_option' and 'Toddler' in axes.get('wands_size',[]):
            raise ValueError('Trundle still offers Toddler')
        if issue=='triple_bed_levels_undefined' and any(v.count(' over ')!=2 for v in axes.get('wands_size',[])):
            raise ValueError('Triple bed levels remain undefined')
        if issue=='pillowcase_uses_mattress_labels' and any(not re.fullmatch(r'\d+ in x \d+ in',v) for v in axes.get('wands_size',[])):
            raise ValueError('Pillowcase still has mattress labels')
        if issue=='oversized_nightstand_width' and any(option_cm(v)>66.04 for v in axes.get('wands_length',[])):
            raise ValueError('Nightstand/side-table width remains oversized')
        if issue=='kitchen_window_drop_requires_subtype_check' and any(option_cm(v)>114.3 for v in axes.get('wands_length',[])):
            raise ValueError('Kitchen curtain drop remains unreviewed')
        if issue=='liner_has_mat_size_options' and any(option_cm(v.split(' x ')[0])<150 for v in axes.get('wands_size',[])):
            raise ValueError('Liner still has mat-scale dimensions')
        if issue in {'piece_count_needs_explicit_component_manifest','crib_set_has_bed_size_axis'}:
            for subject in subjects:
                # This exact source was a single folding table mistakenly given
                # a set-size axis. Its correction has length options, not parts.
                if (issue=='piece_count_needs_explicit_component_manifest' and root['sku']=='WANDS-035956'
                    and 'wands_piece_count' not in axes and 'wands_length' in axes
                    and subject.get('dimension_design',{}).get('profile')=='patio_table'
                    and subject['catalog_fields'].get('lab_sale_unit')=='1 folding table; chairs and benches excluded'):
                    continue
                parts=subject.get('dimension_design',{}).get('components',[])
                if not parts or len({p['component_id'] for p in parts})!=len(parts) or any(type(p['quantity']) is not int or p['quantity']<1 for p in parts):
                    raise ValueError('Missing or invalid component manifest')
                count=sum(p['quantity'] for p in parts if p.get('counts_as_furniture',True))
                option=subject['variant_options'].get('wands_piece_count')
                if option and count!=int(option.split()[0]): raise ValueError('Furniture option/component count mismatch')
                if sum(p['quantity'] for p in parts)!=subject['dimension_design']['total_component_quantity']:
                    raise ValueError('Total component count mismatch')
    for subject in subjects:
        if subject.get('dimension_design',{}).get('status') not in {'synthetic_design_complete','synthetic_components_complete'}:
            raise ValueError('Corrected definition has no complete dimension design')
    return {'root_sku':root['sku'],'original_issues':issues,'status':'resolved_in_local_candidate',
            'children_checked':len(children),'executable':False,'live_verified':False}
