import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_expanded_catalog import canonical,digest
from completion_recovery import recipe,reference_plan
from image_policy import validate_prompt,NO_MEASUREMENTS
from prepare_catalog import sha256


class RecoveryBudgetTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.original=self.root/'original.jpg';self.original.write_bytes(b'original')
        self.failed=self.root/'failed.jpg';self.failed.write_bytes(b'failed')
        self.db=sqlite3.connect(':memory:');self.addCleanup(self.db.close);self.db.row_factory=sqlite3.Row
        self.db.execute('CREATE TABLE reference_completion_recovery(original_sha256,design_sha256,entry,entry_sha256)')
        design={'subject':'Five drawer chest'}
        self.row={'path':str(self.original),'image_sha256':sha256(self.original),'design':canonical(design),'design_sha256':digest(design)}
        self.entry={'baseline_attempts':3,'baseline_image_sha256':sha256(self.failed),'mode':'generate','prompt':'new geometry'}
        self.db.execute('INSERT INTO reference_completion_recovery VALUES(?,?,?,?)',
            (self.row['image_sha256'],self.row['design_sha256'],canonical(self.entry),digest(self.entry)))
        self.attempts=[{'image_path':str(self.failed),'image_sha256':sha256(self.failed)}]*3

    def test_one_extra_attempt_without_resetting_history(self):
        self.assertEqual(reference_plan(self.root,self.db,self.row,self.attempts),self.entry)
        self.assertIsNone(reference_plan(self.root,self.db,self.row,self.attempts+self.attempts[:1]))

    def test_changed_failed_image_is_not_admitted(self):
        self.failed.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'baseline changed'):
            reference_plan(self.root,self.db,self.row,self.attempts)

    def test_changed_receipt_is_not_admitted(self):
        self.db.execute("UPDATE reference_completion_recovery SET entry_sha256='wrong'")
        with self.assertRaisesRegex(ValueError,'receipt changed'):
            reference_plan(self.root,self.db,self.row,self.attempts)


class RecipeScopeTest(unittest.TestCase):
    def test_vanity_light_count_is_a_wall_bar_and_never_a_hanging_pendant(self):
        p=recipe({'subject':'Colgan 4-Light Bath Bar','product_class':'Vanity Lighting'})
        self.assertIsNotNone(p)
        self.assertIn('wall-mounted',p['prompt'])
        self.assertIn('horizontal',p['prompt'])
        self.assertNotIn('long cord',p['prompt'])
    def test_unknown_and_mixed_construction_are_not_generalized(self):
        self.assertIsNone(recipe({'profile':'unreviewed-new-type','subject':'cabinet'}))
        self.assertIsNone(recipe({'product_class':'Accent Cabinets','subject':'2 drawer 2 door cabinet'}))

    def test_numeric_specifications_never_enter_the_render_prompt(self):
        result=recipe({'profile':'monitor-riser','subject':'desktop monitor riser','construction':'open space beneath a flat top',
                       'material':'Bamboo','color':'White','dimensions_cm':{'width':46.2,'height':10.1}})
        validate_prompt(result['prompt'])
        self.assertIn(NO_MEASUREMENTS,result['prompt'])
        self.assertNotIn('46.2',result['prompt']);self.assertNotIn('10.1',result['prompt'])


if __name__=='__main__':unittest.main()
