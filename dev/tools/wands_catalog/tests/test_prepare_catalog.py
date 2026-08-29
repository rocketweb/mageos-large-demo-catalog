from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prepare_catalog import PRICE_VERSION, estimated_price, transform


class PrepareCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.row = {
            "product_id": "42",
            "product_name": "solid wood platform bed",
            "product_class": "Beds",
            "category hierarchy": "Furniture / Bedroom Furniture / Beds",
            "product_description": "A solid acacia platform bed for a modern bedroom.",
            "product_features": "overallwidth-sidetoside:64|framematerial : solid wood|woodspecies : acacia|color : caramel|overallproductweight:80",
            "rating_count": "25",
            "average_rating": "4.5",
            "review_count": "20",
        }

    def test_price_is_deterministic_and_retail_rounded(self) -> None:
        first = estimated_price(self.row)
        second = estimated_price(self.row)
        self.assertEqual(first, second)
        self.assertGreaterEqual(first, 45.0)
        self.assertLessEqual(first, 4500.0)
        self.assertEqual(round(first % 1, 2), 0.99)

    def test_transform_preserves_provenance_and_store_assignment(self) -> None:
        product, prompt = transform(self.row)
        self.assertEqual(product["sku"], "WANDS-000042")
        self.assertEqual(product["product_websites"], "wands")
        self.assertEqual(product["lab_price_version"], PRICE_VERSION)
        self.assertEqual(product["lab_price_synthetic"], "Yes")
        self.assertTrue(product["categories"].startswith("WANDS Catalog/Furniture/"))
        self.assertIn("No visible text", prompt["prompt"])
        self.assertEqual(prompt["output_file"], "WANDS-000042.jpg")

    def test_transform_bounds_name_to_magento_attribute_limit(self) -> None:
        self.row["product_name"] = "Very Long Product " * 30

        product, _ = transform(self.row)

        self.assertLessEqual(len(product["name"]), 255)

    def test_department_name_does_not_override_product_specific_price(self) -> None:
        self.row.update(
            {
                "product_name": "Vienna Body Pillow Case",
                "product_class": "Sheets And Sheet Sets",
                "category hierarchy": "Bed & Bath / Bedding / Sheets & Pillowcases",
                "product_features": "producttype:pillowcase|color:gray",
            }
        )

        price = estimated_price(self.row)

        self.assertGreaterEqual(price, 5.0)
        self.assertLess(price, 100.0)


if __name__ == "__main__":
    unittest.main()
