"""Admit a finite, hash-bound recovery after a measured source recolor fix."""
from __future__ import annotations

import argparse
import ast
from functools import lru_cache
import json
from pathlib import Path
from types import CodeType

from build_expanded_catalog import digest
from prepare_catalog import sha256

STRATEGY = 'source-recolor-v2'
LEGACY_CUE = 'Preserve every mounting part, hanging chain and ring in full view inside the frame.'
MAX_EXTRA_ATTEMPTS = 2
ADMISSION = 'source-recolor-recovery.json'


def code_identity(code):
    """Compare implementations without file positions or line tables."""
    constants=tuple(code_identity(c) if isinstance(c,CodeType) else c for c in code.co_consts)
    return (code.co_code,constants,code.co_names,code.co_varnames,code.co_freevars,code.co_cellvars,
            code.co_argcount,code.co_posonlyargcount,code.co_kwonlyargcount,code.co_flags)


@lru_cache(maxsize=4)
def prompt_source(path,stamp,size):
    source=Path(path).read_text();tree=ast.parse(source,filename=path)
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='source_recolor_prompt')
    # Compile without executing the module. This preserves its future flags and
    # verifies the loaded function, while unrelated line moves remain harmless.
    compiled=compile(tree,path,'exec',dont_inherit=True)
    code=next(c for c in compiled.co_consts if isinstance(c,CodeType) and c.co_name==node.name)
    text=''.join(source.splitlines(keepends=True)[node.lineno-1:node.end_lineno])
    return text,code_identity(code)


def prompt_pin():
    import bulk_expansion_images
    path=Path(bulk_expansion_images.__file__);stat=path.stat()
    source,expected=prompt_source(str(path),stat.st_mtime_ns,stat.st_size)
    if code_identity(bulk_expansion_images.source_recolor_prompt.__code__)!=expected:
        raise ValueError('Loaded recolor implementation differs from its current source; restart the worker')
    return digest(source)


def benchmark_evidence(path, desc):
    evidence=json.loads(path.read_text())
    if (evidence.get('passed') is not True or evidence.get('strategy')!=STRATEGY
            or evidence.get('direct_visual_review_complete') is not True
            or evidence.get('prompt_implementation_sha256')!=prompt_pin()
            or any(evidence.get(k)!=desc[k] for k in ('candidate_sha256','review_identity'))):
        raise ValueError('Recovery requires a current, visually reviewed prompt comparison')
    return evidence


@lru_cache(maxsize=4)
def load_admission(path, stamp, size, run_pin, implementation_pin, benchmark_stamp):
    admission=json.loads(Path(path).read_text())
    if (admission.get('schema')!=1 or admission.get('strategy')!=STRATEGY
            or admission.get('max_extra_attempts')!=MAX_EXTRA_ATTEMPTS
            or admission.get('run_sha256')!=run_pin
            or admission.get('prompt_implementation_sha256')!=implementation_pin):
        raise ValueError('Recovery admission changed or belongs to another run or prompt')
    benchmark=Path(admission['benchmark_path'])
    if sha256(benchmark)!=admission['benchmark_sha256']:
        raise ValueError('Recovery benchmark changed')
    benchmark_evidence(benchmark,json.loads((Path(path).parent/'run.json').read_text()))
    return admission


def allowed(run, record, job, reference, history):
    from bulk_expansion_images import source_recolor_prompt
    path=run/ADMISSION
    if not path.is_file():return False
    # Include mutable file identities in the cache key; a changed receipt never
    # inherits an earlier successful check. The job list itself stays immutable.
    stat=path.stat()
    header=admission_header(str(path),stat.st_mtime_ns,stat.st_size)
    benchmark=Path(header['benchmark_path']);benchmark_stat=benchmark.stat()
    admission=load_admission(str(path),stat.st_mtime_ns,stat.st_size,sha256(run/'run.json'),
                             prompt_pin(),(benchmark_stat.st_mtime_ns,benchmark_stat.st_size))
    entry=admission['jobs'].get(job['job_id'])
    if not entry or record['state'] not in {'rejected','review_required','interrupted'}:return False
    baseline=entry['baseline_attempts'];attempts=record['attempts']
    if (not baseline<=attempts<baseline+MAX_EXTRA_ATTEMPTS or len(history)!=attempts
            or digest(job)!=entry['request_sha256'] or sha256(reference)!=entry['reference_sha256']
            or digest(source_recolor_prompt(job))!=entry['prompt_sha256']):return False
    directory=run/'candidates'/job['job_id']
    if [item.get('attempt') for item in history]!=list(range(1,attempts+1)):return False
    original=directory/f'attempt-{baseline:02d}.jpg'
    if (sha256(original)!=entry['baseline_image_sha256']
            or sha256(original.with_suffix('.json'))!=entry['baseline_metadata_sha256']
            or LEGACY_CUE not in history[baseline-1].get('actual_prompt','')):return False
    current=Path(record['image_path'])
    if (not current.is_file() or sha256(current)!=record['image_sha256']
            or history[-1].get('image_sha256')!=record['image_sha256']):return False
    return all(item.get('reference_sha256')==entry['reference_sha256']
               and digest(item.get('actual_prompt'))==entry['prompt_sha256'] for item in history[baseline:])


@lru_cache(maxsize=4)
def admission_header(path, stamp, size):
    return json.loads(Path(path).read_text())


def prepare(run, benchmark):
    from bulk_expansion_images import (accepted_reference, connect, descriptor, lock,
                                      retry_allowed, source_recolor_prompt)
    desc=descriptor(run);benchmark=benchmark.resolve();benchmark_evidence(benchmark,desc)
    with lock(run,'generation'):
        if (run/ADMISSION).exists():raise ValueError('Recovery already admitted; budgets cannot be reset')
        db=connect(run);jobs={}
        try:
            for row in db.execute("SELECT * FROM jobs WHERE state IN ('rejected','review_required') AND attempts>=3 ORDER BY ordinal"):
                job=json.loads(row['request'])
                if not job.get('reference'):continue
                reference=accepted_reference(db,job,desc['review_identity'])
                if not reference or retry_allowed(run,row,job,reference):continue
                path=Path(row['image_path']);metadata=path.with_suffix('.json')
                if not metadata.is_file() or sha256(path)!=row['image_sha256']:continue
                event=json.loads(metadata.read_text())
                if LEGACY_CUE not in event.get('actual_prompt',''):continue
                jobs[row['job_id']]={'request_sha256':digest(job),'baseline_attempts':row['attempts'],
                    'baseline_image_sha256':row['image_sha256'],'baseline_metadata_sha256':sha256(metadata),
                    'reference_sha256':sha256(reference),'prompt_sha256':digest(source_recolor_prompt(job))}
        finally:db.close()
    return {'schema':1,'strategy':STRATEGY,'max_extra_attempts':MAX_EXTRA_ATTEMPTS,
            'run_sha256':sha256(run/'run.json'),'benchmark_path':str(benchmark),
            'benchmark_sha256':sha256(benchmark),'prompt_implementation_sha256':prompt_pin(),
            'diagnosis':'Legacy shared prompt invented hardware and textile surfaces in accepted-source recolors.',
            'strategy_change':'Recolor the clean accepted source; preserve its existing components, material and background.',
            'jobs':jobs}


def main():
    from bulk_expansion_images import atomic_json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--benchmark',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Choose a new preview file; recovery receipts are immutable')
    if args.output.resolve()==(args.run/ADMISSION).resolve():parser.error('Prepare a preview before activating it')
    plan=prepare(args.run.resolve(),args.benchmark)
    atomic_json(args.output,plan)
    print(json.dumps({'eligible_jobs':len(plan['jobs']),'max_extra_attempts':MAX_EXTRA_ATTEMPTS,
                      'accepted_images_changed':0,'preview':str(args.output.resolve())}))


if __name__=='__main__':main()
