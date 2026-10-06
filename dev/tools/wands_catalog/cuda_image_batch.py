"""Pinned, offline FLUX.2 Klein CUDA renderer. Produces candidates for Studio QA."""
from __future__ import annotations

import argparse
import fcntl
from importlib.metadata import version
import json
import os
from pathlib import Path
import re
import time

from image_policy import validate_prompt
from remote_image_batch import canonical,digest,reference_path,sha256,verify_model_files


def validate_packet(manifest_path,expected_hash,model_path):
    if sha256(manifest_path)!=expected_hash:raise ValueError('Batch manifest changed')
    packet=json.loads(manifest_path.read_text());profile=packet.get('renderer',{})
    if (packet.get('schema')!=3 or not packet.get('jobs')
            or profile.get('backend')!='diffusers-cuda' or profile.get('dtype')!='bfloat16'
            or profile.get('quantize') is not None or profile.get('offload')!='model_cpu'):
        raise ValueError('Unsupported CUDA packet')
    if profile.get('candidate_sha256')!=packet.get('candidate_sha256'):
        raise ValueError('Renderer belongs to a different candidate')
    for package,pin in profile['packages'].items():
        if version(package)!=pin:raise ValueError('Generation dependency differs: '+package)
    if any(profile['model_files'].get(k)!=v for k,v in packet['model_files'].items()):
        raise ValueError('Renderer model differs from the frozen source model')
    verify_model_files(model_path,profile['model_files'])
    for name,pin in profile['code_files'].items():
        if name not in {'cuda_image_batch.py','remote_image_batch.py','image_policy.py'}:
            raise ValueError('Unexpected renderer code filename')
        if sha256(Path(__file__).parent/name)!=pin:raise ValueError('Renderer code changed: '+name)
    identifiers=set()
    for job in packet['jobs']:
        if (not re.fullmatch('[a-f0-9]{64}',job['job_id']) or job['job_id'] in identifiers
                or type(job['attempt']) is not int or job['attempt']<1):raise ValueError('Invalid job')
        identifiers.add(job['job_id']);validate_prompt(job['prompt']);reference_path(manifest_path,job)
    return packet


def render(manifest_path,expected_hash,model_path,output):
    output.mkdir(parents=True,exist_ok=True)
    with (output/'worker.lock').open('a') as stream:
        try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit(73)
        packet=validate_packet(manifest_path,expected_hash,model_path)
        return render_verified(packet,manifest_path,expected_hash,model_path,output)


def render_verified(packet,manifest_path,expected_hash,model_path,output):
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    # This isolated runtime has no host compiler or Python development headers.
    # Use PyTorch's prebuilt operators rather than its optional native DSL JIT.
    os.environ['TORCH_DISABLE_NATIVE_JIT']='1'
    import torch
    from diffusers import Flux2KleinPipeline
    from PIL import Image
    if not torch.cuda.is_available():raise RuntimeError('CUDA unavailable')
    config=packet['config'];profile_pin=digest(packet['renderer']);pipe=None;images=[]
    for job in packet['jobs']:
        path=output/(job['job_id']+'.jpg');metadata=path.with_suffix('.json')
        source=reference_path(manifest_path,job)
        if path.exists():
            item=json.loads(metadata.read_text())
            if (item.get('job_sha256')!=digest(job) or sha256(path)!=item.get('image_sha256')
                    or item.get('renderer_sha256')!=profile_pin):raise ValueError('Existing CUDA attempt changed')
        else:
            if pipe is None:
                pipe=Flux2KleinPipeline.from_pretrained(str(model_path),torch_dtype=torch.bfloat16,local_files_only=True)
                pipe.enable_model_cpu_offload()
            formatted=pipe.tokenizer.apply_chat_template([{'role':'user','content':job['prompt']}],
                        tokenize=False,add_generation_prompt=True,enable_thinking=False)
            if len(pipe.tokenizer(formatted,truncation=False,add_special_tokens=True)['input_ids'])>512:
                raise ValueError('Prompt exceeds token budget')
            extra={}
            if source:
                with Image.open(source) as image:extra['image']=image.convert('RGB')
            torch.cuda.synchronize();torch.cuda.reset_peak_memory_stats();started=time.monotonic()
            result=pipe(prompt=job['prompt'],height=config['height'],width=config['width'],
                        guidance_scale=config['guidance'],num_inference_steps=config['steps'],
                        max_sequence_length=512,generator=torch.Generator(device='cuda').manual_seed(job['seed']),**extra)
            torch.cuda.synchronize()
            temporary=path.with_suffix('.tmp.jpg')
            result.images[0].convert('RGB').save(temporary,format='JPEG',quality=92,optimize=True)
            item={'job_id':job['job_id'],'job_sha256':digest(job),'image_sha256':sha256(temporary),
                  'renderer_sha256':profile_pin,'seconds':round(time.monotonic()-started,3),
                  'peak_memory_bytes':torch.cuda.max_memory_allocated()}
            metadata.write_text(canonical(item)+'\n');os.replace(temporary,path)
            print(canonical({'generated_job':job['job_id'],'seconds':item['seconds'],
                             'peak_memory_bytes':item['peak_memory_bytes']}),flush=True)
        images.append(item)
    result={'schema':2,'batch_id':packet['batch_id'],'manifest_sha256':expected_hash,
            'renderer_sha256':profile_pin,'images':images}
    temporary=output/'results.tmp.json';temporary.write_text(canonical(result)+'\n');os.replace(temporary,output/'results.json')
    return {'generated':len(images),'seconds':sum(x['seconds'] for x in images),
            'peak_memory_bytes':max(x['peak_memory_bytes'] for x in images)}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['render'])
    p.add_argument('--manifest',required=True,type=Path);p.add_argument('--manifest-sha256',required=True)
    p.add_argument('--model-path',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();print(json.dumps(render(a.manifest.resolve(),a.manifest_sha256,a.model_path.resolve(),a.output.resolve())))


if __name__=='__main__':main()
