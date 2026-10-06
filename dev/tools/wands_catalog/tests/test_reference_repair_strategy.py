import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from repair_expansion_references import repair_strategy
from image_policy import validate_prompt


class ReferenceRepairStrategyTest(unittest.TestCase):
    def test_confirmed_count_failure_generates_a_new_structure_even_when_general_flags_pass(self):
        row=self.row()
        q=json.loads(row['review']);q['component_review']={'confidence':.98,'expected':{'drawer_fronts':9},'drawer_fronts':3};row['review']=json.dumps(q)
        self.assertEqual(repair_strategy(row,[])[0],'generate')

    def test_shelf_quantity_gets_a_visible_layout_instruction(self):
        row=self.row(piece_count_matches=False)
        row['design']=json.dumps({'subject':'4 Shelf Wire Shelving Unit','product_class':'Shelving & Racks','color':'','material':'Metal'})
        mode,prompt=repair_strategy(row,[])
        self.assertEqual(mode,'generate')
        self.assertIn('exactly four',prompt)
        self.assertIn('horizontal',prompt)

    def test_explicit_lighting_count_gets_structural_instructions_instead_of_only_a_title(self):
        row=self.row(piece_count_matches=False)
        row['design']=json.dumps({'subject':'Lyra 16-In Chandelier - 1 Light','product_class':'Chandeliers','color':'Brass','material':'Metal'})
        mode,prompt=repair_strategy(row,[])
        self.assertEqual(mode,'generate')
        self.assertIn('One central bulb only',prompt)
        self.assertIn('no side arms',prompt)
        self.assertIn('Lyra',prompt)
        self.assertNotIn('16-In',prompt)

    def row(self, **flags):
        return {'design': json.dumps({'subject': 'Delpha 9 Drawer Standard Dresser - 36 in',
                                     'product_class': 'Dressers & Chests', 'color': 'Brass', 'material': 'Solid Wood'}),
                'review': json.dumps({'decision': 'rejected', 'vision': {
                    'geometry_defects': False, 'piece_count_matches': True, 'product_matches': True, **flags}})}

    def test_measurement_only_defect_preserves_product_reference(self):
        mode, prompt = repair_strategy(self.row(visible_measurements=True), [])
        self.assertEqual(mode, 'edit')
        validate_prompt(prompt)
        self.assertNotIn('36 in', prompt)

    def test_wrong_components_do_not_reuse_disproved_silhouette(self):
        mode, prompt = repair_strategy(self.row(piece_count_matches=False), [])
        self.assertEqual(mode, 'generate')
        self.assertIn('three horizontal rows and three vertical columns', prompt)
        validate_prompt(prompt)

    def test_failed_identity_edit_changes_strategy(self):
        row = self.row()
        prior = self.row(product_matches=False)
        mode, prompt = repair_strategy(row, [{'review': prior['review']}])
        self.assertEqual(mode, 'generate')
        self.assertIn('Dressers & Chests', prompt)

    def test_deformed_product_uses_new_render(self):
        self.assertEqual(repair_strategy(self.row(geometry_defects=True), [])[0], 'generate')


if __name__ == '__main__':
    unittest.main()
