import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from catalog_depth import gallery_briefs
from prepare_catalog import transform
from run_catalog_media_pilot import compile_prompt


class MeasurementPolicyRegressionTest(unittest.TestCase):
    def test_source_title_measurements_do_not_enter_image_prompt(self):
        source = {'product_id': '1', 'product_name': 'Oak 48 in. W x 24 in. D Table',
                  'product_class': 'Tables', 'category hierarchy': 'Furniture / Tables',
                  'product_description': '', 'product_features': 'color:oak',
                  'average_rating': '', 'review_count': ''}
        product, image = transform(source)
        self.assertIn('48', product['name'])
        self.assertNotIn('48', image['prompt'])
        self.assertNotIn('24', image['prompt'])
        self.assertIn('No visible measurements', image['prompt'])

    def test_gallery_has_no_dimension_diagram_or_numeric_measurement_prompt(self):
        record = {'sku': 'WANDS-000001', 'source_product_id': '1', 'name': 'Table 120 cm',
                  'variant_options': {}, 'specifications': {
                      'lab_spec_width_cm': {'value': 120, 'synthetic': True},
                      'lab_spec_height_cm': {'value': 75, 'synthetic': True}},
                  'reference': None}
        jobs = gallery_briefs(record)
        self.assertNotIn('dimensions', [job['view'] for job in jobs])
        for job in jobs:
            self.assertNotIn('120', job['prompt'])
            self.assertNotIn('75', job['prompt'])
            self.assertIn('No visible measurements', job['prompt'])
            self.assertEqual(job['dimensions_cm']['lab_spec_width_cm'], 120)

    def test_pilot_preserves_component_count_but_omits_measurements(self):
        case = {'acceptance_contract': {'product_name': 'Flatware', 'selected_options': {},
                    'sale_unit': 'Complete assortment', 'specifications': {},
                    'dimensions_cm': {}, 'components': [
                        {'quantity': 8, 'label': 'Dinner fork', 'dimensions_cm': {'lab_spec_length_cm': 20}}]},
                'pilot_case': {'framing': 'Show the complete assortment'}}
        prompt = compile_prompt(case)
        self.assertIn('8 x Dinner fork', prompt)
        self.assertNotIn('20cm', prompt)
        self.assertIn('No visible measurements', prompt)


if __name__ == '__main__':
    unittest.main()
