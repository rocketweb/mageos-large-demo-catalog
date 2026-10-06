"""Run-scoped completion permission and explicit advisory counter evidence."""
from functools import lru_cache
import copy
import json
import re
from build_expanded_catalog import digest
from image_policy import product_prompt, visual_text, NO_MEASUREMENTS

AUTHORIZATION='User requested finishing the project and removing gates as needed.'


@lru_cache(maxsize=4)
def checked_policy(text,pin):
    value=json.loads(text)
    if digest(value)!=pin or value.get('schema')!=1 or value.get('authorization')!=AUTHORIZATION:
        raise ValueError('Completion authorization changed')
    return value


def policy(db,desc=None):
    if db is None or not db.execute("SELECT 1 FROM sqlite_master WHERE name='completion_authorization'").fetchone():return None
    row=db.execute('SELECT policy,policy_sha256 FROM completion_authorization WHERE id=1').fetchone()
    if not row:return None
    value=checked_policy(row[0],row[1])
    if not value.get('active'):return None
    if desc and any(value.get(k)!=desc[k] for k in ('candidate_sha256','review_identity')):
        raise ValueError('Completion permission belongs to another candidate or reviewer')
    return value


def admitted(db,kind,key,intent,desc=None):
    if not policy(db,desc):return False
    row=db.execute('SELECT intent_sha256 FROM completion_targets WHERE kind=? AND target=?',(kind,key)).fetchone()
    if not row:return False
    if row[0]!=intent:raise ValueError('Authorized completion brief changed')
    return True


def reference_admitted(db,row,desc=None):
    return admitted(db,'reference',digest([row['image_sha256'],row['design_sha256']]),digest(json.loads(row['design'])),desc)


def review_window(db,scope,item):
    if not policy(db):return 3
    row=db.execute('SELECT failures FROM completion_review_baselines WHERE scope=? AND item=?',(scope,item)).fetchone()
    return row[0]+3 if row else 3


def render_subject(design):
    """Remove a conflicting old finish suffix from the render prompt only.

    The complete frozen subject still goes to QA. Structured variant fields
    identify the requested finish; size and construction words remain intact.
    """
    subject=visual_text(design.get('subject',''))
    cls=design.get('product_class',design.get('profile','')).lower()
    if 'slow cooker' in cls or 'mattress' in cls:
        # These literal prefixes have repeatedly become printed labels in
        # otherwise unbranded synthetic photos. Keep the canonical brief for
        # QA and catalog data; remove only the observed branding from rendering.
        subject=re.sub(r'^(?:All[- ]Clad(?:\s+Electrics)?|Hamilton Beach|Lucid(?:\s+Comfort Collection)?)\s+',
            '',subject,flags=re.I)
    if not design.get('color'):return subject
    finishes=('Beige','Black','Blue','Brown','Cream','Gray','Grey','Green','Ivory','Navy',
        'Natural','Red','Terracotta','White','Gold','Silver','Walnut','Oak','Espresso',
        'Brass','Chrome','Brushed Nickel','Matte Black','Bronze','Clear')
    names='|'.join(re.escape(v) for v in sorted(finishes,key=len,reverse=True))
    return re.sub(r'\s+-\s+(?:'+names+r')(?=,|$)', '',subject,flags=re.I)


def class_geometry(design):
    """Make the sale unit explicit before potentially ambiguous collection names."""
    cls=design.get('product_class',design.get('profile','')).lower()
    subject=design.get('subject','').lower()
    if 'slow cooker' in cls:
        return ('One complete countertop slow cooker with a deep enclosed pot body, two side carrying handles, '
            'a fitted lid with its own lifting handle, and plain unmarked controls on the front. '
            'Any control knob is unmarked and any existing display is blank and dark. All surfaces are free of labels and logos. ')
    if any(word in cls for word in ('washing machine','washer','dryer','refrigerator')):
        return ('Preserve the specified appliance body, doors, handles and control layout. Use plain unmarked controls, '
            'unmarked control knobs and blank dark display windows. Every panel and surface is free of labels and logos. ')
    if 'stackable chair' in cls and 'armless' in subject:
        return ('One armless stackable chair with a distinct seat and back upholstery in the stated fabric, '
            'supported by four narrow legs with open space beneath the seat. No armrests, enclosed side walls '
            'or solid box pedestal. The back and seat are connected by a slender coherent frame, with slightly '
            'flared legs that allow identical chairs to nest for stacking. Show just one complete chair. ')
    if cls=='outdoor conversation sets':
        pieces=re.search(r'\b([2-9]|1[0-2])\s*[- ]?\s*pieces?\b',subject)
        if pieces:
            return ('Arrange exactly '+pieces[1]+' separate complete furniture assemblies with clear gaps between them. '
                'A complete sofa, loveseat, chair or table counts as one furniture assembly. '
                'Cushions and decorative pillows never count as additional pieces. Show every complete assembly, '
                'with its own seat or tabletop and complete supporting structure. ')
    if 'bedding set' in cls:
        return ('The product is a complete fabric bedding set, with a bed-sized quilt or duvet cover and matching pillow covers. '
            'Any named scene, character or object appears as a decorative pattern printed on the fabric, never as a separate physical product. ')
    if 'wall art' in cls or 'wall décor' in cls:
        return ('The product is a complete decorative wall artwork. Any named scene or object belongs within the artwork, '
            'never as a separate functional product. Keep its composition free of writing. ')
    if 'wall plate' in cls:
        return 'The product is one flat electrical wall cover plate with the appropriate socket or switch openings and mounting holes. '
    if 'headboard' in cls:
        return 'The product is one complete broad bed headboard with connected supports, never a whole bed or a separate framed picture. '
    if 'curtain' in cls or 'drape' in cls:
        return ('The product is one continuous hanging curtain panel unless the brief explicitly specifies multiple panels. '
            'Any plain rod only supports the panel for display and is not an extra sale item. ')
    if 'weather instrument' in cls or 'clock' in cls:
        return ('Show the complete recognizable instrument with an entirely plain unmarked face. '
            'No printed digits, letters, tick marks, scales, degree marks or graduation. ')
    return ''


def lighting_geometry(subject):
    text=subject.lower();parts=[]
    for feature,instruction in (
        ('antler','Distinct branching faux antlers with pointed tines form the connected decorative framework.'),
        ('crystal','Many small clear faceted glass crystal pendants hang from the framework as decorative accents, never extra light sockets.'),
        ('candle','Each specified socket uses an upright plain ivory candle sleeve and one small flame-shaped bulb.'),
        ('sputnik','Straight metal spokes radiate from a central hub into a clear starburst. Unlit decorative spokes are not extra light sockets.'),
        ('linear','The connected fixture is broad and horizontally elongated, never a compact teardrop cage.'),
        ('tiered','Two clearly separated decorative tiers sit at different heights, with only the specified total number of light sockets.'),
        ('drum','A broad cylindrical drum shade surrounds the specified light sockets. Photograph from slightly below so the open underside reveals every bulb.'),
        ('schoolhouse','A complete rounded schoolhouse glass shade encloses the bulb and connects securely to the metal fitting.')):
        if feature in text:parts.append(instruction)
    return ' '.join(parts)+' ' if parts else ''


def construction_prompt(design,review,attempt):
    from completion_recovery import recipe
    from repair_expansion_references import corrective_geometry
    from component_review import required_counts
    from completion_sale_units import geometry as sale_geometry
    sale_unit=sale_geometry(design)
    render_design={**design,'subject':render_subject(design)}
    typed=recipe(render_design)
    body=typed['prompt'].replace(NO_MEASUREMENTS,'') if typed else (
        'New studio product photograph. '+class_geometry(design)+'Intended sale unit: '+render_subject(design)+'. '
        'Product class: '+design.get('product_class',design.get('profile',''))+'. '
        'Visible construction: '+design.get('construction','')+'. '
        'Material: '+design.get('material','')+'. Finish: '+design.get('color','')+'. ')
    if sale_unit:body='New studio product photograph. '+sale_unit+' '+body
    body+=' '+corrective_geometry(design.get('subject',''))+' '
    if typed:body+='Intended product: '+render_subject(design)+'. Visible details: '+design.get('construction','')+'. '
    cls=design.get('product_class',design.get('profile','')).lower()
    if any(word in cls for word in ('chandelier','lighting','sconce','pendant','lamp')):
        body+=lighting_geometry(design.get('subject',''))
    counts=required_counts(design);drawers=counts.get('drawer_fronts');doors=counts.get('cupboard_doors')
    if drawers:
        layouts={1:'one full-width drawer',2:'two stacked full-width drawers',3:'three stacked full-width drawers',
            4:'four stacked full-width drawers',5:'five stacked full-width drawers',6:'two columns of three drawers',
            7:'three small upper drawers above two rows of two drawers',8:'two columns of four drawers',9:'three rows of three drawers'}
        if drawers==2 and doors==2:layout='two half-width upper drawers above two lower cupboard doors'
        elif doors:layout=str(drawers)+' separate drawer fronts alongside '+str(doors)+' separate cupboard door panels'
        else:layout=layouts.get(drawers,str(drawers)+' separate drawer fronts')
        body+='Drawer layout: '+layout+'. Each front has a complete rectangular seam and one centered pull. '
    subject=design.get('subject','').lower()
    if design.get('profile')=='pullout-hamper' and 'tilt-out' in design.get('construction',''):
        body+='Each tilt-out front is hinged along its bottom edge, with a removable laundry bin attached behind it. Show both bin fronts tipped forward while their lower pivots remain connected to the cabinet. '
    if design.get('profile')=='rail-planter' or 'railing planter' in subject:
        body+='Show two hooked mounting brackets attached at the upper rear of the trough, extending clearly behind it to hang securely from a railing. '
    if design.get('profile')=='laundry-sorter' and 'two' in design.get('construction','').lower():
        body+='A single coherent frame holds exactly two fabric bags side by side in one horizontal row. Show both empty bag openings, with no second row, extra loose bag, upper bin or added container. '
    if design.get('profile')=='cooking-spoon':
        body+='Exactly one utensil: one small concave spoon head permanently joined to one elongated handle. The spoon head is part of the utensil, with no separate bowl, cup, plate or other tableware. '
    if 'shaded' in subject:
        body+='Every light socket has its own individual lampshade, with each complete shade-and-light assembly clearly separated and visible. '
    if 'bunk' in subject:
        levels=subject.count(' over ')+1 if ' over ' in subject else 2
        body+=str(levels)+' complete sleeping platforms stacked vertically, connected by sturdy posts with a ladder to every upper bed. '
    for name,instruction in (
        ('trundle','A separate low pullout sleeping platform is clearly visible partly extended beneath the main bed.'),
        ('hutch','A complete attached tall storage hutch is visible above the main desk or cabinet.'),
        ('loveseat','A broad two-person upholstered sofa with two separate seat cushions between two arms, never a single armchair.')):
        if name in subject:body+=instruction+' '
    if 'upholstered' in subject and design.get('material') in {'Metal','Solid Wood','Engineered Wood'}:
        body+='The stated structural material applies to the frame and supports; the upholstered panel or seat is covered in padded fabric. '
    defects=(review or {}).get('vision',{}).get('issues',[])
    # Some failed reviews contain paragraphs of model self-correction. They are
    # diagnostics, not additional intended product features or render tokens.
    if defects:body+=render_defect_notes(defects,positive_sale_unit=bool(sale_unit))
    body+=('Show the complete product and every specified component in a clear '+
        ('almost frontal view' if attempt%2 else 'gentle three-quarter view')+
        '. Realistic connected supports, natural photographic detail, plain warm white background. '
        'Never copy writing, brand names or annotation from earlier candidates. No extra products or props.')
    return product_prompt(body)


def render_defect_notes(defects,positive_sale_unit=False):
    """Do not teach an image model the literal writing it must erase."""
    annotation=re.compile(r'\b(?:text|words?|lettering|letters?|numerals?|logo|logos|brand|branding|label|labels|watermark|watermarks|annotation|annotations|measurement|measurements)\b',re.I)
    structural=[];remove_writing=False
    for defect in defects:
        if annotation.search(str(defect)):remove_writing=True
        else:
            if positive_sale_unit:
                from completion_sale_units import wrong_object_diagnostic
                if wrong_object_diagnostic(str(defect)):continue
            structural.append(str(defect))
    body=''
    if remove_writing:body+='Every product surface must be entirely plain and unmarked. Remove all printed or engraved markings, labels and logos. '
    if structural:body+='Correct the previous candidate defects: '+visual_text('; '.join(structural[:3])[:300])+'. '
    return body


def variant_prompt(job):
    from bulk_expansion_images import source_recolor_prompt
    design=job['design'];kind=design.get('product_class',design.get('profile','')).lower()
    if job.get('profile')=='monitor-riser':
        from category_image_corrections import EXAMPLE
        body=('Change only this separate furniture riser finish to '+visual_text(design['color'])+'. '
            'Preserve its exact low broad horizontal load surface, short supports, all storage openings, '
            'accessible cubbies or shallow drawer, construction and viewpoint. ')
        if job.get('job_id')==EXAMPLE:
            body+='Retain the simple black monitor, entirely unmarked and black including screen, bezel, neck and foot. '
        else:
            body+=('Show the empty horizontal top and only the separate furniture platform. '
                'Remove any optional display electronics from the top without changing any furniture geometry. ')
        return product_prompt(body+'Keep the complete furniture in frame on the same plain background.')
    if 'rug' in kind or kind in {'kitchen mats','door mats','doormats'}:
        color=visual_text(job['reference'].get('value') or design['color'])
        return product_prompt('Change only the base or background field of this same fabric rug or mat to '+color+'. '
            'Keep every decorative motif, border, stripe, constellation, cloud and star that is actually visible in the source contrasting and clearly visible. '
            'Only motifs already present in the source are preserved; add no new symbols or decoration. '
            'Retain the source accent colors, exact pattern geometry, woven texture, pile, edge binding, silhouette and viewpoint. '
            'A white ground must retain its contrasting pattern; a black ground must retain its contrasting pattern. '
            'Preserve the lighting and background. Show the same complete recognizable textile product.')
    return source_recolor_prompt(job)


def job_plan(run,db,row,desc):
    if not policy(db,desc):return False,None
    job=json.loads(row['request'])
    if not admitted(db,'job',row['job_id'],digest(job),desc):return False,None
    if row['state'] not in {'pending','rejected','review_required','review_error','interrupted'}:return True,None
    from bulk_expansion_images import accepted_reference,source_recolor_prompt
    from human_keep_acceptance import is_kept
    if is_kept(run,row):return True,None
    reference=accepted_reference(db,job,desc['review_identity'])
    if reference is False:return True,None
    review=json.loads(row['review']) if row['review'] else {}
    if job.get('profile') in {'monitor-riser','shoe-bench'}:
        from category_image_corrections import prompt as category_prompt
        prompt=(variant_prompt(job) if reference and job.get('profile')=='monitor-riser' else category_prompt(job))
    else:prompt=variant_prompt(job) if job.get('reference') else construction_prompt(job['design'],review,row['attempts']+1)
    image_pin=dict(row).get('image_sha256')
    if image_pin:
        manual=db.execute("SELECT observations FROM manual_reviews WHERE job_id=? AND image_sha256=? AND decision='rejected'",(row['job_id'],image_pin)).fetchone()
        if manual:prompt=product_prompt(prompt.replace(NO_MEASUREMENTS,'')+' '+render_defect_notes([manual[0][:300]]))
    return True,{'prompt':prompt,'reference':reference,'attempt':row['attempts']+1,
        'seed':(job['seed']+row['attempts']*104729)%(2**32)}


def reference_strategy(db,row,attempts):
    if not reference_admitted(db,row):return None
    evidence=json.loads((attempts[-1]['review'] if attempts else row['review']) or '{}')
    return 'generate',construction_prompt(json.loads(row['design']),evidence,len(attempts)+1)


def full_product_pass(review):
    if review.get('direct_visual_failure') or review.get('direct_geometry_failure'):
        return False
    v=review.get('vision') or {}
    return bool(v.get('acceptable') is True and v.get('verdict')=='pass' and not v.get('issues')
        and all(v.get(k) is False for k in ('visible_text','visible_measurements','geometry_defects'))
        and all(v.get(k) is True for k in ('product_matches','piece_count_matches'))
        and review.get('ocr',{}).get('status')=='ok' and not review.get('ocr_flags'))


def advisory_valid(review,design):
    proof=review.get('completion_gate_policy') or {}
    p=proof.get('policy') or {}
    return bool(review.get('decision')=='accepted' and p.get('authorization')==AUTHORIZATION
        and p.get('advisory_component_counts') is True and digest(p)==proof.get('policy_sha256')
        and proof.get('design_sha256')==review.get('design_sha256')==digest(design)
        and proof.get('image_sha256')==review.get('image_sha256')
        and p.get('review_identity')==review.get('review_identity') and full_product_pass(review))


def relieve_review(db,review,design):
    p=policy(db)
    if not p or p.get('advisory_component_counts') is not True or review.get('completion_gate_policy'):return review
    if review.get('review_identity')!=p['review_identity'] or review.get('design_sha256')!=digest(design) or not full_product_pass(review):return review
    from lighting_review import accepted as light_accepted,required_count as required_lights
    from component_review import required_table_count,table_identity
    import component_review
    if review.get('decision')=='accepted' and component_review.accepted(review,design):return review
    if not light_accepted(review,design):return review
    if required_lights(design) is not None and not review.get('lighting_review'):return review
    expected=required_table_count(design);table=review.get('table_component_review') or {}
    if expected is not None and not (table.get('expected')==expected and table.get('complete_tables')==expected
        and table.get('confidence',0)>=.95 and table.get('identity')==table_identity(review.get('model'))):return review
    result=copy.deepcopy(review)
    result['completion_gate_policy']={'policy':p,'policy_sha256':digest(p),'image_sha256':review['image_sha256'],
        'design_sha256':review['design_sha256'],'original_decision':review['decision'],
        'change':'Secondary door/drawer/shelf counting is advisory; complete product QA and all other checks remain required.'}
    result['decision']='accepted'
    return result
