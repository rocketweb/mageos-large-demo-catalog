"""Approved exclusions must not excuse missing images on healthy products."""
import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_retained_sku_mapping import RetainedSkuMappingTest
import export_expanded_catalog as exporter
import prepare_expansion_deployment as deployment

class QuarantineCoverageTest(RetainedSkuMappingTest):
    def test_quarantined_variant_does_not_block_healthy_shared_file(self):
        self.db.execute('DELETE FROM reference_repairs')
        retained,report=exporter.resolve_retained(self.db,self.base,'policy',excluded={'METAL'})
        self.assertEqual(set(retained),{'LEATHER'})
        self.assertEqual(report['unresolved_retained_briefs'],0)
        self.assertEqual(report['retained_assignments_expected'],1)
        self.assertEqual(report['retained_images_expected'],1)
        self.assertEqual(report['quarantined_retained_assignments'],1)

    def test_excluding_one_shared_variant_does_not_excuse_other_variant(self):
        self.db.execute('DELETE FROM reference_repairs')
        self.db.execute('DELETE FROM references_to_review')
        retained,report=exporter.resolve_retained(self.db,self.base,'policy',excluded={'METAL'})
        self.assertEqual(report['unresolved_retained_briefs'],1)
        self.assertEqual(retained,{})

    def test_disabled_new_product_requires_explicit_quarantine(self):
        rows={'WANDS-SYN-NEW':{'product_online':'2','visibility':'Not Visible Individually'}}
        deployment.check_media_coverage(rows,[],['WANDS-SYN-NEW'],quarantined={'WANDS-SYN-NEW'})
        with self.assertRaises(ValueError):deployment.check_media_coverage(rows,[],['WANDS-SYN-NEW'])

    def test_quarantine_never_excuses_enabled_products(self):
        rows={'WANDS-SYN-NEW':{'product_online':'1','visibility':'Not Visible Individually'}}
        with self.assertRaises(ValueError):deployment.check_media_coverage(rows,[],['WANDS-SYN-NEW'],quarantined={'WANDS-SYN-NEW'})

class ExactScopeTest(unittest.TestCase):
    def setUp(self):
        import catalog_quarantine as q
        from unittest.mock import patch
        from build_expanded_catalog import write_csv
        from prepare_catalog import sha256
        self.q=q;self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.root=Path(self.t.name)
        self.candidate=self.root/'candidate';(self.candidate/'data').mkdir(parents=True);(self.candidate/'manifest.json').write_text('{}')
        row={'sku':'WANDS-SYN-ONE','product_type':'simple','product_online':'1','visibility':'Catalog, Search'}
        write_csv(self.candidate/'data/1-simple.csv',[row])
        for n in ('2-configurable.csv','3-bundle.csv'):write_csv(self.candidate/'data'/n,[])
        self.proposal=self.root/'proposal.csv';self.entries=[{'sku':row['sku'],'product_online_before':'1','product_online_proposed':'2','visibility_before':'Catalog, Search','visibility_proposed':'Not Visible Individually'}]
        write_csv(self.proposal,self.entries)
        for name,value in [('CANDIDATE',sha256(self.candidate/'manifest.json')),('PROPOSAL',sha256(self.proposal))]:
            p=patch.object(q,name,value);p.start();self.addCleanup(p.stop)

    def test_smaller_unapproved_scope_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'scope'):self.q.approved_rows(self.proposal,self.candidate)

    def test_changed_proposal_is_rejected(self):
        self.proposal.write_text(self.proposal.read_text()+'tampering')
        with self.assertRaisesRegex(ValueError,'proposal'):self.q.approved_rows(self.proposal,self.candidate)

    def test_no_policy_leaves_images_required(self):
        self.assertIsNone(self.q.policy(self.root))
        self.assertFalse(self.q.all_quarantined({'skus':['A']},set()))

    def test_healthy_sku_in_shared_job_prevents_skip(self):
        self.assertFalse(self.q.all_quarantined({'skus':['A','B']},{'A'}))
        self.assertTrue(self.q.all_quarantined({'skus':['A']},{'A'}))
