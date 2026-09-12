# Mage-OS compatibility evidence

Candidate `2026.09.11-rc2` was tested on a fresh, isolated Mage-OS 3.5.0 instance
with PHP 8.4.25, MariaDB 11.4, OpenSearch 3.1.0 and the stock Luma theme.
The starter and full profiles were installed into separate empty databases.
This is an internal acceptance result, not an official Mage-OS certification.

| Check | Starter | Full |
| --- | ---: | ---: |
| Product records | 27 | 53,844 |
| Configurable parents | 3 | 1,995 |
| Bundles | 1 | 50 |
| Configurable links | 10 | 10,736 |
| Bundle options / selections | 4 / 12 | 200 / 600 |
| Verified image roles | 81 | 161,472 |
| Data/media assertions passed | 303 | 616,053 |
| Data/media discrepancies | 0 | 0 |

The full native import reported zero invalid rows and zero errors in all four
phases. All 11 indexes were Ready. Browser checks covered size/color selection,
selected-variant cart addition, color-specific images, bundle price changes,
an out-of-stock product without a purchase button, search results and a mobile
bundle view. No order was placed. This is not a checkout/payment test or a search
ranking-improvement study.

The full profile retains 64 disabled legacy variants, 20 disabled records without
media, and 2,010 children using inherited family illustrations. Every enabled
product has media. Synthetic pictures are not exact product-geometry evidence.

These results apply to the rc2 manifest pins:

```text
starter 42bd8400415204b8bc6b8f5ed5cf8adb8156185eca92ff156cd54285bb68b40f
full    9bf76000f3de8816459638ba2f396af805eaaa83c504886000e1b3c32adcf19d
```

Later builds require their own artifact verification and a documented comparison
before inheriting this acceptance. No Mage-OS 3.4 or clean-install Hyvä result is
claimed. Interrupted-import recovery and existing-store update support remain
unimplemented. Installation is restricted to a dedicated empty lab, with an
empty-baseline backup retained for retry.
