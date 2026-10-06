# Dataset card

Synthetic home-and-furniture fixtures for lab testing, derived from Wayfair
WANDS. Prices, inventory, descriptions, dimensions and images are illustrative;
original WANDS search judgments do not qualify ranking on the rewritten catalog.

Release `catalog-2026.10.06` contains **107,815 records**, including 127 named QA
fixtures across all six core product types. The [release guide](PRODUCTION_RELEASE.md)
provides installation, exact runtime acceptance scope and remaining limits.

| Contents | Count |
| --- | ---: |
| Simple / configurable / bundle | 103,720 / 4,001 / 62 |
| Virtual / downloadable / grouped | 14 / 12 / 6 |
| Distinct accepted JPEG contents | 95,401 |
| JPEG files, including reused QA copies | 95,417 |
| Fictional downloadable PDF/ZIP files | 3 |

## Purpose and source

Home-and-furniture test fixtures derived from
[Wayfair WANDS](https://github.com/wayfair/WANDS), pinned at
`3b74dcf4ba29ab8ff3e6a50b5b09fc627cb882b5`. The release manifest records input hashes,
the tooling baseline commit and exact source-file hashes, including uncommitted
candidate changes. It does not claim a clean source tag or a live database export.

Original WANDS has 42,994 products, 480 search queries and 233,448 judgments.
The generated profiles contain rewritten products and additional relationships.
Original query/judgment files are deliberately not bundled with enriched data.
Use the pinned upstream dataset separately for an original-WANDS benchmark.

## What is synthetic

Prices, promotions, inventory quantities and scenarios, lab collections, rewritten
descriptions, variants, bundles and illustrative dimensions are test data. They
are not observed retail offers, manufacturer measurements, availability promises,
fit guarantees, safety certifications or warranties. Synthetic price attributes
retain their recipe metadata. Corrected dimensions are disclosed in descriptions.

Historical source ratings belong to the source products. Generated hidden variants
do not receive those ratings as invented independent customer feedback. No new
customer reviews, customers, orders or personal transaction records are included.

Images are generated illustrations, not manufacturer photographs. Some size-only
variants share images. Some legacy children inherit a family illustration; coverage
counts identify this explicitly. Repaired assortments may still approximate exact
geometry or component appearance. Structured definitions are authoritative.

## Profiles and reproducibility

The current full profile combines the 107,688-record accepted expansion with the
127-product QA suite. September's 5,000-record medium and 53,844-record full
profiles remain immutable historical prereleases. Disabled retired and quarantined
products remain test records. Physical variant illustrations follow their accepted
color/finish; size-only variants may share media. Virtual and downloadable records
may intentionally have no image. All generated-image prompts prohibit displayed
measurements, text, numerals, rulers, logos and annotated packaging. Automated
and human review reduce defects without guaranteeing perfect product geometry.

Archive construction is deterministic for identical files and configuration.
Source image bytes are preserved. Model revisions were not fully recorded for
all historical images; byte-identical model regeneration is not promised.
Per-file hashes verify transport, not correctness or redistribution rights.

The profile is intended for USD on a fresh, dedicated lab installation. Core
search and theme packages are recipient choices. No ranking-improvement claim
from a different corpus is carried into this release.
