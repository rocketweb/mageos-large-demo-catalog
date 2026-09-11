from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from plan_pilot_media_assignment import choose_target, snapshot_attributes


class MappingTest(unittest.TestCase):
    def test_snapshot_request_includes_option_and_media_attributes(self):
        attrs=snapshot_attributes({'WANDS-X':['wands_finish','wands_piece_count']})
        self.assertTrue({'image','image_label','small_image','small_image_label','thumbnail','thumbnail_label','name','description','lab_sale_unit','wands_finish','wands_piece_count'}<=set(attrs))
        self.assertEqual(attrs,sorted(set(attrs)))

    def test_variant_uses_options_not_historical_sku_words(self):
        product={'sku':'WANDS-030335','kind':'configurable','gallery_target':{'sku':'WANDS-030335-3-PIECES-5B0E','options':{'wands_piece_count':'5 Pieces'}},
                 'child_summary':[{'sku':'WANDS-030335-3-PIECES-5B0E','options':{'wands_piece_count':'5 Pieces'}}]}
        self.assertEqual(choose_target(product,{'wands_piece_count':'5 Pieces'}),'WANDS-030335-3-PIECES-5B0E')
        with self.assertRaises(ValueError):choose_target(product,{'wands_piece_count':'3 Pieces'})
        product['child_summary']=[]
        with self.assertRaises(ValueError):choose_target(product,{'wands_piece_count':'5 Pieces'})

    def test_simple_target_cannot_spill_into_other_sku(self):
        p={'sku':'WANDS-000056','kind':'simple','gallery_target':{'sku':'WANDS-000056','options':{}},'child_summary':[]}
        self.assertEqual(choose_target(p,{}),'WANDS-000056')
        p['gallery_target']['sku']='WANDS-OTHER'
        with self.assertRaises(ValueError):choose_target(p,{})


if __name__=='__main__':unittest.main()
