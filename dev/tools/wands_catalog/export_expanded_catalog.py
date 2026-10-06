#!/usr/bin/env python3
"""Export only complete, reviewed expanded data and images. Never modifies a store."""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
import json
import os
from pathlib import Path
import shutil

from build_expanded_catalog import csv_rows, write_csv, variations, digest
from bulk_expansion_images import (atomic_json, connect, current_job_accepted,
                                   descriptor, require_bulk_gate, reference_held, reference_design)
from prepare_catalog import sha256
import component_review


def accepted_retained(db, row, identity):
    """Return current accepted bytes for one frozen retained-media brief."""
    path=Path(row['path'])
    if sha256(path)!=row['image_sha256']:raise ValueError('Retained original changed')
    if row['review'] and not reference_held(db,row['image_sha256']) and component_review.accepted(json.loads(row['review']),json.loads(row['design'])):
        review=json.loads(row['review'])
        if (review['decision']=='accepted' and review['review_identity']==identity
                and review['image_sha256']==row['image_sha256'] and review['design_sha256']==row['design_sha256']):
            return path
    for repair in db.execute('SELECT * FROM reference_repairs WHERE original_sha256=? AND design_sha256=? ORDER BY attempt DESC',
                             (row['image_sha256'],row['design_sha256'])):
        if not repair['review'] or reference_held(db,repair['image_sha256']) or not component_review.accepted(json.loads(repair['review']),json.loads(row['design'])):continue
        review=json.loads(repair['review']);path=Path(repair['image_path'])
        if (review['decision']=='accepted' and review['review_identity']==identity
                and review['design_sha256']==row['design_sha256']
                and sha256(path)==repair['image_sha256']==review['image_sha256']):return path
    return None


def resolve_retained(db, baseline, identity, excluded=frozenset()):
    """Resolve every retained SKU against its exact brief, including shared files."""
    assignments=json.loads((baseline/'data/media-lineage.json').read_text())['assignments']
    inventory=json.loads((baseline/'data/media-inventory.json').read_text())
    products={r['sku']:r for name in ('1-simple.csv','2-configurable.csv','3-bundle.csv')
              for r in csv_rows(baseline/'data'/name)}
    references={(r['image_sha256'],r['design_sha256']):r
                for r in db.execute('SELECT * FROM references_to_review')}
    resolved={};cache={};missing=set();unresolved=set();by_file=defaultdict(list)
    for sku,assignment in assignments.items():
        if sku in excluded:continue
        name=assignment['file'];key=(inventory[name]['sha256'],digest(reference_design(products[sku])))
        if key not in cache:
            row=references.get(key)
            if row is None:missing.add(key)
            cache[key]=accepted_retained(db,row,identity) if row is not None else None
        path=cache[key];by_file[name].append(path)
        if path is None:unresolved.add(key)
        else:resolved[sku]=path
    covered=sum(all(paths) for paths in by_file.values())
    if {a['file'] for a in assignments.values()}!=set(inventory):raise ValueError('Retained media inventory has missing assignments')
    return resolved,{'unresolved_retained_briefs':len(unresolved),
        'unregistered_retained_briefs':len(missing),'retained_briefs_expected':len(cache),
        'retained_assignments_resolved':len(resolved),'retained_assignments_expected':len(assignments)-len(set(assignments)&set(excluded)),
        'quarantined_retained_assignments':len(set(assignments)&set(excluded)),
        'retained_images_resolved':covered,'retained_images_expected':len(by_file),
        'retained_images_total':len(inventory),
        'retained_conflicts':[],
        'retained_variant_replacements':sum(len({str(p) for p in paths if p})>1 for paths in by_file.values())}


def inspect(run):
    desc=descriptor(run);db=connect(run);baseline=Path(desc['baseline']);candidate=Path(desc['candidate'])
    manifest=json.loads((candidate/'manifest.json').read_text())
    for name,pin in manifest['outputs'].items():
        if sha256(candidate/name)!=pin:raise ValueError('Candidate data changed')
    report={'candidate_sha256':desc['candidate_sha256'],'accepted_new_images':0,
            'unresolved_new_images':Counter(),'unresolved_retained_briefs':0,'retained_conflicts':[],
            'baseline_audit_registered':(run/'baseline-audit.json').is_file(),'pilot_accepted':False}
    from authorized_completion import policy
    completion=policy(db,desc)
    if completion:
        report['completion_policy']=completion
        report['completion_policy_sha256']=digest(completion)
    try:require_bulk_gate(run,db,desc);report['pilot_accepted']=True
    except ValueError:pass
    from catalog_quarantine import policy as quarantine_policy,skus,all_quarantined
    quarantine=quarantine_policy(run,desc);excluded=skus(quarantine)
    if quarantine:
        report['catalog_quarantine']=quarantine
        report['catalog_quarantine_sha256']=digest(quarantine)
    new=[];quarantined_jobs=0
    for row in db.execute('SELECT * FROM jobs ORDER BY ordinal'):
        if all_quarantined(json.loads(row['request']),excluded):
            quarantined_jobs+=1;continue
        if current_job_accepted(db,row,desc['review_identity']):
            new.append((json.loads(row['request']),Path(row['image_path'])))
            report['accepted_new_images']+=1
        else:report['unresolved_new_images'][row['state']]+=1
    retained,coverage=resolve_retained(db,baseline,desc['review_identity'],excluded)
    report.update(coverage)
    from category_image_corrections import unresolved
    report['unresolved_category_images']=unresolved(db,desc['vision_model'],desc['review_identity'],excluded_skus=excluded)
    report.update(quarantined_new_images=quarantined_jobs,new_images_required=48844-quarantined_jobs)
    report['ready']=(report['pilot_accepted'] and report['baseline_audit_registered']
                     and len(new)==report['new_images_required'] and not report['unresolved_new_images']
                     and not report['unresolved_retained_briefs'] and not report['retained_conflicts']
                     and not report['unresolved_category_images']
                     and report['retained_assignments_resolved']==report['retained_assignments_expected']
                     and report['retained_images_resolved']==report['retained_images_expected'])
    db.close()
    return desc,report,new,retained


def export(run,output):
    desc,report,new,retained=inspect(run)
    atomic_json(run/'export-readiness.json',report)
    if not report['ready']:raise ValueError('Incomplete image acceptance; see export-readiness.json. No package exported.')
    if output.exists():raise ValueError('Export destination must not exist')
    candidate=Path(desc['candidate']);baseline=Path(desc['baseline'])
    output.mkdir(parents=True);(output/'data').mkdir();media=output/'media/wands-expanded';media.mkdir(parents=True)
    # New namespace prevents replacing media already used by either installation.
    def copy_image(path):
        filename=sha256(path)+'.jpg';destination=media/filename
        if not destination.exists():shutil.copyfile(path,destination)
        if sha256(destination)!=filename[:-4]:raise ValueError('Image copy verification failed')
        return '/wands-expanded/'+filename
    rows={r['sku']:r for name in ('1-simple.csv','2-configurable.csv','3-bundle.csv') for r in csv_rows(candidate/'data'/name)}
    from feedback_reprocessing import apply_catalog_patches,has_table
    revisions=connect(run)
    try:
        apply_catalog_patches(revisions,rows)
        correction_pins=([r[0] for r in revisions.execute('SELECT DISTINCT manifest_sha256 FROM feedback_reprocessing WHERE active=1')]
                         if has_table(revisions) else [])
    finally:revisions.close()
    from catalog_quarantine import apply_fields,skus
    quarantine=report.get('catalog_quarantine');quarantined=skus(quarantine)
    apply_fields(rows,quarantine)
    from native_metadata import normalize
    normalizations=normalize(rows)
    if quarantine:atomic_json(output/'catalog-quarantine.json',quarantine)
    assignments=json.loads((baseline/'data/media-lineage.json').read_text())['assignments']
    media_rows={}
    def assign(sku,path):
        from native_metadata import media_label
        label=media_label(rows[sku]['name'])
        media_rows[sku]={'sku':sku,'store_view_code':'','url_key':rows[sku]['url_key'],
                         **{role:path for role in ('base_image','small_image','thumbnail')},
                         **{role+'_label':label for role in ('base_image','small_image','thumbnail')}}
    for sku in assignments:
        if sku not in quarantined:assign(sku,copy_image(retained[sku]))
    for job,path in new:
        name=copy_image(path)
        for sku in job['skus']:
            if sku in quarantined:continue
            if sku in media_rows:raise ValueError('Duplicate media assignment')
            assign(sku,name)
    excluded=sorted(set(rows)-set(media_rows))
    original_excluded=set(excluded)-quarantined
    if len(original_excluded)!=20 or not quarantined.issubset(excluded) or any((sku.startswith('WANDS-SYN-') and sku not in quarantined) or rows[sku]['product_online']!='2'
                               or rows[sku]['visibility']!='Not Visible Individually' for sku in excluded):
        raise ValueError('Only the twenty retained disabled imageless records may lack media')
    for name in ('1-simple.csv','2-configurable.csv','3-bundle.csv'):
        if correction_pins or quarantine or normalizations:write_csv(output/'data'/name,[rows[r['sku']] for r in csv_rows(candidate/'data'/name)])
        else:shutil.copyfile(candidate/'data'/name,output/'data'/name)
    write_csv(output/'data/4-media.csv',[media_rows[sku] for sku in sorted(media_rows)])
    shutil.copyfile(baseline/'data/5-merchandising.csv',output/'data/5-merchandising.csv')
    for name in ('new-products.csv','existing-parent-updates.csv','categories.jsonl','counts.json'):
        if (correction_pins or quarantine or normalizations) and name.endswith('.csv'):
            write_csv(output/name,[{key:rows[row['sku']].get(key,value) for key,value in row.items()}
                                   for row in csv_rows(candidate/name)])
        else:shutil.copyfile(candidate/name,output/name)
    counts=json.loads((candidate/'counts.json').read_text())
    counts.update(image_files=len(list(media.iterdir())),media_assignments=len(media_rows),media_roles=3*len(media_rows))
    counts['source_enabled_visible']=counts.get('enabled_visible')
    counts['enabled_visible']=sum(r['product_online']=='1' and r['visibility']!='Not Visible Individually' for r in rows.values())
    counts.update(disabled_products=sum(r['product_online']=='2' for r in rows.values()),
                  enabled_visible_products=sum(r['product_online']=='1' and r['visibility']!='Not Visible Individually' for r in rows.values()),
                  quarantined_products=len(quarantined))
    atomic_json(output/'data/counts.json',counts)
    atomic_json(output/'counts.json',counts)
    options=defaultdict(set)
    for row in rows.values():
        if row['product_type']=='configurable':
            for group in variations(row):
                for key,value in group.items():
                    if key!='sku':options[key].add(value)
    atomic_json(output/'data/attribute-options.json',{key:sorted(values) for key,values in sorted(options.items())})
    atomic_json(output/'data/media-inventory.json',{
        str(path.relative_to(output)):{'sha256':sha256(path),'bytes':path.stat().st_size,
                                      'acceptance':'measurement-free OCR and vision review',
                                      'review_identity':desc['review_identity']}
        for path in sorted(media.iterdir())})
    atomic_json(output/'data/media-lineage.json',{'excluded_disabled_skus':excluded,'assignments':{
        sku:{'file':'media'+row['base_image'],'sha256':Path(row['base_image']).stem}
        for sku,row in sorted(media_rows.items())}})
    atomic_json(output/'visual-acceptance.json',report)
    files={str(p.relative_to(output)):{'sha256':sha256(p),'bytes':p.stat().st_size}
           for p in sorted(output.rglob('*')) if p.is_file()}
    atomic_json(output/'manifest.json',{'schema':1,'profile':'expanded-measurement-free','products':107688,
                'source_candidate_sha256':desc['candidate_sha256'],'review_identity':desc['review_identity'],
                'source_run_sha256':sha256(run/'run.json'),
                'human_correction_manifests':sorted(correction_pins),
                'native_metadata_normalizations':normalizations,
                'completion_policy_sha256':report.get('completion_policy_sha256'),
                'catalog_quarantine_sha256':report.get('catalog_quarantine_sha256'),
                'component_review_identity':component_review.identity(desc['vision_model']),
                'media_assignments':len(media_rows),'excluded_disabled_skus':excluded,'files':files})
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path)
    a=p.parse_args();run=a.run.resolve()
    if a.output:report=export(run,a.output.resolve())
    else:
        _,report,_,_=inspect(run)
        atomic_json(run/'export-readiness.json',report)
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
