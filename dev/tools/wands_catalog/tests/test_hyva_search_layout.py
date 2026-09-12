"""Search defaults must be present before the collection initializes its toolbar."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


class HyvaSearchLayoutTest(unittest.TestCase):
    def test_search_defaults_are_constructor_data_not_late_layout_actions(self):
        root = Path(__file__).resolve().parents[4]
        layout = root / 'app/code/RocketWeb/LabCatalog/view/frontend/layout/hyva_catalogsearch_result_index.xml'
        page = ET.parse(layout).getroot()
        block = page.find("./body/referenceBlock[@name='search_result_list']")
        args = {arg.attrib['name']: arg for arg in block.findall('./arguments/argument')}
        self.assertEqual(args['default_sort_by'].text, 'relevance')
        self.assertEqual(args['sort_by'].text, 'relevance')
        self.assertEqual(args['default_direction'].text, 'desc')
        self.assertEqual({item.attrib['name'] for item in args['available_orders']},
                         {'name', 'price', 'relevance'})
        self.assertIsNone(block.find('action'))
        toolbar = page.find("./body/referenceBlock[@name='product_list_toolbar']")
        self.assertEqual(toolbar.find("./action[@method='setDefaultOrder']/argument").text, 'relevance')
        self.assertEqual(toolbar.find("./action[@method='setDefaultDirection']/argument").text, 'desc')
        self.assertEqual({arg.text for arg in toolbar.findall("./action[@method='unsetData']/argument")},
                         {'_current_grid_order', '_current_grid_direction'})
        # Do not pin a current order: native request-driven Price/Name choices must still work.
        self.assertIsNone(toolbar.find("./arguments/argument[@name='_current_grid_order']"))


if __name__ == '__main__':
    unittest.main()
