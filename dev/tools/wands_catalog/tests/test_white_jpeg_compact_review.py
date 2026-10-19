import copy
import json
from pathlib import Path
import sys
import unittest

from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import white_jpeg_compact_review as compact
import white_jpeg_dark_fast as dark


class CompactReviewTest(unittest.TestCase):
    def setUp(self):
        self.review = {'background': 'studio', 'white_background': True, 'major_product_damage': False,
                       'confidence': .95, 'reason': 'Product intact; backdrop shadow removed.',
                       'regions': ['B']}

    def test_every_numbered_region_must_be_present_and_ordered(self):
        compact.parse(json.dumps(self.review), 1)
        for count, edit in [(2, {}), (1, {'regions': []}), (1, {'regions': ['unknown']})]:
            with self.subTest(count=count, edit=edit), self.assertRaises(ValueError):
                compact.parse(json.dumps({**self.review, **edit}), count)

    def test_major_damage_uncertainty_and_low_confidence_never_pass(self):
        self.assertEqual(compact.choose(self.review, 1)[0], 'white')
        for verdict in ['D','U']:
            value=copy.deepcopy(self.review);value['regions'][0]=verdict
            self.assertEqual(compact.choose(value, 1)[0], 'original')
        for edit in [{'background': 'scene'}, {'major_product_damage': True}, {'white_background': False}, {'confidence': .94}]:
            self.assertEqual(compact.choose({**self.review, **edit}, 1)[0], 'original')

    def test_minor_changes_allowed_and_boolean_confidence_rejected(self):
        self.review['regions'][0] = 'M'
        self.assertEqual(compact.choose(self.review, 1)[0], 'white')
        self.review['confidence'] = True
        with self.assertRaises(ValueError):compact.parse(json.dumps(self.review), 1)

    def test_substantial_material_change_stays_with_the_existing_reviewer(self):
        good={'source_chroma_loss_fraction':.01,'envelope_foreground_loss_fraction':.03}
        self.assertTrue(compact.material_ok(good))
        self.assertFalse(compact.material_ok({**good,'source_chroma_loss_fraction':.06}))
        with self.assertRaises(ValueError):compact.material_ok({**good,'source_chroma_loss_fraction':float('nan')})

    def test_all_crops_share_one_payload_and_native_holds_need_no_model(self):
        image=Image.new('RGB',(768,768),'white')
        regions=[{'kind':'enclosed_whitened_area','crop':[50,50,200,200]} for _ in range(8)]
        query=compact.payload(image,image,{'file':'a','source_sha256':'s','output_sha256':'o'},regions)
        self.assertEqual(sum(c['type']=='image_url'for c in query['messages'][1]['content']),3)
        with self.assertRaises(ValueError):compact.payload(image,image,{'file':'a','source_sha256':'s','output_sha256':'o'},regions+[regions[0]])
        metrics={'retained_pixel_agreement':.85,'native_edge_retention':.99}
        self.assertIn('diffuse',compact.native_hold(metrics,{},[]))
        self.assertIn('eight',compact.native_hold(metrics,{},regions+[regions[0]]))


class DarkProductTest(unittest.TestCase):
    def setUp(self):
        self.source=Image.new('RGB',(256,256),(240,235,225));self.candidate=Image.new('RGB',(256,256),'white')
        for image in [self.source,self.candidate]:ImageDraw.Draw(image).rectangle((55,35,200,225),fill=(20,30,50))
        self.metrics={'border_median_rgb':[240,235,225], 'backdrop_fit_p90':3,'border_edge_fraction':0,
                      'white_border':1,'native_edge_retention':.99,'retained_pixel_agreement':.99}

    def test_dark_solid_product_passes_but_new_internal_white_hole_fails(self):
        self.assertTrue(dark.passes(dark.features(self.source,self.candidate,self.metrics)))
        ImageDraw.Draw(self.candidate).rectangle((100,90,150,150),fill='white')
        self.assertFalse(dark.passes(dark.features(self.source,self.candidate,self.metrics)))

    def test_pale_surface_and_large_dark_erasure_fail(self):
        for image in [self.source,self.candidate]:ImageDraw.Draw(image).rectangle((80,70,180,170),fill=(250,250,250))
        self.assertFalse(dark.passes(dark.features(self.source,self.candidate,self.metrics)))
        ImageDraw.Draw(self.candidate).rectangle((55,35,200,225),fill='white')
        self.assertFalse(dark.passes(dark.features(self.source,self.candidate,self.metrics)))

    def test_glass_room_bedding_and_bad_native_evidence_stay_out(self):
        row={'output_file':'a.jpg'};meta={'classes':['Chairs']}
        self.assertTrue(dark.gate(row,self.metrics,meta))
        self.assertFalse(dark.gate(row,self.metrics,meta,glass_scoped=True))
        for cls in ['Room Bundle','Bedding Sets','Glass Tables','Unknown']:
            self.assertFalse(dark.gate(row,self.metrics,{'classes':[cls]}))
        self.assertFalse(dark.gate(row,{**self.metrics,'native_edge_retention':.6},meta))
        with self.assertRaises(ValueError):dark.gate(row,{**self.metrics,'white_border':float('nan')},meta)


if __name__=='__main__':unittest.main()
