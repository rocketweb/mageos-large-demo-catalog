import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1]/'distribution/acceptance/extract_demo_stock.py'
SPEC = importlib.util.spec_from_file_location('demo_stock', PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DemoStockBackupTest(unittest.TestCase):
    def source(self, payload):
        return ['CREATE TABLE `cataloginventory_stock_item` (',
                '  `item_id` int NOT NULL,', '  `qty` decimal(12,4),',
                '  `low_stock_date` timestamp NULL,', ') ENGINE=InnoDB;',
                'INSERT INTO `cataloginventory_stock_item` VALUES '+payload+';']

    def test_exact_numeric_and_nullable_dates(self):
        self.assertEqual(MODULE.extract(self.source("(1,3.0000,NULL),(2,-1.2500,'2026-09-13 12:30:00')")),
                         [{'item_id': '1', 'qty': '3.0000', 'low_stock_date': None},
                          {'item_id': '2', 'qty': '-1.2500', 'low_stock_date': '2026-09-13 12:30:00'}])

    def test_rejects_unexpected_sql_and_duplicate_rows(self):
        for payload in ["(1,NOW(),NULL)", "(1,2,'arbitrary text')", '(1,2,NULL),(1,3,NULL)', '(1,2)']:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                MODULE.extract(self.source(payload))

    def test_multiline_dump_and_unrelated_binary_text(self):
        lines = self.source('(1,3.0000,NULL)')
        lines[-1:] = ['INSERT INTO `cataloginventory_stock_item` VALUES\n',
                      '(1,3.0000,NULL),\n', '(2,4.0000,NULL);\n']
        lines.insert(0, 'unrelated binary column: \x00\xac')
        self.assertEqual(len(MODULE.extract(lines)), 2)

    def test_truncated_stock_statement_fails_closed(self):
        lines = self.source('(1,3.0000,NULL)')
        lines[-1] = 'INSERT INTO `cataloginventory_stock_item` VALUES\n'
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            MODULE.extract(lines)


if __name__ == '__main__':
    unittest.main()
