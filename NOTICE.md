# Licenses and attribution

The root [MIT license](LICENSE) covers Rocket Web's catalog module, tooling,
documentation and authored catalog additions. It does not replace the separate
licenses or notices below. Preserve the applicable notices when redistributing.

| Material | Terms and source |
| --- | --- |
| Rocket Web catalog code and authored data | [MIT](LICENSE); copies also accompany the [module](app/code/RocketWeb/LabCatalog/LICENSE.txt) and [tooling](dev/tools/wands_catalog/LICENSE.txt). |
| Original WANDS material | [Upstream MIT notice](dev/tools/wands_catalog/distribution/WANDS-LICENSE.txt), copyright 2021 ecir2022, retained from [Wayfair WANDS](https://github.com/wayfair/WANDS). |
| Generated catalog images in release assets | [CC0 1.0](dev/tools/wands_catalog/distribution/CC0-1.0.txt), only to the extent Rocket Web holds the rights. Historical model/reference provenance is incomplete. |
| Workbench source snapshot under `packages/` | Its own [OSL-3.0](packages/module-opensearch-relevance-workbench/LICENSE.txt) and [AFL-3.0](packages/module-opensearch-relevance-workbench/LICENSE_AFL.txt) notices and [source record](packages/WORKBENCH_SOURCE.md). Not relicensed by the root MIT file. |
| Mage-OS development project and dependencies | Existing Composer metadata and package-specific licenses apply. The root Composer project is not the portable catalog installer. |
| Storefront screenshots | Documentation captures contain third-party UI and marks. Neither the root MIT file nor catalog-image CC0 terms relicense those elements. See [capture notes](dev/tools/wands_catalog/docs/screenshots/README.md). |

Mage-OS, Magento, Hyvä, Wayfair and other names or marks remain with their owners.
This is an independent test catalog, not an official Mage-OS or Wayfair release
or a claim of endorsement. Theme packages and model weights are not included in
the portable catalog archives.

Prices, inventory, dimensions, descriptions, variants and assortments include
synthetic additions. Images are illustrations, not manufacturer photography.
Read the [dataset card](dev/tools/wands_catalog/distribution/DATA_CARD.md) and
[distribution terms](dev/tools/wands_catalog/distribution/TERMS.md), including the
media-provenance limitations. CC0 does not waive third-party trademark, patent,
privacy or other rights; see the [Creative Commons explanation](https://creativecommons.org/publicdomain/zero/1.0/).

## WANDS citation

When using WANDS in research, retain its requested citation:

> Yan Chen, Shujian Liu, Zheng Liu, Weiyi Sun, Linas Baltrunas, and Benjamin
> Schroeder. 2022. *WANDS: Dataset for Product Search Relevance Assessment.*
> Proceedings of the 44th European Conference on Information Retrieval.

[Download the upstream BibTeX entry](dev/tools/wands_catalog/distribution/CITATION.bib).
Also identify the catalog release tag and manifest hash when reporting results
on this derived catalog. Original WANDS judgments do not validate rankings on
rewritten products, generated variants or bundles.
