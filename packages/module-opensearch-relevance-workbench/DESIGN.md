# Workbench design system

## Product thesis

The Workbench turns search relevance work into one calm, evidence-led operating sequence inside Magento Admin. It is designed for a lab operator who needs to know what is live, what evidence supports a candidate, what to do next, and how to restore the prior state.

## Visual world

Magento Admin is the visual world. The Workbench uses native Admin controls, tables, permissions, form behavior, and message language. The custom shell adds hierarchy and workflow orientation without presenting a separate design system.

The palette is intentionally restrained:

- Charcoal command header for the operating context
- Magento orange for selection and the primary path
- Neutral gray canvas and borders for supporting information
- Green only for an active Workbench candidate
- Standard Magento warning and error treatments for risk and failure

The interface uses no decorative imagery or raster assets. Image provenance is therefore not applicable.

## Information architecture

The primary workflow is:

1. Readiness: verify the runtime and surface blockers.
2. Snapshot: preview and approve the exact query demand for the cycle.
3. Tune: capture the stock query shape and create one bounded candidate.
4. Judge: prepare and complete a human rating queue.
5. Compare: run offline experiments, inspect evidence, and explicitly accept a winner.
6. Activate: apply the exact accepted candidate or restore the previous live state.

The workflow rail reports durable completion where evidence exists and marks the first incomplete step as current. Tune completes when a valid candidate and approved query snapshot are available for the same store. Judge and Compare complete only from persisted compatible input identities. Form submissions return to the step that owns the action.

## First viewport

The command header answers two questions immediately:

- What does this workspace do?
- What search configuration is live for each store view?

The workflow rail and recommended panel then expose the next useful action. A hash in the URL preserves an operator's explicit step selection.

## Content hierarchy

Each panel presents the primary action first. Historical records, schedules, exported evidence, and cleanup previews are secondary disclosures. Empty primary states explain both what is missing and which workflow step resolves it.

The Activate panel separates three concepts:

- Current storefront state by store view
- Accepted candidates that are not already live and require a fresh evidence check on submission
- Append-only activation and rollback history

An already-live candidate is not offered for activation again.

## Interaction and accessibility

The workflow uses an accessible tablist with linked tabs and panels, arrow-key navigation, Home and End support, and responsive orientation metadata. The selected tab and completed workflow state are distinct.

Rating controls are grouped with a fieldset and query-product legend. Context cells use row headers. Long rating queues keep column headings visible. Secondary disclosure buttons expose their expanded state. Empty tables receive an explicit empty row.

At narrower widths, the workflow becomes a horizontal tab strip and the command header stacks. Tables remain horizontally scrollable inside their sections.

## Runtime safety reflected in the design

Activation is intentionally narrow. The UI offers only explicitly accepted winning experiments that are not already live. The activation service then captures current index evidence and refuses stale evidence before writing any state. The storefront integration applies the persisted field-boost transformation only to the quick-search request. GraphQL and other request types remain unchanged. Failures return the original stock query.

Every activation and rollback records an append-only event and updates the per-store current-state pointer transactionally. Rollback restores the exact previous activation or stock search. Reapplying the exact current candidate is rejected so that the rollback chain cannot point back to the same effective state.

## Source map

- Admin shell and task content: `view/adminhtml/templates/workbench.phtml`
- Responsive presentation: `view/adminhtml/web/css/workbench.css`
- Tab behavior and progressive disclosure: `view/adminhtml/web/js/workbench.js`
- Workflow and live-state view data: `Block/Adminhtml/Workbench.php`
- Activation validation: `Model/Activation/LiveActivationService.php`
- Append-only activation state: `Model/Persistence/LiveActivationRepository.php`
- Storefront query application: `Plugin/OpenSearch/CaptureMappedQuery.php`

## Acceptance status

Source-level design review is part of the code-first gate. Screenshot-based finish review remains pending until an authorized Magento Admin runtime is available with the current source deployed.
