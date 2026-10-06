import json,subprocess,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
class BackupScopeTest(unittest.TestCase):
    def test_exact_full_comtom_population_can_receive_media_only_recovery_backup(self):
        tool=Path(__file__).resolve().parents[1]/'expansion_database_backup.php'
        receipt={'schema':1,'candidate_sha256':'921e5e1a0d8a386c93bf0f80dd6543c9d3561e5ad27e31df5b80b9d3e0d8502e','target_root':'/var/www/html','original_before_wands_products':53844,'before_wands_products':107688,'already_imported_skus':['WANDS-SYN-'+str(i) for i in range(53844)],'media_only':True}
        code='require '+json.dumps(str(tool))+'; echo expansionBackupPopulation("/var/www/html", json_decode('+json.dumps(json.dumps(receipt))+',true));'
        p=subprocess.run(['/opt/homebrew/bin/php'],input='<?php '+code,capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stdout,'107688')
    def test_exact_reconciled_population_is_backed_up(self):
        tool=Path(__file__).resolve().parents[1]/'expansion_database_backup.php'
        receipt={'schema':1,'candidate_sha256':'921e5e1a0d8a386c93bf0f80dd6543c9d3561e5ad27e31df5b80b9d3e0d8502e','target_root':'/Users/matt/code/mageos-latest','original_before_wands_products':42994,'before_wands_products':42996,'already_imported_skus':['WANDS-SYN-A','WANDS-SYN-B']}
        code='require '+json.dumps(str(tool))+'; echo expansionBackupPopulation("/Users/matt/code/mageos-latest", json_decode('+json.dumps(json.dumps(receipt))+',true));'
        p=subprocess.run(['/opt/homebrew/bin/php','-r',code],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stdout,'42996')
        receipt['before_wands_products']=42997
        code='require '+json.dumps(str(tool))+'; expansionBackupPopulation("/Users/matt/code/mageos-latest", json_decode('+json.dumps(json.dumps(receipt))+',true));'
        self.assertNotEqual(subprocess.run(['/opt/homebrew/bin/php','-r',code],capture_output=True).returncode,0)
