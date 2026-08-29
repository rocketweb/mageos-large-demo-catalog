# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The primary user is a merchant or search operator working inside Mage-OS Admin. They need to understand current catalog-search behavior, test a bounded change, judge the result, and control whether that change reaches the storefront.

## Product Purpose

OpenSearch Relevance Workbench turns catalog-search tuning into an evidence-backed operating workflow. Success means an operator can move from readiness through snapshot, tuning, judgment, comparison, activation, and rollback without OpenSearch Dashboards or hidden live changes.

## Positioning

The Workbench binds every decision to immutable query, catalog-index, configuration, judgment, and experiment identities. It combines merchant review with local decision gates, then makes the accepted state and recovery path explicit.

## Operating Context

The product runs as a Mage-OS Admin module against the store's configured OpenSearch service. The primary workflow is periodic rather than continuous. Private-lab testing uses a generated 1,200-product catalog and a supported OpenSearch 3.8 Search Relevance runtime.

## Capabilities and Constraints

- The human workflow covers readiness, exact query snapshots, stock baselines, bounded field-boost candidates, human ratings, offline experiments, evidence review, activation, and rollback.
- Live activation is limited to an explicitly accepted candidate. It records the pre-activation state, current state, actor, evidence identity, and an auditable rollback operation.
- The interface must always distinguish evaluation state from the configuration currently serving storefront search.
- The supported OpenSearch 3.8 artifact does not qualify the LLM judgment path. Human judgment remains the complete supported path.
- The generated catalog proves mechanics and scale, not merchant usability or ranking quality.
- Paid LLM work, connector credentials, and remote resource deletion remain outside the current application boundary.

## Brand Commitments

The product name is OpenSearch Relevance Workbench. Language should be direct, calm, operational, and explicit about evidence, safety, and current state.

## Evidence on Hand

- The repository contains deterministic integration, security, and Mage-OS qualification suites.
- The large-catalog lane has verified 1,200 Magento product entities, 816 storefront-indexed documents, and a 50-pair human rating queue.
- The private comtom lab provides a live Mage-OS, Hyvä, MySQL, and OpenSearch runtime for operator acceptance.
- No representative merchant catalog, approved relevance labels, or completed merchant observation is available yet.

## Product Principles

1. Show the operator where they are, what is live, and what action comes next.
2. Make evidence identity and freshness visible before consequential actions.
3. Keep every live change narrow, explicit, auditable, and reversible.
4. Put the main task first and move history, diagnostics, and raw detail behind progressive disclosure.
5. Never present generated-catalog results as merchant relevance proof.
