import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from authorized_completion import construction_prompt
from image_policy import validate_prompt


class CompletionSaleUnitsTest(unittest.TestCase):
    def prompt(self, subject, category, issue='The image shows a whole bed instead of the sale item.'):
        design={'subject':subject,'product_class':category,'material':'','color':'',
                'construction':'Existing synthetic catalog reference; inspect its visible construction and exact sale unit.'}
        original=dict(design)
        prompt=construction_prompt(design,{'vision':{'issues':[issue]}},17)
        self.assertEqual(design,original)
        validate_prompt(prompt)
        return prompt

    def test_pillowcase_pair_is_not_a_complete_bed(self):
        p=self.prompt('Warrenville 3-Line Embroidery 2-Piece Microfiber Pillowcase','Sheets And Sheet Sets')
        self.assertIn('exactly two separate fabric pillowcases',p)
        self.assertNotIn('The image shows a whole bed',p)

    def test_furniture_cushion_is_a_separate_sale_item(self):
        self.assertIn('standalone padded fabric seat cushion',self.prompt('Indoor/Outdoor Dining Chair Cushion','Furniture Cushions'))

    def test_cardboard_cutout_has_a_flat_printed_surface(self):
        self.assertIn('flat printed cardboard silhouette',self.prompt('Star Wars Han Solo In Carbonite Life Size Cardboard Cutout','Life Size Cutouts|Licensed Products'))

    def test_led_strip_uses_positive_geometry_not_the_rejected_puck(self):
        p=self.prompt('Rgb Smd Led Waterproof Flexible Strip + Ir Remote','Under Cabinet Lighting','The image shows a circular puck device instead of a flexible strip.')
        self.assertIn('long narrow flexible ribbon',p)
        self.assertNotIn('circular puck device',p)
        self.assertIn('plain unmarked remote',p)

    def test_five_canvas_panels_are_separately_visible(self):
        self.assertIn('exactly five separate canvas panels',self.prompt('Paris Eiffel Tower 5 Piece Wall Art On Wrapped Canvas Set','Wall Art'))

    def test_four_table_set_has_four_complete_tables(self):
        p=self.prompt('Millis 4 Piece Coffee Table Set','Living Room Table Sets')
        self.assertIn('exactly four complete separate tables',p)
        self.assertIn('own tabletop and complete supports',p)

    def test_over_toilet_storage_uses_open_lower_gap(self):
        self.assertIn('two tall side supports with a large open lower gap',self.prompt('Valeria Over-The-Toilet Storage','Bathroom Storage'))

    def test_bread_knife_has_an_explicit_serrated_blade(self):
        self.assertIn('elongated serrated stainless steel blade',self.prompt('A Cut Above Pro Stainless Bread Knife','Open Stock Knives And Kitchen Scissors'))

    def test_widespread_faucet_includes_separate_handles_and_drain(self):
        p=self.prompt('Dryden Widespread Bathroom Faucet With Drain Assembly','Bathroom Sink Faucets')
        self.assertIn('one central spout and two separate side handles',p)
        self.assertIn('separate drain assembly',p)

    def test_appliance_pair_is_two_bodies_and_single_top_loader_keeps_top_door(self):
        self.assertIn('exactly two complete separate appliance bodies',self.prompt('Top Load Washer And Electric Dryer','Washer And Dryer Sets'))
        self.assertIn('top-loading washing machine with a hinged lid',self.prompt('Farberware Professional Top Load Washer','Washing Machines'))

    def test_unmatched_product_keeps_existing_diagnostic_behavior(self):
        p=self.prompt('Plain Glass Bowl','Glassware & Barware','The required glass rim is missing.')
        self.assertIn('required glass rim is missing',p)

    def test_relevant_manual_structure_is_not_discarded_with_wrong_object_diagnostics(self):
        p=self.prompt('White Top Load Washer','Washing Machines','The lid is missing its handle.')
        self.assertIn('lid is missing its handle',p)


if __name__=='__main__':unittest.main()
