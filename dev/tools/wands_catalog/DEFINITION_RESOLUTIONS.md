# Remaining product-definition resolutions

The user approved coherent, explicitly synthetic definitions for genuine WANDS
conflicts, with the conflicting source evidence retained. That approval is for
local definition work. It does not authorize import, stock transfer, deletion,
commit, push, deployment or image generation.

## Completed local scope

`var/wands/catalog-definitions-v3` resolves the 41 remaining flagged families and
all eight held definitions. These overlap: five holds are among the 41 families,
and three are standalone products, giving **44 distinct product definitions**.

| Definition group | Products | Resolution |
| --- | ---: | --- |
| Outdoor furniture assortments | 22 | Exact component roles and counts; coherent named additions for variable sets; furniture counts exclude loose pillows |
| Nursery-decor sets | 9 | Retain the named textile/decor assortments and remove adult-bed size axes |
| End tables and plastic nightstand | 6 | Compact widths, preserved round/square footprints, end-table identity retained, plastic finishes changed to Clear/Black |
| Pillowcases/sham | 3 | Actual cover dimensions and explicit sale quantities; no mattress labels |
| Toddler bed | 1 | Toddler-only frame design, retaining color choices |
| Bakeware, flatware and kitchen-tool sets | 3 | Exact enumerated assortments with no unexplained pieces |

This extends the previous 49 corrected roots to **93 corrected roots** in a
357-root review packet. All 87 original family-audit findings now pass the
post-correction semantic checks. There are zero remaining holds in this packet.
This clears the known definition queue, not every possible realism issue in
the entire catalog.

### Important conflict decisions

- **Cobleskill:** two pillowcases are actually specified by
  `numberofpillowcasesincluded`. The old hold incorrectly treated the missing
  generic total as missing quantity. The extraction rule now honors the specific
  count while still rejecting contradictory quantity fields.
- **Plaid pillow sham:** one cover, using the singular product description as
  the approved synthetic choice. Both conflicting quantity fields remain in the
  source evidence.
- **Keratin Krew:** retain pillowcase identity rather than the contradictory
  fitted-sheet type. The new copy makes the fictional choice explicit through
  the shared synthetic-design disclosure.
- **Ghost Buster:** keep plastic construction and use Clear/Black instead of
  Walnut/Oak. Variant facets are reconciled with changed options, so a Clear
  child cannot keep a stale Walnut facet. Clear remains withheld from the
  separate controlled specification enum until that enum supports it.
- **Abe:** one round table plus four chairs, with color options only. The
  conflicting five-chair/six-piece fields are preserved, not silently corrected
  in the WANDS source.
- **Bakeware:** two round cake pans, one square cake pan, one rectangular cake
  pan and its lid, one loaf pan, one muffin pan, one rack and two baking sheets.
  The lid has explicitly matched synthetic exterior dimensions; no sealing,
  temperature or cooking-performance claim is made.
- **Flatware:** eight five-piece place settings plus five named serving utensils,
  totaling 45 pieces. Conflicting serving-utensil flags remain in evidence.
- **Burger/fry kit:** one assembled burger press and one assembled fry cutter.
  Internal pieces are not presented as five independently defined products.

Nursery and bed descriptions make no infant-sleep, fit, capacity, installation
or safety claims. Images must show nursery assortments laid out, not in use
with an infant. All new geometry remains explicitly synthetic.

## Exact local change and relationship checks

The cumulative packet proposes changes to 603 active records and retirement of
64 redundant children: **667 distinct affected records**. It proposes five
configurable-to-simple root conversions where removing invented size axes leaves
only one real design. These counts include the previous packet's 20 retirements
and one conversion. No records have been deleted or converted in Magento.

The inverse records preserve complete original definitions, prices and inventory.
The five proposed simple roots use named existing child inventory/price seeds;
actual stock transfer needs its own destination snapshot and import decision.
If applied as proposed, the original 2,000 configurable families would become
1,995. Maintaining exactly 2,000 would require selecting five suitable replacement
families, not keeping nonsensical size choices on these products.

All 600 selection references across the 50 pinned local Magento bundles were
checked. None references a changed or retired product. This is evidence about
the pinned local bundle release, not a fresh inspection of the remote database.

## Rebuild and verify

```sh
cd /Users/matt/code/rocket-search/.worktrees/wands-merchandising

python3 dev/tools/wands_catalog/catalog_repairs.py \
  --depth-packet var/wands/depth-pilot-v9-synthetic-dimensions \
  --expand-tested-rules \
  --resolve-remaining-definitions \
  --media-dir /Users/matt/code/mageos-latest/pub/media/import/wands \
  --output-dir var/wands/catalog-definitions-next

python3 dev/tools/wands_catalog/verify_catalog_repairs.py \
  --packet var/wands/catalog-definitions-next
```

Use a fresh versioned output directory. Standard output and runtime failures
stay in the sibling `.log` and `.verify.log` files; `--json` opts into terminal
output. No GPU, network service or background worker is started.

New outputs supplement the earlier correction packet:

- `definition-audit.after.jsonl`: checks all original findings against actual
  candidate axes, geometry and component manifests, not merely a repair flag.
- `resolution-policy.json`: the explicit synthetic-resolution policy and the
  prohibition on globally renaming shared EAV option values.
- `bundle-reference-impact.json`: every-option bundle reference counts and hits.
- `rules.json` and `source-evidence.jsonl`: authored choices and unchanged source
  evidence. Each resolved record also carries the resolution basis and version.

The independent verifier rechecks the full family audit, forward/inverse replay,
original family closure, fixed assortment counts, bundle references and pinned
input/output hashes. Original WANDS benchmark files stay unchanged.

## Not part of this completion

Reference images still require repair and visual acceptance. Gallery briefs
remain non-executable. Magento import must create/reuse new option labels and
assign them to the affected SKUs only; it must never rename shared old labels
such as Toddler or Walnut globally. Component storage, disclosure-aware rendering,
new-enum support, fresh remote preflight/backup and live acceptance remain
separate work. Catalog images remain outside Git.
