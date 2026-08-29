# Phase 0 Contract Findings

Date: 2026-08-26

These findings apply to the exact local fixture and do not establish support for another OpenSearch distribution.

## Pinned distribution

- OpenSearch image: `opensearchproject/opensearch:3.8.0`
- Image digest: `sha256:bcc1797519726ceb6d651d4a3e60b7c30da91793914a8dfe75fd441d4f641509`
- Search Relevance plugin: `3.8.0.0`
- ML Commons plugin: `3.8.0.0`

## Confirmed contracts

- Query-set create, read, search, and delete work.
- Mustache search configurations round-trip without payload changes.
- Imported judgments complete and feed a pointwise experiment.
- Experiment validation reports `VALID` and `DRIFTED` for the tested cases.
- Physical-index evidence detects document drift independently of SRW validation.
- A restricted Security plugin role can manage the tested SRW resources and capture index evidence without reading catalog documents or cluster settings.
- Mage-OS's public client resolver supplies the store-configured stock OpenSearch client to both Search Relevance requests and physical-index evidence capture. Raw client injection is not safe because dependency injection constructs it without connection options.
- Raw Search Relevance requests carry a five-second connection deadline and a 30-second overall deadline through the Mage-OS 3.4 legacy transport adapter.

## Mage-OS baseline qualification

The public fixture completed a clean Mage-OS 3.4.0 installation on PHP 8.4.24 with MySQL 8.4 and the pinned OpenSearch 3.8 image. Declarative schema status and dependency-injection compilation passed after the fixture was corrected to mirror a package without the repository's development `vendor/` tree.

An opt-in clean fixture also installed licensed Hyvä 1.5.2 without storing its repository identity or credentials in this source tree. It enabled `Hyva_Theme`, activated `Hyva/default`, compiled dependency injection, rebuilt the catalog-search index, passed the installed Search Relevance transport, and completed the same baseline validation.

The stock storefront and GraphQL paths each passed two-sentinel compilation and five fresh native-request round trips. They are not the same baseline:

- storefront `quick_search_container`: `de375797d58b2f4eb6342dbe74482380607adf95b5026cbc1ddb81afb5f1c925`
- GraphQL `graphql_product_search`: `9d4792092e941710b54e00f6837ebd789e1014c382f096a3f9b354a26bfe9324`

GraphQL has a distinct request definition and one additional query-text path in this fixture. Storefront and GraphQL therefore require separate immutable baseline types. The capture plugin remained a no-op outside the explicit request-scoped capture context in unit coverage.

The active Hyvä storefront produced the same `quick_search_container` template digest and query-text paths as Luma in this exact fixture. Hyvä therefore shares the storefront baseline type for Mage-OS 3.4.0 and Hyvä 1.5.2. The public CI lane remains free of private dependencies; licensed Hyvä qualification is an explicit operator-run gate.

## Dependency drift

A fresh Mage-OS 3.4.0 project install on 2026-08-26 resolved `opensearch-project/opensearch-php` 2.6.0. The installed module resolved the configured stock OpenSearch client, called the Search Relevance stats route successfully, captured index-backed storefront and GraphQL requests, and completed dependency-injection compilation. The direct Search Relevance integration lane remains pinned to 2.5.1 so both dependency points keep explicit coverage.

## Remote ownership names

Search Relevance 3.8 rejects resource names longer than 50 characters. A full SHA-256 value cannot be embedded in a namespaced remote name. Use a bounded prefix and short hash in the remote name, while storing the full content hash locally and reconstructing the full hash from the remote immutable fields during cleanup preview. Eligibility still requires exact remote ID, type, name, and full content-hash matches.

## Tested least-privilege actions

The security fixture passed with this exact cluster-action set:

```text
cluster:admin/search_relevance_stats_action
cluster:admin/opensearch/search_relevance/queryset/put
cluster:admin/opensearch/search_relevance/queryset/get
cluster:admin/opensearch/search_relevance/queryset/search
cluster:admin/opensearch/search_relevance/queryset/delete
cluster:admin/opensearch/search_relevance/search_configuration/create
cluster:admin/opensearch/search_relevance/search_configuration/get
cluster:admin/opensearch/search_relevance/search_configuration/search
cluster:admin/opensearch/search_relevance/search_configuration/delete
cluster:admin/opensearch/search_relevance/judgment/create
cluster:admin/opensearch/search_relevance/judgment/get
cluster:admin/opensearch/search_relevance/judgment/search
cluster:admin/opensearch/search_relevance/judgment/delete
cluster:admin/opensearch/search_relevance/experiment/create
cluster:admin/opensearch/search_relevance/experiment/get
cluster:admin/opensearch/search_relevance/experiment/search
cluster:admin/opensearch/search_relevance/experiment/delete
cluster:admin/opensearch/search_relevance/experiment/validate
```

Physical-index evidence required only these actions on the allowlisted index pattern:

```text
indices:admin/aliases/get
indices:admin/mappings/get
indices:monitor/settings/get
indices:monitor/stats
```

The role could not search catalog documents or read cluster settings. This list covers the routes exercised in Phase 0. It is not permission for future routes added in later phases.

## LLM judgment blocker

An upstream refresh on 2026-08-26 found no supported replacement artifact. The newest official Search Relevance tag remains [`3.8.0.0`](https://github.com/opensearch-project/search-relevance/tags). The repository's current `main` commit, `8a6646ceb3d8a78cf8260a7d9e6b3fdad5b09319`, identifies itself as `3.9.0-SNAPSHOT`, but its [runtime dependency block](https://github.com/opensearch-project/search-relevance/blob/8a6646ceb3d8a78cf8260a7d9e6b3fdad5b09319/build.gradle#L230-L245) still adds Reflections without adding the SLF4J API to the plugin runtime. The relevant dependency block is otherwise unchanged from the 3.8 tag.

The unreleased 3.9 work also [removes the global judgment cache and adds explicit existing-judgment reuse plus a failed-judgment retry route](https://github.com/opensearch-project/search-relevance/pull/528). A future 3.9 qualification must therefore replace the 3.8 cache contract instead of assuming backward compatibility.

The first remote-model prediction against the untouched pinned distribution terminates OpenSearch with:

```text
java.lang.NoClassDefFoundError: org/slf4j/LoggerFactory
at org.reflections.Reflections.<clinit>(Reflections.java:115)
at org.opensearch.ml.common.MLCommonsClassLoader.loadMLAlgoParameterClassMapping(...)
```

The packaged Search Relevance plugin contains `reflections-0.10.2.jar` and `opensearch-ml-client-3.8.0.0.jar`, but it does not contain the SLF4J API jar required when the ML client deserializes the remote prediction. The ML Commons plugin separately contains `slf4j-api-1.7.36.jar`, but plugin classloader isolation does not make that jar available to Search Relevance.

`Test/Fixture/OpenSearch/Dockerfile.llm` builds a diagnostic-only derivative that copies the exact SLF4J API jar already present in ML Commons into Search Relevance. That derivative survives prediction, but the current deterministic stub probe returns a completed judgment with the document in `failures` and zero generated ratings. The cache-behavior probe is therefore opt-in and is not a passing release gate.

Consequences:

- The untouched OpenSearch 3.8.0 distribution is not LLM-ready for this module.
- Do not present the dependency-corrected derivative as a supported production distribution.
- Do not promise cache reuse or LLM judgment support until an official artifact or explicitly reviewed distribution passes the complete connector, judgment, failure, cache, and cleanup suite.
- Keep module policy at `overwriteCache=true` unless every locally recorded identity matches. The local policy remains defensive and does not imply that the upstream cache has been qualified.
