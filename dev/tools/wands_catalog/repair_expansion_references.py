"""Audit retained media and repair rejected references without altering the baseline."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time

from build_expanded_catalog import canonical, csv_rows, digest
from bulk_expansion_images import (CONFIG, atomic_json, connect, descriptor, lock,
                                   reference_design, status, review_eligible, record_review_failure, reference_held,
                                   prioritize_reference_work)
from generate_images import append_event
from image_policy import GuardedImageModel, product_prompt
from image_review import Reviewer, ReviewUnavailable, ReviewServiceUnavailable
from prepare_catalog import sha256
from run_catalog_media_pilot import check_token_budget


def corrective_geometry(subject):
    instructions=[]
    for count,part in re.findall(r'\b([2-9])\s*[- ]\s*(door|drawer|tier|shelves|shelf)\b',subject,re.I):
        noun={'door':'separate front door panels, each with its own handle',
              'drawer':'separate drawer fronts, each with its own pull',
              'tier':'distinct horizontal shelf levels',
              'shelf':'distinct useful horizontal shelf surfaces, including the highest and lowest shelves',
              'shelves':'distinct useful horizontal shelf surfaces, including the highest and lowest shelves'}[part.lower()]
        word={2:'two',3:'three',4:'four',5:'five',6:'six',7:'seven',8:'eight',9:'nine'}[int(count)]
        instructions.append('Rebuild the visible structure with exactly '+word+' '+noun+'. Make all of them clearly visible.')
        if part.lower()=='drawer' and int(count)==9:
            instructions.append('Arrange the drawer fronts in three horizontal rows and three vertical columns; each front has its own complete visible outline.')
    if re.search(r'\bL[- ]shape',subject,re.I):
        instructions.append('Rebuild the desktop as two joined perpendicular wings forming a clear L shape. Show both wings completely.')
    if re.search(r'\brod[- ]pocket\b',subject,re.I):
        instructions.append('The curtain header is a sewn fabric rod pocket, with the rod hidden inside the fabric. No exposed metal eyelets.')
    return ' '.join(instructions)


def repair_strategy(row, attempts):
    """Stop carrying a disproved silhouette into every repair attempt."""
    evidence=json.loads(attempts[-1]['review'] if attempts else row['review'])
    vision=evidence.get('vision',{})
    structural=(vision.get('geometry_defects') is True or vision.get('piece_count_matches') is False)
    counted=evidence.get('component_review') or {}
    if counted.get('confidence',0)>=.95:
        structural=structural or any(type(counted.get(key)) is int and counted[key]!=wanted
            for key,wanted in counted.get('expected',{}).items())
    # A failed identity edit is evidence that another edit of the same original
    # is a poor repair strategy. Fresh rendering still requires independent QA.
    failed_identity_edit=bool(attempts and vision.get('product_matches') is False)
    mode='generate' if structural or failed_identity_edit else 'edit'
    design=json.loads(row['design'])
    from completion_recovery import recipe
    lighting=recipe(design)
    if lighting and lighting['pattern']=='explicit-light-count':
        from image_policy import NO_MEASUREMENTS
        return 'generate',product_prompt(lighting['prompt'].replace(NO_MEASUREMENTS,'')+
            ' Intended product identity: '+design['subject']+'. Additional visible features: '+design.get('construction','')+'.')
    introduction=('Create a new studio product photograph of this intended sale unit: ' if mode=='generate'
                  else 'Repair this product photograph to accurately depict this intended sale unit: ')
    body=(introduction+design['subject']+'. '
          'Product class: '+design.get('product_class','')+'. '
          'Material: '+design['material']+'. Color or finish: '+design['color']+'. '
          +corrective_geometry(design['subject'])+' '
          'Accurate silhouette, visible components, plausible joins and coherent construction matching that description. '
          'No lettering, numbers or graphic annotations. Natural photographic appearance, '
          'plain warm-white background, whole product inside the frame. No extra products or props.')
    return mode,product_prompt(body)


def register(run):
    desc=descriptor(run);baseline=Path(desc['baseline']);db=connect(run)
    rows={r['sku']:r for name in ('1-simple.csv','2-configurable.csv','3-bundle.csv')
          for r in csv_rows(baseline/'data'/name)}
    assignments=json.loads((baseline/'data/media-lineage.json').read_text())['assignments']
    inventory=json.loads((baseline/'data/media-inventory.json').read_text())
    covered=set()
    with db:
        for sku,assignment in assignments.items():
            name=assignment['file']
            # Shared bytes can represent distinct material, size or component briefs.
            # Every assigned SKU needs its own matching brief before export.
            covered.add(name);path=baseline/name;design=reference_design(rows[sku])
            if sha256(path)!=inventory[name]['sha256']:raise ValueError('Baseline media changed')
            db.execute('INSERT OR IGNORE INTO references_to_review VALUES(?,?,?,?,NULL)',
                       (inventory[name]['sha256'],digest(design),str(path),canonical(design)))
        if covered!=set(inventory):raise ValueError('Unassigned retained images require explicit audit briefs')
    db.close();atomic_json(run/'baseline-audit.json',{'images':len(covered),'inventory_sha256':sha256(baseline/'data/media-inventory.json')})
    return status(run)


def queue(db,pilot,run=None):
    from remote_reference_repairs import reserved_targets,kept_images
    reserved=reserved_targets(db)
    protected=kept_images(run) if run else set()
    selection=('AND EXISTS(SELECT 1 FROM job_references j JOIN jobs b ON b.job_id=j.job_id '
               'WHERE j.image_sha256=r.image_sha256 AND j.design_sha256=r.design_sha256 AND b.pilot=1)') if pilot else ''
    result=[];admitted=[];identity=None;fair_completion=False
    rows=list(db.execute('SELECT * FROM references_to_review r WHERE 1=1 '+selection+' ORDER BY path'))
    for row in prioritize_reference_work(db,rows):
        if (row['image_sha256'],row['design_sha256']) in reserved:continue
        from authorized_completion import reference_admitted
        completion=bool(run and reference_admitted(db,row))
        fair_completion=fair_completion or completion
        if not completion and (not row['review'] or (json.loads(row['review'])['decision'] not in {'rejected','review_required'} and not reference_held(db,row['image_sha256']))):continue
        attempts=list(db.execute('SELECT * FROM reference_repairs WHERE original_sha256=? AND design_sha256=? ORDER BY attempt',
                                 (row['image_sha256'],row['design_sha256'])))
        if row['image_sha256'] in protected or any(a['image_sha256'] in protected for a in attempts):continue
        if run and (completion or any(a['review'] and json.loads(a['review'])['decision']=='accepted' for a in attempts)):
            from export_expanded_catalog import accepted_retained
            from bulk_expansion_images import descriptor as current_descriptor
            # Descriptor validation hashes the entire frozen job file. Verify
            # it once for this scan, rather than thousands of times while the
            # generation lock prevents the remote GPUs from getting new work.
            if identity is None:identity=current_descriptor(run)['review_identity']
            if accepted_retained(db,row,identity):continue
        if attempts:
            latest=attempts[-1]
            if not latest['review'] or (not completion and json.loads(latest['review'])['decision'] not in {'rejected','review_required'}
                    and not reference_held(db,latest['image_sha256'])):continue
        from completion_recovery import reference_plan
        if len(attempts)<CONFIG['max_attempts'] or completion:
            result.append((row,len(attempts)+1))
        elif run and reference_plan(run,db,row,attempts):
            # A finite, diagnosed pilot should be observed before more untested
            # copies of its recipe enter the backlog.
            admitted.append((row,len(attempts)+1))
    if fair_completion:
        # Exhaustion used to rotate the queue naturally. With authorized
        # completion retries, path ordering can retry the same hard failures
        # forever. Visit less-tried briefs first; stable sorting retains the
        # waiting-product priority within an attempt round.
        result.sort(key=lambda item:item[1])
    return admitted+result


def repair(run,pilot=False,limit=0):
    # Generation and repair deliberately share the same GPU-worker lock.
    with lock(run,'generation'):
        desc=descriptor(run);db=connect(run)
        from bulk_expansion_images import generation_checkpoint_requested
        if generation_checkpoint_requested(run,db):db.close();return status(run)
        jobs=queue(db,pilot,run)
        if limit:jobs=jobs[:limit]
        if not jobs:db.close();return status(run)
        os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
        from transformers import Qwen2TokenizerFast
        from mflux.models.common.config.model_config import ModelConfig
        from mflux.models.flux2.variants import Flux2Klein, Flux2KleinEdit
        snapshot=Path(desc['model_snapshot'])
        for name,pin in desc['model_files'].items():
            if sha256(snapshot/name)!=pin['sha256']:raise ValueError('Pinned image model changed')
        tokenizer=Qwen2TokenizerFast.from_pretrained(snapshot/'tokenizer',local_files_only=True)
        models={}
        for row,attempt in jobs:
            if generation_checkpoint_requested(run,db):break
            original=Path(row['path'])
            if sha256(original)!=row['image_sha256']:raise ValueError('Original reference changed')
            attempts=list(db.execute('SELECT * FROM reference_repairs WHERE original_sha256=? AND design_sha256=? ORDER BY attempt',
                                     (row['image_sha256'],row['design_sha256'])))
            from completion_recovery import reference_plan
            recovery=reference_plan(run,db,row,attempts)
            from authorized_completion import reference_strategy
            mode,prompt=reference_strategy(db,row,attempts) or ((recovery['mode'],recovery['prompt']) if recovery else repair_strategy(row,attempts))
            check_token_budget(prompt,tokenizer)
            if mode not in models:
                klass=Flux2Klein if mode=='generate' else Flux2KleinEdit
                models[mode]=GuardedImageModel(klass(model_config=ModelConfig.from_name(CONFIG['model']),
                                                    model_path=str(snapshot),quantize=CONFIG['quantize']))
            directory=run/'reference-repairs'/digest([row['image_sha256'],row['design_sha256']])
            directory.mkdir(parents=True,exist_ok=True)
            path=directory/f'attempt-{attempt:02d}.jpg';metadata=path.with_suffix('.json')
            seed=(int(row['image_sha256'][:8],16)+104729*attempt)%(2**32)
            event={'original_sha256':row['image_sha256'],'design_sha256':row['design_sha256'],
                   'attempt':attempt,'prompt':prompt,'seed':seed,'mode':mode,'config':CONFIG}
            if path.exists():
                # Recover only a fully written, hash-verified attempt after a crash.
                saved=json.loads(metadata.read_text())
                if any(saved[k]!=v for k,v in event.items()) or saved['image_sha256']!=sha256(path):
                    raise ValueError('Incomplete or changed repair attempt')
            else:
                started=time.monotonic()
                args={'prompt':prompt,'seed':seed,'width':CONFIG['width'],'height':CONFIG['height'],
                      'num_inference_steps':CONFIG['steps'],'guidance':CONFIG['guidance']}
                if mode=='edit':args['image_paths']=[original]
                result=models[mode].generate_image(**args)
                temporary=path.with_suffix('.tmp.jpg')
                result.image.convert('RGB').save(temporary,format='JPEG',quality=92,optimize=True)
                os.link(temporary,path);temporary.unlink()
                event.update(image_sha256=sha256(path),seconds=round(time.monotonic()-started,3))
                atomic_json(metadata,event);append_event(run/'repair-events.jsonl',event)
            with db:db.execute('INSERT INTO reference_repairs VALUES(?,?,?,?,?,NULL)',
                              (row['image_sha256'],row['design_sha256'],attempt,str(path.resolve()),sha256(path)))
            status(run)
        db.close()
    return status(run)


def review_repairs(run,ocr,settings,pilot=False,limit=0):
    with lock(run,'reference-repair-review'):
        desc=descriptor(run);db=connect(run)
        from authorized_completion import policy
        p=policy(db,desc) or {}
        reviewer=Reviewer(desc['vision_model'],ocr,settings,component_advisory=bool(p.get('advisory_component_counts')),synthetic_names=bool(p.get('synthetic_name_context')))
        selection=('AND EXISTS(SELECT 1 FROM job_references j JOIN jobs b ON b.job_id=j.job_id '
                   'WHERE j.image_sha256=r.original_sha256 AND j.design_sha256=r.design_sha256 AND b.pilot=1)') if pilot else ''
        try:
            rows=list(db.execute('SELECT r.*,s.design FROM reference_repairs r JOIN references_to_review s '
                                 'ON s.image_sha256=r.original_sha256 AND s.design_sha256=r.design_sha256 '
                                 'WHERE r.review IS NULL '+selection+' ORDER BY image_path'))
            rows=prioritize_reference_work(db,rows,'original_sha256')
            completed=0;consecutive_errors=0
            for row in rows:
                if (run/'STOP').exists():break
                if limit and completed>=limit:break
                item=digest([row['original_sha256'],row['design_sha256'],row['attempt']])
                if not review_eligible(db,'repair',item):continue
                completed+=1
                path=Path(row['image_path'])
                if sha256(path)!=row['image_sha256']:raise ValueError('Repair changed before review')
                try:
                    result=reviewer.inspect(path,json.loads(row['design']))
                    from authorized_completion import relieve_review
                    result=relieve_review(db,result,json.loads(row['design']))
                except ReviewUnavailable as error:
                    if isinstance(error,ReviewServiceUnavailable):
                        from bulk_expansion_images import record_service_outage
                        record_service_outage(run,'repair',item,error)
                        raise
                    record_review_failure(db,run,'repair',item,error)
                    consecutive_errors+=1
                    if consecutive_errors>=3:raise
                    continue
                consecutive_errors=0
                with db:db.execute('UPDATE reference_repairs SET review=? WHERE original_sha256=? AND design_sha256=? AND attempt=?',
                    (canonical(result),row['original_sha256'],row['design_sha256'],row['attempt']))
                append_event(run/'repair-reviews.jsonl',{'original_sha256':row['original_sha256'],'attempt':row['attempt'],**result})
                status(run)
        finally:reviewer.close();db.close()
    return status(run)


def dispatch(args):
    if args.command=='register-baseline-audit':return register(args.run)
    if args.command=='repair-references':return repair(args.run,args.pilot,args.limit)
    return review_repairs(args.run,args.ocr,args.omlx_settings,args.pilot,args.limit)
