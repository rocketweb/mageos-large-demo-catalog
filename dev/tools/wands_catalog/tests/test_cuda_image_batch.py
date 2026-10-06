import fcntl
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock,patch

from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cuda_image_batch as cuda
from image_policy import product_prompt
from remote_image_batch import digest,sha256


class CudaRendererTest(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.path=self.root/'manifest.json';self.out=self.root/'output'
        source=self.root/'source.jpg';Image.new('RGB',(16,16),'white').save(source)
        pin=sha256(source);references=self.root/'references';references.mkdir()
        (references/(pin+'.jpg')).write_bytes(source.read_bytes())
        self.packet={'schema':3,'batch_id':'a'*32,'candidate_sha256':'candidate','model_files':{},
            'config':{'width':16,'height':16,'steps':4,'guidance':1},
            'renderer':{'backend':'diffusers-cuda','candidate_sha256':'candidate','dtype':'bfloat16',
                        'quantize':None,'offload':'model_cpu','packages':{},'model_files':{},'code_files':{}},
            'jobs':[{'job_id':f'{n:064x}','attempt':1,'seed':n,'prompt':product_prompt('A plain blue chair'),
                     'reference_sha256':pin if n else None,'reference_file':f'references/{pin}.jpg' if n else None} for n in (0,1)]}
        self.save()

    def save(self):self.path.write_text(json.dumps(self.packet))

    def test_generated_and_edited_images_use_pinned_parameters_and_resume(self):
        pipe=MagicMock();pipe.return_value.images=[Image.new('RGB',(16,16),'blue')]
        pipe.tokenizer.return_value={'input_ids':[1]};pipe.tokenizer.apply_chat_template.return_value='prompt'
        klass=MagicMock();klass.from_pretrained.return_value=pipe
        gpu=MagicMock();gpu.is_available.return_value=True;gpu.max_memory_allocated.return_value=123
        torch=SimpleNamespace(cuda=gpu,bfloat16='bf16',Generator=MagicMock())
        with patch.dict(sys.modules,{'torch':torch,'diffusers':SimpleNamespace(Flux2KleinPipeline=klass)}):
            cuda.render(self.path,sha256(self.path),self.root/'model',self.out)
            cuda.render(self.path,sha256(self.path),self.root/'model',self.out)
        klass.from_pretrained.assert_called_once();pipe.enable_model_cpu_offload.assert_called_once()
        self.assertEqual(pipe.call_count,2)
        self.assertNotIn('image',pipe.call_args_list[0].kwargs)
        self.assertEqual(pipe.call_args_list[1].kwargs['image'].size,(16,16))
        self.assertEqual(pipe.call_args.kwargs['num_inference_steps'],4)
        result=json.loads((self.out/'results.json').read_text())
        self.assertEqual(result['renderer_sha256'],digest(self.packet['renderer']))
        self.assertEqual(len(result['images']),2)
        self.assertEqual(os.environ.get('TORCH_DISABLE_NATIVE_JIT'),'1')

    def test_busy_worker_does_not_load_cuda(self):
        self.out.mkdir()
        with (self.out/'worker.lock').open('a') as stream,patch.object(cuda,'render_verified') as render:
            fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(SystemExit) as error:cuda.render(self.path,sha256(self.path),self.root,self.out)
            self.assertEqual(error.exception.code,73);render.assert_not_called()

    def test_missing_prohibition_or_modified_reference_fails_before_gpu(self):
        with patch.object(cuda,'render_verified') as render:
            self.packet['jobs'][0]['prompt']='A chair with size labels';self.save()
            with self.assertRaises(ValueError):cuda.render(self.path,sha256(self.path),self.root,self.out)
            self.packet['jobs'][0]['prompt']=product_prompt('A chair');self.save()
            (self.root/self.packet['jobs'][1]['reference_file']).write_bytes(b'changed')
            with self.assertRaises(ValueError):cuda.render(self.path,sha256(self.path),self.root,self.out)
            render.assert_not_called()

    def test_environment_changes_fail_closed(self):
        with patch.object(cuda,'version',return_value='different'):
            self.packet['renderer']['packages']={'torch':'pinned'};self.save()
            with self.assertRaises(ValueError):cuda.validate_packet(self.path,sha256(self.path),self.root)
        self.packet['renderer']['packages']={};self.packet['renderer']['code_files']={'../other':'wrong'};self.save()
        with self.assertRaises(ValueError):cuda.validate_packet(self.path,sha256(self.path),self.root)


if __name__=='__main__':unittest.main()
