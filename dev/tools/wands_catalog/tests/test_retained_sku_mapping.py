import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_expanded_catalog import canonical, digest, write_csv
from bulk_expansion_images import reference_design
from prepare_catalog import sha256
import export_expanded_catalog as exporter
import repair_expansion_references as repairs


class RetainedSkuMappingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); (self.base/'data').mkdir()
        self.original = self.base/'shared.jpg'; self.original.write_bytes(b'original leather chair')
        self.metal = self.base/'metal.jpg'; self.metal.write_bytes(b'corrected metal chair')
        self.rows = [dict(sku=sku, name='Chair - Black, '+material, lab_spec_material=material,
                          color='Black', wands_product_class='Dining Chairs')
                     for sku, material in [('LEATHER', 'Leather'), ('METAL', 'Metal')]]
        for name in ('1-simple.csv', '2-configurable.csv', '3-bundle.csv'):
            write_csv(self.base/'data'/name, self.rows if name=='1-simple.csv' else [])
        (self.base/'data/media-lineage.json').write_text(canonical({'assignments':{r['sku']:{'file':'shared.jpg'} for r in self.rows}}))
        (self.base/'data/media-inventory.json').write_text(canonical({'shared.jpg':{'sha256':sha256(self.original)}}))
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;self.addCleanup(self.db.close)
        self.db.executescript('CREATE TABLE references_to_review(image_sha256,design_sha256,path,design,review,PRIMARY KEY(image_sha256,design_sha256)); CREATE TABLE reference_repairs(original_sha256,design_sha256,attempt,image_path,image_sha256,review);')
        for row in self.rows:
            design=reference_design(row);dh=digest(design)
            review={'decision':'accepted' if row['sku']=='LEATHER' else 'rejected','image_sha256':sha256(self.original),'design_sha256':dh,'review_identity':'policy'}
            self.db.execute('INSERT INTO references_to_review VALUES(?,?,?,?,?)',(sha256(self.original),dh,str(self.original),canonical(design),canonical(review)))
            if row['sku']=='METAL':
                review={**review,'decision':'accepted','image_sha256':sha256(self.metal)}
                self.db.execute('INSERT INTO reference_repairs VALUES(?,?,1,?,?,?)',(sha256(self.original),dh,str(self.metal),sha256(self.metal),canonical(review)))

    def test_distinct_variants_receive_their_own_accepted_replacement(self):
        retained,report=exporter.resolve_retained(self.db,self.base,'policy')
        self.assertEqual(retained,{'LEATHER':self.original,'METAL':self.metal})
        self.assertEqual(report['unresolved_retained_briefs'],0)
        self.assertEqual(report['retained_images_resolved'],1)
        self.assertEqual(report['retained_assignments_resolved'],2)
        self.assertEqual(report['retained_conflicts'],[])

    def test_missing_variant_brief_blocks_export_even_if_shared_image_passes(self):
        self.db.execute('DELETE FROM references_to_review WHERE design_sha256=?',(digest(reference_design(self.rows[1])),))
        retained,report=exporter.resolve_retained(self.db,self.base,'policy')
        self.assertEqual(set(retained),{'LEATHER'})
        self.assertEqual(report['unregistered_retained_briefs'],1)
        self.assertEqual(report['unresolved_retained_briefs'],1)
        self.assertEqual(report['retained_images_resolved'],0)

    def test_audit_registers_every_distinct_brief_for_a_shared_file(self):
        self.db.execute('DELETE FROM references_to_review')
        self.db.commit()
        # register owns its connection; use a file-backed fixture for reopening.
        path=self.base/'registration.sqlite'
        with sqlite3.connect(path) as copy:self.db.backup(copy)
        def connect(_):
            db=sqlite3.connect(path);db.row_factory=sqlite3.Row;return db
        with patch.object(repairs,'descriptor',return_value={'baseline':str(self.base)}),patch.object(repairs,'connect',side_effect=connect),patch.object(repairs,'status',return_value={}):
            repairs.register(self.base)
        with sqlite3.connect(path) as check:
            self.assertEqual(check.execute('SELECT count(*) FROM references_to_review').fetchone()[0],2)


if __name__=='__main__':unittest.main()
