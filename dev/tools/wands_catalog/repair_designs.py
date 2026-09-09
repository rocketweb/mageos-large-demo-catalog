"""Authored local catalog corrections. New geometry/assortments remain synthetic.

These definitions target the frozen depth-pilot repair queue, not arbitrary
products with similar names. Source conflicts are retained, never voted away.
"""
import copy
from prepare_catalog import parse_features

VERSION = 'wands-catalog-repairs-v3'
DISCLOSURE = 'Synthetic lab product design; options and assortments are not manufacturer-verified.'


def part(identifier, label, profile, quantity=1, **dimensions):
    return {'id': identifier, 'label': label, 'profile': profile, 'quantity': quantity,
            'dimensions': dimensions}


def axis(code, label, old, new, target=None):
    return {'from': code, 'to': target or code, 'label': label, 'map': dict(zip(old, new))}


def expansion_rule(row, family):
    """Explicitly reviewed identities, with source-role and option-schema guards.

    This is not a class-wide rewrite. A listed identity that has drifted returns
    a hold; an unreviewed identity returns None. Existing prices/SKUs are kept.
    """
    pid = int(row['product_id'])
    name = row['product_name'].casefold()
    features = {k:[v.casefold() for v in values] for k,values in parse_features(row['product_features']).items()}
    axes = {a['attribute']:a['values'] for a in family['axes']}
    def hold(reason):
        return {'hold_reason':reason, 'scope':'full_catalog_expansion'}
    nightstands = {
        4322:'One-Drawer Nightstand in Walnut', 4880:'Mirefield Cylindrical Two-Drawer Nightstand',
        8809:'Zinnia Two-Drawer Nightstand', 15548:'Cornell Nightstand',
        17064:'Loft One-Drawer Nightstand', 20704:'Voelker Two-Drawer Nightstand',
        25039:'Remillard One-Drawer Nightstand', 26445:'Chauvin Mid-Century Nightstand',
        27042:'Wellinhall One-Drawer Nightstand', 39471:'Colrain Two-Drawer Nightstand in Silver',
        41691:'Teixeira One-Drawer Nightstand', 42710:'Kepner Two-Drawer Nightstand',
    }
    if pid in nightstands:
        old = axes.get('wands_length')
        if 'nightstand' not in name or 'nightstands' not in row['product_class'].casefold():
            return hold('Reviewed nightstand source identity changed.')
        if old not in [['30 in','36 in','48 in'], ['30 in','36 in','48 in','60 in']] or set(axes)-{'wands_length','wands_finish'}:
            return hold('Nightstand option schema differs from the reviewed three/four-width family.')
        if any('plastic' in v or 'pmma' in v for k,vv in features.items() if 'material' in k for v in vv):
            return hold('Plastic construction needs separate finish and shape reconciliation.')
        if pid == 4880 and 'cylindrical' not in name:
            return hold('Cylindrical nightstand shape evidence changed.')
        design = {'profile':'nightstand','bindings':{'wands_length':'width'}}
        if pid == 4880: design['depth_matches_width'] = True
        return {'name':nightstands[pid], 'axis':axis('wands_length','Overall width',old,
            ['18 in','22 in','26 in'] if len(old)==3 else ['16 in','20 in','24 in','26 in']),
            'design':design, 'sale_unit':'1 nightstand',
            'copy':'A bedside storage cabinet offered in compact widths. The selected width describes the overall cabinet, not a drawer interior.',
            'rationale':'Extend the tested nightstand-width correction to this reviewed source identity. Geometry and retained finish options are synthetic; conflicting construction claims are not repeated.',
            'scope':'full_catalog_expansion'}
    if pid == 22607:
        return hold('Ghost Buster has plastic/PMMA construction but generated Walnut/Oak finishes. Resolve finish and material identity together before correcting its width.')
    pillowcases = {1981:('Comfort Body Pillowcase',True,1),2024:('Ajah Sherpa Body Pillowcase',True,1),
        2739:('Pillowcase',False,1),11019:('Blew Pillowcase',False,1),
        20967:('Plaid Flannel Body Pillowcase',True,1),33289:('Cobleskill Pillowcase Pair',False,2),
        37955:('Oberlin Ticking Striped Cotton Pillowcase Pair',False,2)}
    if pid in pillowcases:
        title,body,count = pillowcases[pid]
        counts=set(features.get('numberofpiecesincluded',[])+features.get('numberofpillowcasesincluded',[]))
        if counts != {str(count)}:
            return hold('Pillowcase quantity fields are missing or conflicting; keep sale unit unresolved.')
        required={'producttype':{'pillowcase'},'flatsheetincluded':{'no'},'fittedsheetincluded':{'no'},'pillowcaseincluded':{'yes'}}
        if 'pillowcase' not in name or any(set(features.get(k,[]))!=v for k,v in required.items()):
            return hold('Pillowcase identity or included-sheet evidence differs from the reviewed role.')
        subtype=set(features.get('pillowcasetype',[]))
        if (body and subtype!={'body pillow'}) or (not body and (not subtype <= {'standard','king'} or (not subtype and pid!=33289))):
            return hold('Pillowcase subtype needs separate geometry review.')
        old=axes.get('wands_size')
        if old not in [['Twin','Full','Queen'],['Twin','Full','King'],['Twin','Full','Queen','King']] or set(axes)-{'wands_size','color'}:
            return hold('Pillowcase option schema differs from reviewed mattress-label mappings.')
        lengths=([48,54,60] if len(old)==3 else [48,52,54,60]) if body else ([26,30,36] if len(old)==3 else [26,28,30,36])
        descriptor={'profile':'pillowcase','rectangle_axis':'wands_size'}
        if count==2:
            descriptor={'components':[{**part('pillowcases','Pillowcase','pillowcase',2),'rectangle_axis':'wands_size'}]}
        return {'name':title,'axis':axis('wands_size','Each pillowcase width x length',old,[f'20 in x {n} in' for n in lengths]),
            'design':descriptor,'sale_unit':f'{count} pillowcase'+('s' if count>1 else '')+'; pillow inserts and sheets excluded',
            'copy':'A pillowcase design with explicit laid-flat dimensions for each case. The selected dimensions describe a cover, not a mattress or a sheet set.',
            'rationale':'Extend the tested pillowcase-size correction only after agreeing source quantity, product type, included items and subtype. Dimensions are synthetic, not verified insert fit.',
            'scope':'full_catalog_expansion'}
    if pid == 26409:
        if 'trundle' not in name or set(features.get('producttype',[]))!={'daybed'} or axes!={'wands_size':['Toddler','Twin','Full','Queen']}:
            return hold('Geary daybed identity or size schema differs from reviewed source evidence.')
        return {'name':'Geary Daybed with Stowed Trundle',
            'axis':axis('wands_size','Main bed size',axes['wands_size'],['Twin','Twin XL','Full','Queen']),
            'design':{'profile':'trundle_frame','bed_axis':'wands_size'},
            'sale_unit':'1 daybed frame with 1 stowed trundle; mattresses excluded',
            'copy':'A daybed frame with a pull-out trundle stored underneath. The size option describes the main bed; dimensions show the closed exterior only.',
            'rationale':'Extend the tested non-toddler trundle correction to the reviewed daybed. No mattress-fit, motion clearance or safety claim.',
            'scope':'full_catalog_expansion'}
    return None


def rules():
    result = {}
    def add(ids, **rule):
        for pid in ids:
            result[f'WANDS-{pid:06d}'] = copy.deepcopy(rule)

    lengths = ['63 in','84 in','95 in','108 in']
    for pid, name, count in [
        (885, 'Cafe Curtain Panel', 1),
        (12133, 'Spice Spoon Print Kitchen Curtain Pair', 2),
        (12132, 'Colorful Spice Print Kitchen Curtain Pair', 2),
        (12070, 'Retro Dots Kitchen Curtain Pair', 2),
    ]:
        panel = part('panels', 'Curtain panel', 'cafe_panel', count)
        panel['bindings'] = {'wands_length':'length'}
        add([pid], name=name, axis=axis('wands_length','Panel drop',lengths,['24 in','30 in','36 in','45 in']),
            design={'components':[panel]}, sale_unit=f'{count} curtain panel' + ('s' if count>1 else ''),
            copy='A short-drop curtain design for a kitchen window. Each listed measurement applies to one panel, not the full window.',
            rationale='Replace full-length drape options with explicitly synthetic kitchen-panel drops.')
    tiers = part('tiers','Tier panel','cafe_panel',2)
    tiers['bindings'] = {'wands_length':'length'}
    add([933], name='Barnyard Valance and Tier Curtain Set',
        axis=axis('wands_length','Tier-panel drop',lengths,['24 in','30 in','36 in','45 in']),
        design={'components':[part('valance','Valance','valance'),tiers]}, sale_unit='1 valance and 2 tier panels',
        copy='A coordinated three-piece window set with one valance and a pair of lower tier panels. The selected drop changes the tiers only.',
        rationale='Keep the source-named valance/tier assortment while correcting the tier-length choices.')
    for pid,name in [(14741,'Three-Drawer Solid Wood Nightstand'),(39871,'Lafever One-Drawer Nightstand')]:
        add([pid], name=name, axis=axis('wands_length','Overall width',['30 in','36 in','48 in'],['18 in','22 in','26 in']),
            design={'profile':'nightstand','bindings':{'wands_length':'width'}}, sale_unit='1 nightstand',
            copy='A bedside storage cabinet offered in three compact widths. Select the width and finish independently.',
            rationale='Use nightstand-scale widths; preserve SKU, price, stock and finish choices.')
    for pid, name, sizes in [
        (10980,'Body Pillowcase',['20 in x 48 in','20 in x 54 in','20 in x 60 in']),
        (39141,'Estevao Body Pillowcase',['20 in x 48 in','20 in x 54 in','20 in x 60 in']),
        (19888,'Hance Pillowcase',['20 in x 26 in','20 in x 30 in','20 in x 36 in']),
    ]:
        add([pid], name=name, axis=axis('wands_size','Pillowcase dimensions',['Twin','Full','Queen'],sizes),
            design={'profile':'pillowcase','rectangle_axis':'wands_size'}, sale_unit='1 pillowcase; pillow insert excluded',
            copy='A single pillowcase in the selected color and laid-flat dimensions. Pillow inserts, sheets and other bedding are not included.',
            rationale='Use actual synthetic pillowcase dimensions, not mattress labels. The body-pillow title/description takes precedence for the fictional design; conflicting source labels remain in the evidence.')
    add([34585], name='Vinyl Shower Curtain Liner',
        axis=axis('wands_size','Liner width x drop',['18 in x 30 in','24 in x 36 in','30 in x 48 in'],
                  ['70 in x 72 in','72 in x 72 in','72 in x 84 in']),
        design={'profile':'shower_curtain','rectangle_axis':'wands_size'}, sale_unit='1 shower liner; hooks and rod excluded',
        copy='A single vinyl liner with separately defined width and drop. Select the color and liner dimensions; bath mats are not included.',
        rationale='The source identifies a liner, not a bath mat. Replace mat-size options with synthetic liner sizes.')
    for pid,name in [(11383,'Dunleavy Bed with Stowed Trundle'),(26322,'Pompano Platform Bed with Stowed Trundle')]:
        add([pid], name=name,
            axis=axis('wands_size','Main bed size',['Toddler','Twin','Full'],['Twin','Twin XL','Full']),
            design={'profile':'trundle_frame','bed_axis':'wands_size'}, sale_unit='1 main bed frame with 1 stowed trundle; mattresses excluded',
            copy='A main bed frame with a pull-out trundle stored underneath. The size option describes the main bed; diagrams show the closed exterior only.',
            rationale='Remove the inappropriate toddler trundle design without SKU churn. New sizes are synthetic concepts, not a mattress-fit or clearance specification.')
    add([17111], name='Moorcroft Three-Level Bunk Frame',
        axis=axis('wands_size','Top / middle / bottom bed sizes',['Toddler','Twin','Full','Queen'],
                  ['Twin over Twin over Twin','Twin over Twin over Full','Twin over Full over Full','Full over Full over Full']),
        design={'profile':'bunk_frame','bed_axis':'wands_size','dimensions':{'height':225}},
        sale_unit='1 three-level bed-frame assembly; mattresses excluded',
        copy='A three-level frame concept with the top, middle and bottom sleeping positions named explicitly. Dimensions describe the overall frame exterior only.',
        rationale='Make all three levels explicit. No structural, load, guardrail, mattress-fit or safety assertion is created.')
    add([9621], name='Paw Toddler Bed Frame', drop_axes=['wands_size'],
        design={'profile':'bed','fixed_bed_size':'Toddler'}, sale_unit='1 toddler bed frame; mattress excluded',
        copy='A toddler-sized bed-frame design with a choice of color. There are no twin or full-size versions in this candidate family.',
        rationale='Consolidate redundant adult-size children into one toddler design per color; retirement remains a separate proposal.')

    # Crib sets retain their actual named component roles. Dimensions and variant
    # consolidation are fictional proposals, not infant-sleep suitability claims.
    crib_sets = {
        11451: ('Bow Print Four-Piece Nursery Decor Set', [part('comforter','Comforter','nursery_cover'),part('sheet','Fitted crib sheet','crib_sheet'),part('skirt','Crib skirt','crib_skirt'),part('wall-decor','Wall decoration','wall_decor')]),
        34811: ('Sleepy Sheep Four-Piece Nursery Decor Set', [part('quilt','Nursery quilt','nursery_cover'),part('sheet','Fitted crib sheet','crib_sheet'),part('skirt','Crib skirt','crib_skirt'),part('plush','Decorative plush','plush')]),
        38422: ('Thorgarth Twelve-Piece Nursery Decor Set', [part('quilt','Crib quilt','nursery_cover'),part('valances','Valance','valance',2),part('skirt','Crib skirt','crib_skirt'),part('sheet','Fitted crib sheet','crib_sheet'),part('diaper-stacker','Diaper stacker','fabric_bag'),part('toy-bag','Toy bag','fabric_bag'),part('pillows','Decorative pillow','pillow',2),part('wall-hangings','Wall hanging','wall_decor',3)]),
        17166: ('Carrollton Six-Piece Nursery Decor Set', [part('cover','Duvet cover','nursery_cover'),part('sheet','Fitted crib sheet','crib_sheet'),part('pillowcases','Pillowcase','nursery_pillowcase',2),part('blanket','Blanket','nursery_cover'),part('booties','Pair of decorative booties','booties_pair')]),
    }
    for pid,(name,components) in crib_sets.items():
        add([pid], name=name, drop_axes=['wands_size'], design={'components':components},
            sale_unit=f'{sum(c["quantity"] for c in components)} listed pieces'+('; booties count as one pair' if pid==17166 else ''),
            copy='A coordinated nursery-decor assortment with each included item listed separately. No adult-bed size variants are offered. Illustrations must show the textile assortment laid out, not in use with an infant.',
            rationale='Preserve the source-named assortment and remove unrelated mattress sizes. No infant-sleep, age, safety or fit claim is made.')

    for pid,name in [(2448,'Louise Bistro Set'),(33594,'Outdoor Bistro Table and Chair Set'),(39965,'Suzy Bistro Set with Cushions')]:
        variants={}
        for count in range(2,6):
            variants[f'{count} Pieces']={'components':[part('table','Bistro table','patio_table',width=65+10*(count-2),depth=65+10*(count-2)),part('chairs','Bistro chair','dining_chair',count-1)]}
        add([pid], name=name, design_variants=variants, design_axis='wands_piece_count', sale_unit='1 table plus the listed number of chairs',
            copy='An outdoor bistro assortment with one table and the listed chairs. The piece count refers to furniture, not cushion inserts or packaging.',
            rationale='Define every existing piece-count option explicitly; expansions beyond the source assortment are synthetic.')
    def seating(pid,name,counts,components):
        add([pid],name=name,axis=axis('wands_piece_count','Furniture pieces',['2 Pieces','3 Pieces','4 Pieces'],[str(n)+' Pieces' for n in counts]),
            design_axis='wands_piece_count', design_variants={str(n)+' Pieces':{'components':components(n)} for n in counts},
            sale_unit='the listed furniture assortment; loose cushions are not counted as furniture pieces',
            copy='A coordinated outdoor seating assortment. The selected furniture count determines the exact seating modules and table listed below; dimensions belong to the individual components.',
            rationale='Replace generic counts with explicit coherent assortments. Added/removed modules are synthetic lab variants, not recovered manufacturer configurations.')
    seating(20492,'Claunch Modular Outdoor Seating Set',[4,5,6],lambda n:[part('loveseats','Loveseat','patio_sofa',2,width=140,seat_width=110),part('corner','Corner seating module','patio_chair'),part('table','Coffee table','coffee_table')]+([part('armless','Armless seating module','patio_chair',n-4)] if n>4 else []))
    seating(6005,'Pierceton Modular Rattan Seating Set',[6,7,8],lambda n:[part('armless','Armless seating module','patio_chair',n-4),part('corner','Corner seating module','patio_chair'),part('armchairs','Armchair','patio_chair',2),part('table','Coffee table','coffee_table')])
    seating(32748,'Rochford Modular Outdoor Seating Set',[5,6,7],lambda n:[part('corners','Corner sofa module','patio_chair',2),part('armless','Armless sofa module','patio_chair',n-3),part('table','Storage coffee table','coffee_table')])
    seating(15278,'Latshaw Outdoor Sofa Seating Set',[2,3,4],lambda n:[part('loveseat','Loveseat','patio_sofa',width=140,seat_width=110),part('table','Coffee table','coffee_table')]+([part('chairs','Lounge chair','patio_chair',n-2)] if n>2 else []))
    add([30335],name='Merlyn Outdoor Sofa, Chair and Ottoman Set',
        axis=axis('wands_piece_count','Furniture pieces',['2 Pieces','3 Pieces','4 Pieces','5 Pieces'],['4 Pieces','5 Pieces','6 Pieces','7 Pieces']),
        design_axis='wands_piece_count',design_variants={str(n)+' Pieces':{'components':[part('sofa','Sofa','patio_sofa'),part('chairs','Lounge chair','patio_chair',n-3),part('ottoman','Ottoman','ottoman'),part('table','Coffee table','coffee_table'),{**part('pillows','Decorative pillow','pillow',2),'counts_as_furniture':False}]} for n in range(4,8)},
        sale_unit='listed furniture pieces; 2 decorative pillows are included separately',
        copy='A patio group built around a sofa, an ottoman and a coffee table, with the selected number of lounge chairs. Two decorative pillows are accessories, not furniture pieces.',
        rationale='Source names one sofa, chair, ottoman and table plus two pillows. Normalize furniture count to four before defining synthetic larger assortments.')
    add([35956],name='Vada Folding Picnic Table',
        axis=axis('wands_piece_count','Table length',['2 Pieces','3 Pieces','4 Pieces','5 Pieces'],['24 in','30 in','36 in','42 in'],target='wands_length'),
        design={'profile':'patio_table','dimensions':{'width':60,'height':58},'bindings':{'wands_length':'depth'}},
        sale_unit='1 folding table; chairs and benches excluded',
        copy='A portable picnic table offered in four synthetic table lengths. Each option is one table, not a dining set; chairs and benches are not included.',
        rationale='Source description and features identify one folding table with no chairs; replace a misclassified piece-count axis.')
    add([35295],name='Skiatook Three-Piece Table and Floor Lamp Set',
        design={'components':[part('floor-lamp','Floor lamp','floor_lamp'),part('table-lamps','Table lamp','table_lamp',2)]},
        sale_unit='1 floor lamp and 2 table lamps',
        copy='A three-lamp assortment with one floor lamp and a matching pair of table lamps in the selected finish.',
        rationale='Explicitly synthetic 1+2 split of the source-named mixed three-lamp set; the source does not verify that split.')
    add([22468],name='Loewen Triangular Three-Shelf Wall Unit',
        design={'profile':'wall_storage','dimensions':{'width':71,'depth':15.24,'height':67}},
        sale_unit='1 assembled wall unit with 3 integral shelves',
        copy='One triangular wall unit with three integral shelves. It is not a pack of three separate shelving units; mounting hardware and load ratings are not specified here.',
        rationale='The full source description identifies one triangular piece with three shelves, resolving the misleading three-piece title without inventing a set.')
    add([8286],name='Pineapple Upholstery Fabric Cut',
        design={'profile':'fabric_cut','dimensions':{'width':137.16,'length':91.44}},
        sale_unit='1 precut panel, 54 in wide x 36 in long; multiple quantities are separate cuts',
        copy='A patterned fabric offered as individual precut panels for upholstery-project mockups. Ordering two gives two separate cuts, not a continuous two-yard length.',
        rationale='Authored synthetic sale unit, not an inference that unitless source numbers were inches.')

    for pid,reason in {
        3897:'Nine named baking pieces plus a lid are suggested, but the lid association and cake-pan allocation need an explicit design decision before a complete assortment can be claimed.',
        17842:'The 45-piece service-for-eight title and named serving pieces conflict with explicit no-serving-piece flags. Do not silently choose the convenient source fields.',
        22642:'Description identifies a burger press and fry cutter, while the source says five included pieces without defining the five roles.',
        34345:'Pillowcase title/description conflicts with the fitted-sheet product-type field. Product identity needs an explicit resolution.',
        42749:'Five-piece title conflicts with six pieces and five chairs plus one table. Resolve the source assortment before adapting its family.',
    }.items():
        add([pid],hold_reason=reason)
    return result
