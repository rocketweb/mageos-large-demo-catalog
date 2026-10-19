import csv
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

from PIL import Image,ImageDraw

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import white_jpeg_text_recreation as recreation


class TextRecreationTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.job=Path(self.tmp.name);approval=self.job/'human-approvals/remaining-spotcheck-20261019-A';approval.mkdir(parents=True)
        self.audit=self.job/'audit-expanded-fast-20261018';self.audit.mkdir()
        data=self.job/'data';data.mkdir();self.queue=self.job/'recreated'
        # An invalid image proves that preparation and output recording never
        # decode a source photo, even to obtain its dimensions.
        self.source=self.job/'source-must-not-be-decoded.jpg';self.source.write_bytes(b'not an image')
        sha=recreation.sha(self.source);items=[];products=[]
        with sqlite3.connect(self.audit/'audit.sqlite3')as db:
            db.executescript('CREATE TABLE category_features(file TEXT,features TEXT);CREATE TABLE glass_outline_checks(file TEXT,verdict TEXT);')
            for n in range(114):
                filename=f'source-{n}.jpg';sku=f'SKU-{n}'
                items.append({'id':f'P001-{n:03d}','decision':'original','file':filename,'name':'Pillow',
                    'skus':[sku],'original_path':str(self.source),'source_sha256':sha,
                    'candidate_path':str(self.source),'output_sha256':sha})
                products.append({'sku':sku,'name':f'Bird Pillow {n}','description':'<p>A square cotton bird pillow.</p>',
                    'lab_spec_width_cm':'48','lab_spec_shape':'Square','color':'Blue'})
                db.execute('INSERT INTO category_features VALUES(?,?)',(filename,json.dumps({'dimensions':[768,768]})))
        recreation.write(approval/'plan.json',{'items':items})
        recreation.write(approval/'applied.json',{'white':869,'original_exceptions':114})
        recreation.write(self.job/'local-catalog.json',{'data':str(data)})
        for name in ('1-simple.csv','2-configurable.csv','3-bundle.csv','6-qa.csv'):
            with(data/name).open('w',newline='')as f:
                writer=csv.DictWriter(f,fieldnames=products[0]);writer.writeheader()
                if name=='1-simple.csv':writer.writerows(products)

    def test_prepare_uses_only_catalog_text_and_measured_dimensions(self):
        recreation.prepare(self.job,self.queue)
        jobs=recreation.jobs(self.queue)
        self.assertEqual(len(jobs),114)
        self.assertTrue(all(j['reference_images']==[]and j['source_image_decoded']is False for j in jobs))
        prompt=Path(jobs[0]['prompt_file']).read_text()
        self.assertIn('Bird Pillow 0',prompt);self.assertIn('square cotton bird pillow',prompt)
        self.assertNotIn(str(self.source),prompt)
        html=(self.queue/'review.html').read_text()
        self.assertNotIn(self.source.as_uri(),html)

    def test_generated_image_is_encoded_without_reading_original_pixels(self):
        recreation.prepare(self.job,self.queue)
        generated=self.job/'generated.png';image=Image.new('RGB',(512,512),'white')
        ImageDraw.Draw(image).rectangle((100,100,400,400),fill='navy');image.save(generated)
        result=recreation.record(self.queue,'NR001',generated)
        self.assertEqual(result['completed'],1)
        record=recreation.read(self.queue/'records/NR001.json')
        self.assertEqual(record['jpeg_quality'],90)
        self.assertEqual(record['reference_images'],[])
        self.assertFalse(record['original_image_viewed'])
        with Image.open(record['jpeg_path'])as check:
            self.assertEqual(check.size,(768,768));self.assertEqual(check.mode,'RGB');self.assertEqual(check.format,'JPEG')
        self.assertEqual(self.source.read_bytes(),b'not an image')
        with self.assertRaisesRegex(ValueError,'overwrite'):
            recreation.record(self.queue,'NR001',generated)


if __name__=='__main__':unittest.main()
