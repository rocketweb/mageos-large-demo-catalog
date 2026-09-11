# Pilot definition update scope

Prepared 2026-09-11 against the relevance catalog snapshot captured at
`2026-09-11T12:51:33+00:00`. This is a proposal, not deployment approval.
No catalog records, options, stock, images or product assignments were changed.

## Recommended boundary

Update the five pilot families together. This means **13 active products and four
retained, disabled nursery variants**, not the old 667-record catalog packet.
All seventeen products belong only to website 2, WANDS Relevance Lab, in this
snapshot. Keep all existing SKUs, entity IDs, URL rewrites, categories and websites.

| Family | Active products | Definition change |
| --- | ---: | --- |
| WANDS-000056 | 1 | Convert existing root to a simple three-piece nursery-decor set; disable and unlink four inappropriate size variants |
| WANDS-003897 | 1 | Explicit ten-piece bakeware assortment |
| WANDS-017842 | 1 | Explicit forty-five-piece flatware assortment |
| WANDS-030335 | 5 | Outdoor parent plus four children, with coherent furniture counts and separately included pillows |
| WANDS-035295 | 5 | Lamp parent plus four finish variants, each with one floor lamp and two table lamps |

Apply six customer-facing definition fields to each active product: name, full
description, short description, meta title, meta description and `lab_sale_unit`.
The approved synthetic disclosure stays in the copy. Do not copy every field from
the old candidate packet: its quantities and prices are not a fresh inventory plan.

## Exact base proposal counts

| Storage change | Row operations |
| --- | ---: |
| Active-product copy: 39 varchar updates, 26 text updates, 13 new sale-unit varchar rows | 78 |
| Reassign four outdoor child option values | 4 |
| Disable four obsolete nursery children, retaining records | 4 |
| Change existing nursery root type, configurable to simple | 1 |
| Detach nursery: four super links, four product relations, one super attribute, one label | 10 |
| Add one new `6 Pieces` option and its default-store label | 2 |
| Change only the outdoor parent's option caption to `Furniture pieces` | 1 |
| **Total before nursery activation and media** | **100** |

These are explicit logical row operations, not a prediction of all native importer,
indexer, URL, staging or cache side effects. Actual write counts must be compared on
a clone. The proposal is not an executable import. Field changes and original rows
are recorded in the local packet for review and inverse preparation.

No product deletion, shared option rename, bundle change, stock movement, price
write or media assignment is included in these 100 operations.

## Outdoor options: change assignments, not shared labels

| Existing SKU | Current option | Proposed option |
| --- | --- | --- |
| WANDS-030335-2-PIECES-05E3 | 2 Pieces | 4 Pieces, existing option 365 |
| WANDS-030335-3-PIECES-5B0E | 3 Pieces | 5 Pieces, existing option 366 |
| WANDS-030335-4-PIECES-50B3 | 4 Pieces | 6 Pieces, new option ID allocated at application |
| WANDS-030335-5-PIECES-EB6C | 5 Pieces | 7 Pieces, existing option 367 |

The historical SKU strings remain stable identifiers. Reassign all four children
together in the reviewed migration; assigning only the photographed child would
temporarily duplicate the existing `5 Pieces` option within the family.

The shared `2 Pieces`, `3 Pieces` and `4 Pieces` options each have 56 product
consumers; `5 Pieces` has six. Renaming any of those global options would affect
other families. The proposal changes four product values and one parent-specific
caption instead. The new `6 Pieces` option is additive metadata; it has no assigned
consumer until the single intended child is assigned. Option ID 367 already exists
for `7 Pieces` and has no current product consumer in the dependency snapshot.

## Nursery activation: explicit additional decision

The four obsolete SKUs are:

- `WANDS-000056-TODDLER-56FF`
- `WANDS-000056-TWIN-EAC9`
- `WANDS-000056-FULL-008D`
- `WANDS-000056-QUEEN-153F`

Retain their rows, identifiers, media, quantities and historical references. Disable
their product status and detach them from the former configurable parent. Do not
delete products or sum their quantities into the root.

The current root has zero legacy and default-source quantity, while each child has
47 units. The root inherits stock management. Leaving this unchanged after conversion
does not establish that the new simple product can be purchased. There are no
reservation rows for these seventeen SKUs in the captured snapshot; this is not an
audit of orders or customer history, neither of which was queried.

Recommended separately approved activation for this synthetic lab:

- Seed the root with **47 units** in both legacy stock and its existing default MSI
  source row, using the fresh retained Toddler quantity as the lab seed. Set explicit
  `manage_stock=1` and `use_config_manage_stock=0`. This is a synthetic reseed, not a
  transfer or a sum of physical inventory. Leave all four disabled child stocks intact.
- Use the approved local definition price **$74.99**, with its synthetic special
  price **$63.74**, instead of retaining the live parent's $109.99 base price.
  The current configurable storefront price is not proven by that parent EAV value;
  record the actual rendered price on the clone before and after conversion.
- Set root weight to **1.75**, using the retained child's lab weight. The root's
  current weight is null. Retain the store's existing weight unit configuration.

Those choices add seven changed fields across five storage rows: one stock row,
one source row and three decimal EAV rows. They are not included in the base 100
operations and require approval. The old local candidate quantity of 51 is stale
relative to the fresh seed and should not be imported blindly. Inspect existing
special-price date scopes before activating the promotion.

## Dependency evidence and intentionally held work

The read-only dependency probe found twelve configurable relations in total, no
inbound bundle selections, no related/upsell/cross-sell product links, seventeen
existing product URL rewrites, no configurable option pricing rows and no reservation
rows for the scoped SKUs. All four nursery child links match the four retirement
targets. The six copy fields have no per-store overrides on these targets.

The two snapshots are individually read-only and consistent. Entity identities/types
match between them, but they are not one cross-file atomic transaction. Refresh all
evidence immediately before a write window and reject drift. The plan uses a 24-hour
freshness gate and never infers deployment readiness from snapshot success.

Structured component dimensions are deliberately outside this minimal prerequisite.
The live catalog has no `lab_spec_*` EAV attributes; the older full definition packet
also calls for disclosure-aware component storage and rendering. Do not flatten set
dimensions into misleading whole-product measurements. A later schema/rendering
feature needs its own implementation and review. The current scoped copy does not
publish those component measurements as manufacturer facts.

The new photos are still a separate five-product media stage, as specified in
`STOREFRONT_MEDIA_CHECKPOINT.md`. Its earlier expectation that sibling prices remain
unchanged applies to media assignment, not approval to silently skip the coherent
four-child definition update. Both configurable parents and the other six variants
remain excluded from this five-image assignment.

## Apply and rollback requirements

1. Approve the base scope and the nursery activation choice separately. Refresh the
   catalog/dependency snapshot and enumerate any changed counts before implementation.
2. Implement a narrowly scoped, dry-run-first migration for type conversion, link
   detachment, the option addition and four assignments. Do not assume native
   add/update CSV import safely changes an existing product type. The current local
   importer delegates to native add/update and has no dedicated type-conversion step.
3. Snapshot and back up every affected row, old media and required application code;
   verify restore on an isolated clone before live use. Preserve the exact old EAV
   values and the absence of new sale-unit rows, all four child statuses, nursery
   entity type, links, super attribute and its label, and the outdoor caption/options.
4. The inverse must restore those rows and original four option assignments. A newly
   allocated `6 Pieces` option can be removed only if no unapproved consumer or label
   appeared; otherwise retain it and report the extra additive metadata. Never delete
   existing shared option definitions or historical products. Activation, if approved,
   needs its own five-row inverse, including restoring a previously absent special price.
5. Rehearse forward and inverse operations on the clone, including price, stock,
   salability, product type, selected SKU, all four outdoor options and all lamp
   variants. Detect unexpected indexed/derived changes. Do not place an order.
6. Obtain exact deployment approval for the tested revision, packet hash, destination
   and affected counts. Apply narrowly with competing writes paused, then verify.
   Only afterward refresh and approve the separate media upload/import preflight.

## Reproducible local packet

Current output: `var/wands/pilot-definition-scope-v3/`.

- `summary.json`: counts and open creation/rehearsal gates.
- `fields.proposed.json`: exact before/after values and before rows for 87 field operations.
- `relationships.detach.proposed.json`: exact ten nursery relationship/metadata rows.
- `options.create.proposed.json`: the additive `6 Pieces` option proposal.
- `axis-labels.proposed.json`: one parent-specific caption change.
- `inventory.before.json`: current stock, source rows and reservation aggregates.
- `dependencies.review.json`: relationship, URL, option-consumer and reservation evidence.

The complete candidate definitions are present for provenance, not blanket write
authorization. The generated files are ignored and must not be staged. Scope v1 and
v2 are historical, superseded packets. The private remote evidence directory is
`var/wands/pilot-definition-remote-v1/`; its remote source is the isolated container
temporary directory `/tmp/wands-definition-scope.E9sWGK`, outside the application.

From the worktree root, with fresh evidence and a new output directory:

```sh
python3 dev/tools/wands_catalog/scope_pilot_definition_update.py \
  --definitions var/wands/catalog-definitions-v3 \
  --request var/wands/pilot-definition-request-v1/snapshot-request.json \
  --snapshot var/wands/pilot-definition-remote-v1/before \
  --dependencies var/wands/pilot-definition-remote-v1/dependencies.json \
  --output-dir var/wands/pilot-definition-scope-new

tail -f var/wands/pilot-definition-scope-new.log
```

The original request was prepared by running the same planner with only
`--definitions` and a fresh `--output-dir`. Keep the same candidate and request hashes
when collecting a new snapshot. Routine output goes to logs, not the terminal.
