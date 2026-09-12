#!/usr/bin/env python3
"""Stage exactly five reviewed JPEGs for a future disposable native-import rehearsal."""
import argparse
import csv
import json
import logging
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from build_nursery_assortment import pin_packet
from build_realism_review import write_json
from prepare_catalog import sha256
from verify_catalog_repairs import check

TARGETS={'WANDS-000056','WANDS-003897','WANDS-017842','WANDS-030335-3-PIECES-5B0E','WANDS-035295-BRONZE-D916'}
FIELDS={'sku','store_view_code','base_image','base_image_label','small_image','small_image_label','thumbnail','thumbnail_label'}


def validate_fields(assignment):
    fields=assignment['fields'];filename=assignment['image']['file']
    check(set(fields)==FIELDS,'Non-media CSV column or missing field')
    check(fields['sku']==assignment['target_sku'] and fields['sku'] in TARGETS,'Wrong exact media target')
    check(fields['store_view_code']=='','Unexpected store override')
    check(PurePosixPath(filename).name==filename and filename.endswith('.jpg'),'Unsafe import filename')
    expected='/wands/pilot-media-v1/'+filename
    for role in ('base_image','small_image','thumbnail'):
        check(fields[role]==expected,'Media path escaped reviewed destination')
        check(fields[role+'_label']==fields['base_image_label'] and fields[role+'_label'].endswith(' - synthetic lab assortment'),'Inconsistent media labels')
    return 'pub/media/import'+expected


def build(args):
    out=args.output_dir.resolve();check(not out.exists(),'Choose fresh output')
    pins={};pin_packet(args.assignment,pins,'wands-pilot-media-assignment-v1');pin_packet(args.exports,pins,'wands-storefront-exports-v1')
    rows=json.loads((args.assignment/'assignments.json').read_text())
    check(len(rows)==5 and {row['target_sku'] for row in rows}==TARGETS,'Wrong five-product media scope')
    snapshot=json.loads(args.snapshot.read_text());acceptance=json.loads(args.definition_acceptance.read_text())
    check(snapshot['consistent_read_only'] is True and snapshot['host']=='relevance.comtom.lab','Wrong source snapshot')
    check(acceptance['native_template_verified'] is True and acceptance['rollback_verified'] is True,'Definition rehearsal is not verified')
    for path,digest in acceptance['inputs'].items():check(sha256(Path(path))==digest,'Definition acceptance input drift')
    tables=snapshot['rows'];entities={r['sku']:r for r in tables['catalog_product_entity']}
    check(TARGETS<=set(entities),'Media target missing from captured scope')
    ids={str(entities[sku]['entity_id']) for sku in TARGETS}
    associations=[r for r in tables['catalog_product_entity_media_gallery_value_to_entity'] if str(r['entity_id']) in ids]
    gallery_ids={str(r['value_id']) for r in associations}
    old_media=[r for r in tables['catalog_product_entity_media_gallery'] if str(r['value_id']) in gallery_ids]
    csv_path=args.assignment/'media.review.csv'
    with csv_path.open(newline='') as handle:csv_rows=list(csv.DictReader(handle))
    check(csv_rows==[r['fields'] for r in rows],'CSV differs from approved assignment rows')
    staged=[];total=0
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent,prefix='.native-media-stage-') as temporary:
        stage=Path(temporary)
        for row in rows:
            destination=validate_fields(row);source=args.exports/row['image']['file']
            check(sha256(source)==row['image']['sha256'] and source.stat().st_size==row['image']['bytes'],'Reviewed media changed')
            target=stage/'staging-root'/destination;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
            check(sha256(target)==row['image']['sha256'],'Staged media differs')
            total+=source.stat().st_size
            staged.append({'sku':row['target_sku'],'path':'staging-root/'+destination,'bytes':source.stat().st_size,'sha256':sha256(target)})
        destination=stage/'staging-root/var/wands/media.review.csv';destination.parent.mkdir(parents=True);shutil.copyfile(csv_path,destination)
        write_json(stage/'old-media-backup-required.json',{'associations':associations,'gallery_files':old_media,'binaries_backed_up':False,'retirement_approved':False})
        for path in (args.snapshot,args.definition_acceptance,Path(__file__)):pins[str(path.resolve())]=sha256(path)
        summary={'target_products':5,'image_roles':15,'image_labels':15,'files':5,'bytes':total,
            'staged':staged,'existing_gallery_associations':len(associations),'existing_gallery_files':len(old_media),
            'parent_assignments':0,'old_gallery_policy':'preserve; retirement requires separate approval',
            'native_import_validated':False,'native_import_executed':False,'rollback_rehearsed_for_media':False,
            'live_definition_preflight_required':True,'remote_media_uploaded':False,'publication_approved':False,
            'next_step':'Use a fresh disposable Mage-OS root with the verified definition migration applied. Native validateSource can persist import staging data; never treat validation as a live read-only operation.'}
        write_json(stage/'scope.json',summary)
        outputs={str(path.relative_to(stage)):sha256(path) for path in stage.rglob('*') if path.is_file()}
        write_json(stage/'manifest.json',{'version':'wands-native-media-rehearsal-v1','inputs':pins,'outputs':outputs,'publication_approved':False})
        stage.rename(out)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('assignment','exports','snapshot','definition-acceptance','output-dir'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args();args.output_dir.parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=args.output_dir.with_suffix('.log'),level=logging.INFO)
    try:build(args);logging.info('Five reviewed JPEGs staged locally; native import and live approval remain pending')
    except Exception:logging.exception('Native media rehearsal staging failed');raise SystemExit(1)
