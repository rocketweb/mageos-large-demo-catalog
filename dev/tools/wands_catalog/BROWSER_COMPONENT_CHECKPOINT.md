# Native Hyva browser component checkpoint, 2026-09-11

All **24 browser scenarios pass** using the installed Hyva dropdown, configurable
selection JavaScript, price template, price formatting, Alpine 3 and stylesheet.
These are native components rendered by the isolated Magento runtime, not a
rewritten or mocked price calculator. The fixture uses the remotely captured Hyva
theme registration and store assignment, ID 5.

## Coverage and evidence

Each of the two configurable families is tested at 1920x1080 and 390x844:

- Empty selection fails native required-field validation.
- All four choices select exactly the expected child ID and SKU.
- Native selection and price events match the visible price and indexed price.
- Clearing a choice restores the minimal price and required-selection state.
- No browser page errors or horizontal overflow occur.

That is 16 successful selection cases and eight required/reset cases. Outdoor
prices are $134.99, $159.99, $189.99 and $209.99 for 4, 5, 6 and 7 Pieces. All lamp
finishes are $109.99. The visible labels remain Furniture pieces and Finish.

Four final-state screenshots received direct visual review. Desktop and mobile
controls, labels and prices are visible without clipping. The page identifies
itself as an isolated component rehearsal, not the live storefront.

- `var/wands/theme-browser-components-v2.json`: native rendered components and
  installed asset hashes.
- `var/wands/hyva-browser-fixture-v1/`: two offline pages and private vendor assets.
- `var/wands/hyva-browser-tests-v4/result.json`: complete 24-case browser evidence.
- `var/wands/hyva-browser-visual-observations-v1.json`: hash-bound screenshot review.
- `var/wands/hyva-browser-acceptance-v1/result.json`: independent acceptance of
  browser scenarios, visual evidence and native rollback.
- `var/wands/theme-browser-cart-verification-v1/result.json`: all 21 native
  unsaved-cart cases still pass with captured theme metadata.
- `var/wands/theme-browser-native-verification-v1/result.json`: exact native
  HTML/JSON option bindings and verified rollback.
- `var/wands/browser-component-unit-tests-v2.log`: **414 Python tests pass**.

The first harness wait incorrectly looked for Alpine state on the select instead
of its component root. A second attempt exposed a transient duplicate old/new price
during Alpine rendering when both prices were identical. The final harness waits
for exactly one visible price before asserting. No production template change was
made for either harness timing issue, and failed run logs are retained.

## Isolation and recovery

The browser pages load only local scripts/styles. Their content security policy
blocks connections, form submissions and images. No demo URL is navigated, no
catalog images are loaded, and no live cart is created. Vendor assets and screenshots
remain ignored under `var/wands`; they are not redistributed in the repository.

The 105-row migration rehearsal was reversed, and native stock/price indexing was
rerun. All 17 product observations, price rows and **121 in-process table hashes**
match the indexed baseline. There are 119 persistent tables plus two temporary
index working tables. No synthetic theme tables were added in this pass. Database
`wands_rehearsal_theme_capture_v1` is restored, and the browser sessions were closed.

Runtime: Mage-OS 3.5.0, Hyva 1.5.2, PHP 8.4.24 and MariaDB 11.4.12. Browser runner:
agent-browser 0.28.0. This does not establish acceptance on Mage-OS 3.4.

## Repeat the browser test

Run from the merchandising worktree, using a fresh output directory:

```sh
python3 dev/tools/wands_catalog/test_hyva_browser_components.py \
  --manifest var/wands/hyva-browser-fixture-v1/manifest.json \
  --output-dir var/wands/hyva-browser-tests-new
```

Routine output is written to the adjacent `.log` file. The runner verifies input
hashes, discovers the dropdown by its accessible role/name, takes fresh references
before interaction, and closes its named browser session. A new run requires its
own screenshot review before final acceptance.

## Remaining release gates

This closes the native **component interaction** gate, not the entire storefront.
Full product pages, actual routing/layout, persisted cart, checkout, production CSP
and gallery/media behavior remain unverified. The native media-import lifecycle and
production migration adapter still need rehearsal. Fresh remote scope/backup evidence
and explicit approval must precede live definition changes, media upload/import or
gallery retirement. No push, merge, module deployment or live catalog mutation was
performed in this pass.
