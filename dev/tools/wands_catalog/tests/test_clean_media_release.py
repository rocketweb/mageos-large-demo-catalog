import csv,hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'distribution'))
from build_clean_media_release import validated_projection
class CleanMediaReleaseTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.data={};self.changes={}
  self.policy=self.root/'exclusions.json';self.policy.write_text(json.dumps({'products':[{'sku':'WANDS-2'}]}))
  self.rules=self.root/'text.json';self.rules.write_text(json.dumps({'replacements':[{'from':'Disney','to':'Datney'}]}))
  self.directory=self.root/'clean';self.directory.mkdir()
  fields=['sku','name','product_type','related_skus','bundle_values']
  for name in ['1-simple.csv','2-configurable.csv','3-bundle.csv','4-media.csv','5-merchandising.csv','6-qa.csv']:
   old=self.root/name;new=self.directory/name
   rows=[{'sku':'WANDS-1','name':'Disney Table','product_type':'simple','related_skus':'WANDS-2','bundle_values':''},{'sku':'WANDS-2','name':'Star Wars','product_type':'simple','related_skus':'','bundle_values':''}]if name=='1-simple.csv'else[]
   for p,values in [(old,rows),(new,[{**rows[0],'name':'Datney Table','related_skus':''}]if rows else[])]:
    with p.open('w',newline='')as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(values)
   self.data['data/'+name]=old;self.changes[name]={'source_sha256':self.sha(old),'output_sha256':self.sha(new)}
  self.projection={'state':'verified','data':str(self.directory),'exclusions':str(self.policy),'exclusions_sha256':self.sha(self.policy),'text_policy_sha256':self.sha(self.rules),'changes':self.changes,'counts':{'products':1,'excluded_products':1}}
  self.config={'text_policy':str(self.rules)}
 def sha(self,p):return hashlib.sha256(p.read_bytes()).hexdigest()
 def test_only_exact_approved_exclusions_and_renames_are_packaged(self):
  result=validated_projection(self.projection,self.config,self.data)
  self.assertEqual(set(result),set(self.data));self.assertIn('Datney Table',result['data/1-simple.csv'].read_text())
 def test_hash_matched_unapproved_product_change_is_rejected(self):
  p=self.directory/'1-simple.csv';p.write_text(p.read_text().replace('Datney Table','Different product'));self.changes['1-simple.csv']['output_sha256']=self.sha(p)
  with self.assertRaisesRegex(ValueError,'approved changes'):validated_projection(self.projection,self.config,self.data)
 def test_source_and_exclusion_drift_are_rejected(self):
  self.policy.write_text('{}')
  with self.assertRaisesRegex(ValueError,'exclusion'):validated_projection(self.projection,self.config,self.data)
if __name__=='__main__':unittest.main()
