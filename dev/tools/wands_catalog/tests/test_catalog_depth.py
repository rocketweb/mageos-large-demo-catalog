import copy
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from catalog_depth import extract_specs, length_cm, select_pilot, recommend, gallery_briefs, rating_proposal, render_review, validate_records, curated_collections
from build_realism_review import DEPARTMENTS
from synthetic_dimensions import add_dimensions, LABEL


def source(pid="1", features="", cls="Sofas", dept="Furniture"):
    return {"product_id": pid, "product_name": "Example sofa", "product_class": cls,
            "category hierarchy": dept + " / " + cls, "product_features": features}


def product(sku="A", cls="Sofas", style="Modern", dept="Furniture", price=100):
    return {"sku": sku, "source_product_id": sku, "source_class": cls, "department": dept,
            "name": sku, "price": price, "salable": True, "specifications": {"lab_spec_style": {"value": style, "synthetic": False}},
            "variant_options": {}, "kind": "simple"}


class CatalogDepthTest(unittest.TestCase):
    def test_explicit_units_and_fraction_conversion(self):
        for value, expected in [('12 in',30.48),('1 ft',30.48),('300 mm',30),('1 m',100),('1 1/2 inches',3.81),('2\u2032 6\u2033',76.2)]:
            self.assertAlmostEqual(length_cm(value), expected)

    def test_ambiguous_measurements_never_infer_units(self):
        for value in ['42','5-10 in','12 x 24 in','-2 cm','nan','0 in','12 in approx','12.5.4 in']:
            with self.assertRaises(ValueError): length_cm(value)

    def test_aliases_normalized_before_conflict_check(self):
        facts, withheld=extract_specs(source(features='Width: 12 in|Overall Width - Side to Side: 30.48 cm'))
        self.assertEqual(facts['lab_spec_width_cm']['value'],30.48)
        self.assertFalse(withheld)

    def test_conflict_and_unknown_are_withheld(self):
        facts, withheld=extract_specs(source(features='Width: 12 in|Width: 15 in|Height: 42|Frame Material: Mystery|Style: Modern'))
        self.assertEqual(set(facts),{'lab_spec_style'})
        self.assertEqual(len(withheld),3)

    def test_dimension_units_can_be_grounded_in_matching_source_title(self):
        row=source(features='Width: 84'); row['product_name']='Example 84" Wide Sofa'
        facts,_=extract_specs(row)
        self.assertEqual(facts['lab_spec_width_cm']['value'],213.36)
        self.assertTrue(any(e['key']=='product_name' for e in facts['lab_spec_width_cm']['evidence']))

    def test_source_title_does_not_resolve_conflicting_measurements(self):
        row=source(features='Width: 84|Width: 90'); row['product_name']='Example 84" Wide Sofa'
        facts,flags=extract_specs(row)
        self.assertNotIn('lab_spec_width_cm',facts)
        self.assertTrue(flags)

    def test_title_measurements_require_named_axis(self):
        row=source(features=''); row['product_name']='Example 84" Sofa'
        facts,_=extract_specs(row)
        self.assertNotIn('lab_spec_width_cm',facts)

    def test_parent_and_children_do_not_inherit_variable_dimensions(self):
        row=source(features='Width: 84 in|Seat Depth: 22 in|Frame Material: Solid Wood')
        for options in [None, {'wands_size':'Large'}]:
            facts, withheld=extract_specs(row,{'wands_size'},options)
            self.assertNotIn('lab_spec_width_cm',facts)
            self.assertNotIn('lab_spec_seat_depth_cm',facts)
            self.assertEqual(facts['lab_spec_frame_material']['value'],'Solid Wood')
            self.assertTrue(withheld)

    def test_material_options_are_synthetic_not_original_facts(self):
        row=source(features='Material: Cotton|Upholstery Material: Cotton')
        facts,_=extract_specs(row,{'wands_material'},{'wands_material':'Velvet'})
        self.assertEqual(facts['lab_spec_material']['value'],'Velvet')
        self.assertTrue(facts['lab_spec_material']['synthetic'])
        self.assertNotIn('lab_spec_upholstery',facts)

    def test_unsafe_claims_are_not_promoted(self):
        facts,_=extract_specs(source(features='Material: certified non-toxic cotton|Warranty: Lifetime|Care: safe for infant sleep'))
        self.assertFalse(facts)

    def test_balanced_sample_is_reproducible_without_input_order_bias(self):
        rows=[source(str(i),cls='Sofas' if i%2 else 'Chairs',dept='Furniture' if i<10 else 'Rugs') for i in range(20)]
        first=select_pilot(rows,{},6,['Furniture','Rugs'])
        self.assertEqual([r['product_id'] for r in first],[r['product_id'] for r in select_pilot(rows[::-1],{},6,['Furniture','Rugs'])])
        self.assertEqual(sum(r['category hierarchy'].startswith('Rugs') for r in first),3)

    def test_sample_refuses_unfillable_department_quota(self):
        with self.assertRaises(ValueError): select_pilot([source()],{},3,['Furniture','Rugs'])

    def test_sampling_prefers_configurable_roots_across_classes(self):
        rows=[source(str(i),cls='Sofas' if i<5 else 'Tables') for i in range(10)]
        selected=select_pilot(rows,{'0':{},'1':{},'2':{},'3':{}},4,['Furniture'])
        self.assertEqual({r['product_id'] for r in selected},{'0','1','2','3'})

    def test_recommendations_do_not_cross_adult_child_use(self):
        current=product('A','Desks'); child=product('B','Kids Desks|Table Lamps',dept='Baby & Kids')
        self.assertFalse(recommend(current,[child])['complements'])

    def test_recommendations_are_explainable_and_never_self_links(self):
        a=product(); b=product('B'); lamp=product('L','Table Lamps',dept='Lighting',price=30)
        wrong=product('X','Patio Sofas',dept='Outdoor'); unavailable=product('Z'); unavailable['salable']=False
        picks=recommend(a,[a,b,lamp,wrong,unavailable])
        self.assertEqual([r['target_sku'] for r in picks['alternatives']],['B'])
        self.assertEqual([r['target_sku'] for r in picks['complements']],['L'])
        self.assertTrue(all(r['review_required'] for rows in picks.values() for r in rows))

    def test_no_matching_evidence_means_no_recommendation(self):
        a=product(); b=product('B',style='Rustic')
        self.assertEqual(recommend(a,[b]),{'alternatives':[],'complements':[]})

    def test_unknown_and_synthetic_style_do_not_prove_coordination(self):
        a=product(); b=product('B'); b['specifications']['lab_spec_style']['synthetic']=True
        self.assertFalse(recommend(a,[b])['alternatives'])

    def test_gallery_requires_reference_and_dimension_evidence(self):
        p=product(); p.update(name='Example',reference=None)
        jobs=gallery_briefs(p)
        self.assertEqual(len(jobs),5)
        self.assertTrue(all(not j['executable'] for j in jobs))
        dimension=next(j for j in jobs if j['view']=='dimensions')
        self.assertIn('missing_explicit_dimensions',dimension['blockers'])
        self.assertTrue(all('missing_reference' in j['blockers'] for j in jobs))

    def test_synthetic_gallery_labels_scale_without_claiming_reference_approval(self):
        p=product(cls='Accent Chairs'); p.update(name='Armchair',reference=None,axis_codes=[])
        p=add_dimensions(p)
        jobs=gallery_briefs(p)
        diagram=next(j for j in jobs if j['view']=='dimensions')
        room=next(j for j in jobs if j['view']=='room')
        self.assertEqual(diagram['dimension_basis'],'synthetic_lab_design')
        self.assertIn(LABEL,diagram['prompt'])
        self.assertTrue(diagram['dimension_provenance'])
        self.assertNotIn('missing_explicit_dimensions',diagram['blockers'])
        self.assertNotIn('scale_unverified',room['blockers'])
        self.assertTrue(all('reference_identity_and_options_unapproved' in j['blockers'] and not j['executable'] for j in jobs))

    def test_component_gallery_does_not_invent_set_wide_dimensions(self):
        p=product(cls='Kitchen Gadgets'); p.update(name='Mortar And Pestle',reference=None,axis_codes=[])
        p=add_dimensions(p)
        diagram=next(j for j in gallery_briefs(p) if j['view']=='dimensions')
        self.assertEqual(diagram['dimension_basis'],'synthetic_lab_component_design')
        self.assertEqual(diagram['dimensions_cm'],{})
        self.assertEqual(len(diagram['component_dimensions']),2)
        self.assertNotIn('missing_explicit_dimensions',diagram['blockers'])
        self.assertIn('not an installed span',diagram['prompt'])
        self.assertIn(LABEL,diagram['prompt'])
        self.assertFalse(diagram['executable'])

    def test_source_ratings_do_not_create_fake_reviews_or_child_inheritance(self):
        p={'wands_average_rating':'4.5','wands_review_count':'41'}
        value=rating_proposal(p,True)
        self.assertEqual(value['count'],41)
        self.assertTrue(value['source_product_only'])
        self.assertEqual(value['created_reviews'],0)
        for rating,count in [('6','1'),('nan','4'),('4.5','-1'),('4.5','1.5')]:
            self.assertIsNone(rating_proposal({'wands_average_rating':rating,'wands_review_count':count},False))

    def test_review_escapes_untrusted_names(self):
        row=product('<script>alert(1)</script>'); row.update(reference=None,withheld=[],axes=[],rating=None)
        page=render_review([row],{'products':1},[])
        self.assertNotIn('<script>alert(1)</script>',page)
        self.assertIn('&lt;script&gt;',page)

    def test_validator_rejects_duplicate_ids_and_orphan_links(self):
        a=product()
        with self.assertRaises(ValueError): validate_records([a,a],[],{'A'})
        with self.assertRaises(ValueError): validate_records([a],[{'sku':'A','alternatives':[{'target_sku':'missing'}],'complements':[]}],{'A'})

    def test_small_space_collection_requires_real_measurement(self):
        unknown=product('A','End Tables'); measured=product('B','End Tables')
        measured['specifications']['lab_spec_width_cm']={'value':60,'synthetic':False}
        result=next(c for c in curated_collections([unknown,measured]) if c['id']=='small-space-tables')
        self.assertEqual([r['sku'] for r in result['candidates']],['B'])

    def fixture(self, root):
        raw=[source(str(i*2+n),features='Style: Modern|Width: 40 cm',dept=dept) for i,dept in enumerate(DEPARTMENTS) for n in range(2)]
        prepared=[{'wands_product_id':r['product_id'],'sku':'WANDS-'+r['product_id'].zfill(6),'name':'Example',
                   'product_type':'simple','url_key':'product-'+r['product_id'],'wands_average_rating':'4.5','wands_review_count':'10'} for r in raw]
        patches=[{**r,'price':'100','special_price':'','is_in_stock':'1'} for r in prepared]
        for name,rows,delimiter in [('source.tsv',raw,'\t'),('prepared.csv',prepared,','),('products.patch.csv',patches,',')]:
            with (root/name).open('w',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(rows[0]),delimiter=delimiter)
                writer.writeheader(); writer.writerows(rows)
        (root/'configurable-families.jsonl').write_text('')
        (root/'queries.all.jsonl').write_text('{"query_id":"original","query":"sofa"}\n')
        (root/'qrels.all.trec').write_text('original 0 1 2\n')
        fingerprint=lambda name:hashlib.sha256((root/name).read_bytes()).hexdigest()
        (root/'manifest.json').write_text(json.dumps({'outputs':{'products.patch.csv':fingerprint('products.patch.csv')},
            'inputs':{key:{'sha256':fingerprint(name)} for key,name in [('source','source.tsv'),('prepared','prepared.csv'),('families','configurable-families.jsonl')]}}))
        return [sys.executable,str(Path(__file__).resolve().parents[1]/'catalog_depth.py'),
                '--source-products',str(root/'source.tsv'),'--prepared-products',str(root/'prepared.csv'),
                '--merchandising-dir',str(root),'--realism-packet',str(root),'--media-dir',str(root),
                '--benchmark-dir',str(root),'--count','20','--output-dir']

    def test_cli_quiet_reproducible_and_preserves_benchmark_and_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); command=self.fixture(root)
            before={p.name:p.read_bytes() for p in root.iterdir()}
            for name in ['first','second']:
                result=subprocess.run(command+[str(root/name)],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,(root/(name+'.log')).read_text())
                self.assertEqual(result.stdout,''); self.assertEqual(result.stderr,'')
            for path in (root/'first').iterdir():
                self.assertEqual(path.read_bytes(),(root/'second'/path.name).read_bytes(),path.name)
            self.assertTrue(all((root/name).read_bytes()==value for name,value in before.items()))
            result=subprocess.run(command+[str(root/'first')],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(result.stdout+result.stderr,'')

    def test_packet_hash_mismatch_fails_without_publishing(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); command=self.fixture(root)
            with (root/'products.patch.csv').open('a') as stream: stream.write('\n')
            result=subprocess.run(command+[str(root/'rejected')],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse((root/'rejected').exists())

    def test_synthetic_opt_in_has_separate_labeled_export_and_deterministic_packet(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); command=self.fixture(root)
            # Fixture has an implausibly narrow source sofa. Use a supported
            # desk class with a source height; retain all lineage checks.
            with (root/'source.tsv').open() as stream:
                rows=list(csv.DictReader(stream,delimiter='\t'))
            for row in rows:
                row['product_class']='Kids Desks'; row['product_features']='Style: Modern|Height: 65 cm'
            with (root/'source.tsv').open('w',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(rows[0]),delimiter='\t'); writer.writeheader(); writer.writerows(rows)
            manifest=json.loads((root/'manifest.json').read_text())
            manifest['inputs']['source']['sha256']=hashlib.sha256((root/'source.tsv').read_bytes()).hexdigest()
            (root/'manifest.json').write_text(json.dumps(manifest))
            for name in ['first','second']:
                result=subprocess.run(command+[str(root/name),'--synthetic-dimensions'],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout+result.stderr,'')
            for path in (root/'first').iterdir():
                self.assertEqual(path.read_bytes(),(root/'second'/path.name).read_bytes(),path.name)
            packet=root/'first'
            with (packet/'specifications.proposed.csv').open() as stream:
                proposed=list(csv.DictReader(stream))
            self.assertTrue(all(r['lab_spec_height_cm']=='65.0' and r['lab_spec_width_cm']=='' for r in proposed))
            with (packet/'synthetic-dimensions.proposed.csv').open() as stream:
                synthetic=list(csv.DictReader(stream))
            self.assertEqual(len(synthetic),40)
            self.assertTrue(all(r['display_label']==LABEL and r['rule_version'] and r['evidence_json'] for r in synthetic))
            summary=json.loads((packet/'manifest.json').read_text())
            self.assertTrue(summary['synthetic_dimensions_enabled'])
            self.assertEqual(summary['synthetic_dimension_facts'],40)
            self.assertIn(LABEL,(packet/'review.html').read_text())

    def test_component_csv_keeps_component_identity_and_is_reproducible(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); command=self.fixture(root)
            for filename,delimiter in [('source.tsv','\t'),('prepared.csv',','),('products.patch.csv',',')]:
                with (root/filename).open() as stream:
                    rows=list(csv.DictReader(stream,delimiter=delimiter))
                for row in rows:
                    if filename=='source.tsv':
                        row.update(product_class='Kitchen Gadgets',product_name='Mortar And Pestle',product_features='Style: Modern')
                    else:
                        row['name']='Mortar And Pestle'
                with (root/filename).open('w',newline='') as stream:
                    writer=csv.DictWriter(stream,fieldnames=list(rows[0]),delimiter=delimiter);writer.writeheader();writer.writerows(rows)
            manifest=json.loads((root/'manifest.json').read_text())
            for key,filename in [('source','source.tsv'),('prepared','prepared.csv')]:
                manifest['inputs'][key]['sha256']=hashlib.sha256((root/filename).read_bytes()).hexdigest()
            manifest['outputs']['products.patch.csv']=hashlib.sha256((root/'products.patch.csv').read_bytes()).hexdigest()
            (root/'manifest.json').write_text(json.dumps(manifest))
            for name in ['first','second']:
                result=subprocess.run(command+[str(root/name),'--synthetic-dimensions'],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,(root/(name+'.log')).read_text())
                self.assertEqual(result.stdout+result.stderr,'')
            for path in (root/'first').iterdir():
                self.assertEqual(path.read_bytes(),(root/'second'/path.name).read_bytes(),path.name)
            with (root/'first'/'component-dimensions.proposed.csv').open() as stream:
                rows=list(csv.DictReader(stream))
            self.assertEqual(len(rows),120)
            self.assertEqual({r['component_id'] for r in rows},{'mortar','pestle'})
            self.assertTrue(all(r['quantity']=='1' and r['display_label']==LABEL and r['composition_evidence_json'] for r in rows))
            with (root/'first'/'specifications.proposed.csv').open() as stream:
                self.assertTrue(all(r['lab_spec_width_cm']=='' for r in csv.DictReader(stream)))


if __name__=='__main__': unittest.main()
