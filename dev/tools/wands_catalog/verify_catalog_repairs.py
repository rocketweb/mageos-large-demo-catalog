#!/usr/bin/env python3
"""Verify a local correction packet, including forward/inverse record parity.

Read-only. This does not prove that Magento can import the packet or replace
the fresh destination snapshot, database backup and deployment acceptance.
"""
import argparse
import copy
import json
import logging
from pathlib import Path

from build_realism_review import read_csv, unique_index
from catalog_repairs import read_jsonl, validate_candidate, scan_families, bundle_reference_impact, INVENTORY, PRICE_FIELDS
from definition_resolutions import validate_resolved_definition, remaining_rules
from prepare_catalog import sha256


def check(condition, message):
    if not condition:
        raise ValueError(message)


def verify_operations(after, changes, inverse, retired):
    """Rewind and replay complete records, not just compare record counts."""
    current=unique_index(after,'sku'); forward=unique_index(changes,'sku')
    restore=unique_index(inverse,'sku'); gone=unique_index(retired,'sku')
    check(set(restore)==set(forward)|set(gone),'Inverse coverage differs from affected SKUs')
    check(not (set(gone)&set(current)),'Retired SKU is still active')
    check(set(forward)<=set(current),'Changed SKU is not active')
    before=copy.deepcopy(current)
    for sku,item in restore.items():
        check(item['restore']['sku']==sku,'Inverse record identity mismatch')
        check(item['executable'] is False,'Executable inverse operation')
        before[sku]=copy.deepcopy(item['restore'])
    for sku,item in gone.items():
        check(item['executable'] is False,'Executable retirement operation')
        check(item['before']==before[sku],'Retirement snapshot disagrees with inverse')
    replay=copy.deepcopy(before)
    for sku,item in forward.items():
        check(item['executable'] is False,'Executable forward operation')
        expected={k for k in set(before[sku])|set(current[sku]) if before[sku].get(k)!=current[sku].get(k)}
        check(set(item['fields'])==expected,'Incomplete forward field diff: '+sku)
        for key,values in item['fields'].items():
            check(values=={'before':before[sku].get(key),'after':current[sku].get(key)},'Forward field value mismatch: '+sku+':'+key)
            if key in current[sku]: replay[sku][key]=copy.deepcopy(values['after'])
            else: replay[sku].pop(key,None)
    for sku in gone: replay.pop(sku)
    check(replay==current,'Forward replay does not reproduce candidate records')
    validate_candidate(list(before.values()),after,retired)
    return before


def verify_packet(packet):
    packet=packet.resolve(); manifest=json.loads((packet/'manifest.json').read_text())
    for path,digest in manifest['inputs'].items():
        check(Path(path).is_file() and sha256(Path(path))==digest,'Pinned input changed: '+path)
    for name,digest in manifest['outputs'].items():
        check(Path(name).name==name,'Unsafe output path')
        check((packet/name).is_file() and sha256(packet/name)==digest,'Packet output changed: '+name)
    check({p.name for p in packet.iterdir()}==set(manifest['outputs'])|{'manifest.json'},'Unexpected packet contents')
    roots=read_jsonl(packet/'candidate-products.jsonl'); children=read_jsonl(packet/'candidate-children.jsonl')
    changes=read_jsonl(packet/'changes.proposed.jsonl'); inverse=read_jsonl(packet/'inverse.proposed.jsonl')
    retired=read_jsonl(packet/'retirements.proposed.jsonl')
    before=verify_operations(roots+children,changes,inverse,retired)
    base=Path(manifest['baseline_packet']); baseline_manifest=base/'manifest.json'
    check(str(baseline_manifest) in manifest['inputs'],'Baseline manifest not pinned')
    lineage=json.loads(baseline_manifest.read_text())
    patch=unique_index(read_csv(Path(lineage['inputs']['patch']['path'])),'sku')
    families=unique_index(read_jsonl(Path(lineage['inputs']['families']['path'])),'source_product_id')
    prepared=unique_index(read_csv(Path(lineage['inputs']['prepared']['path'])),'wands_product_id')
    baseline=read_jsonl(base/'products.jsonl')+read_jsonl(base/'children.jsonl')
    for record in baseline:
        original=copy.deepcopy(record);original['catalog_fields']=patch[record['sku']]
        check(before[record['sku']]==original,'Inverse differs from frozen pilot: '+record['sku'])
    expected_ids=set()
    for root in roots:
        old=before[root['sku']]; family=families.get(old['source_product_id'])
        original=family['parent'] if family else prepared[old['source_product_id']]
        expected_ids.add(original['sku'])
        check(old['identity']=={k:original[k] for k in ('sku','product_type','url_key')},'Original root identity changed')
        check(old['axes']==(family['axes'] if family else []),'Original root axes changed')
        for child in family['variants'] if family else []:
            expected_ids.add(child['sku'])
            check(before[child['sku']]['variant_options']==child['options'],'Original child options changed')
            check(before[child['sku']]['parent_sku']==root['sku'],'Original child parent changed')
    check(set(before)==expected_ids,'Original family closure differs from source records')
    for sku,record in before.items():
        check(record['catalog_fields']==patch[sku],'Inverse catalog values differ from pinned patch: '+sku)
    current=unique_index(roots+children,'sku')
    for record in current.values():
        structural=record.get('structural_review')
        if structural:
            seed=before[structural['inventory_seed_sku']]
            check(record['kind']=='simple' and before[record['sku']]['kind']=='configurable','Invalid proposed type conversion')
            check(structural['actual_inventory_transfer_approved'] is False,'Inventory conversion unexpectedly approved')
            check(all(record['catalog_fields'].get(k)==seed['catalog_fields'].get(k) for k in (*INVENTORY,*PRICE_FIELDS)),'Type conversion differs from exact inventory/price seed')
    source=unique_index(read_csv(Path(lineage['inputs']['source']['path']),'\t'),'product_id')
    findings=scan_families(list(families.values()),source)
    recorded_audit=unique_index(read_jsonl(packet/'definition-audit.after.jsonl'),'root_sku')
    check(set(recorded_audit)=={r['root_sku'] for r in findings},'After-audit scope differs from original full-family scan')
    for finding in findings:
        sku=finding['root_sku']
        if sku in current and current[sku].get('repair'):
            group=[c for c in children if c['parent_sku']==sku]
            check(recorded_audit[sku]==validate_resolved_definition(current[sku],group,finding['issues']),'After-audit evidence differs from candidate semantics')
        else:
            check(recorded_audit[sku]['status']=='unresolved','Unchanged definition marked resolved')
    remaining=sum(r['status']=='unresolved' for r in recorded_audit.values())
    check(manifest['unresolved_original_family_findings']==remaining,'Unresolved audit count mismatch')
    policy=json.loads((packet/'resolution-policy.json').read_text())
    if policy['enabled']:
        check(remaining==0 and not read_jsonl(packet/'held-definitions.jsonl'),'Approved batch left unresolved definitions')
        definitions=remaining_rules()
        check(manifest['remaining_definition_rules_applied']==len(definitions),'Resolution rule count mismatch')
        for sku,rule in definitions.items():
            check(current[sku]['repair']['resolution_kind']==rule['resolution_kind'],'Missing explicit resolution metadata')
            if rule.get('expected_component_count'):
                for subject in [c for c in children if c['parent_sku']==sku] or [current[sku]]:
                    check(subject['dimension_design']['total_component_quantity']==rule['expected_component_count'],'Fixed assortment component count mismatch')
        release_manifest=Path(lineage['inputs']['packet_manifest']['path'])
        bundle_path=release_manifest.parent/'bundles.jsonl'
        check(str(bundle_path) in manifest['inputs'],'Bundle source is not pinned')
        expected=bundle_reference_impact(read_jsonl(bundle_path),{r['sku'] for r in changes},{r['sku'] for r in retired})
        check(json.loads((packet/'bundle-reference-impact.json').read_text())==expected,'Bundle impact report mismatch')
    for name in ('gallery-briefs.jsonl','specifications.sparse.proposed.jsonl','reference-review.jsonl',
                 'image-repair-drafts.jsonl','recommendations.review.jsonl'):
        check(all(row['executable'] is False for row in read_jsonl(packet/name)),'Executable review proposal: '+name)
    for name in ('benchmark-freeze.json','new-judgment-seeds.jsonl','collections.json'):
        check((packet/name).read_bytes()==(base/name).read_bytes(),'Frozen baseline artifact changed: '+name)
    counts={'products':len(roots),'selected_children':len(children),'changed_active_records':len(changes),
            'retirement_proposals':len(retired),'total_affected_records':len(inverse)}
    check(all(manifest[k]==v for k,v in counts.items()),'Manifest counts disagree with exact records')
    check(manifest['live_writes']==0 and manifest['images_generated']==0 and manifest['deployment_ready'] is False,'Invalid local-only state')
    return {**counts,'input_hashes_verified':len(manifest['inputs']),'output_hashes_verified':len(manifest['outputs']),
            'original_family_findings_rechecked':len(findings),'unresolved_original_family_findings':remaining,
            'forward_inverse_round_trip':True,'original_family_closure':len(before),'frozen_benchmark_unchanged':True,
            'magento_import_validated':False,'visual_acceptance':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet',type=Path,required=True)
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args()
    log=args.packet.with_name(args.packet.name+'.verify.log')
    logging.basicConfig(filename=log,level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:
        result=verify_packet(args.packet)
        logging.info('Verified: %s',json.dumps(result,sort_keys=True))
        if args.json: print(json.dumps(result,indent=2))
        return 0
    except Exception:
        logging.exception('Local packet verification failed')
        return 1


if __name__=='__main__': raise SystemExit(main())
