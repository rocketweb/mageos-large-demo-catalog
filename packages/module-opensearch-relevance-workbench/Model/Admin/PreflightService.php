<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Admin;

use MageOS\OpenSearchRelevanceWorkbench\Api\SearchRelevanceClientInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\CapabilityDetector;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\ConfiguredOpenSearchClientProvider;

class PreflightService
{
    public function __construct(
        private readonly ConfiguredOpenSearchClientProvider $clientProvider,
        private readonly SearchRelevanceClientInterface $searchRelevanceClient,
        private readonly CapabilityDetector $capabilityDetector
    ) {
    }

    /**
     * @return array<string, bool|string|list<string>|array<string, string>>
     */
    public function run(): array
    {
        $client = $this->clientProvider->get();
        $clusterInfo = $client->info();
        $plugins = $client->cat()->plugins(['format' => 'json']);
        $pluginVersions = [];

        foreach ($plugins as $plugin) {
            $component = $plugin['component'] ?? null;
            $version = $plugin['version'] ?? null;

            if (is_string($component) && is_string($version)) {
                $pluginVersions[$component] = $version;
            }
        }

        ksort($pluginVersions, SORT_STRING);
        $stats = $this->searchRelevanceClient->stats();
        $report = $this->capabilityDetector->detect(
            (string)($clusterInfo['version']['number'] ?? ''),
            array_keys($pluginVersions),
            $stats !== []
        );
        $reasonCodes = $report->getReasonCodes();

        if ($report->isLlmReady()) {
            $reasonCodes[] = 'LLM_JUDGMENT_RUNTIME_UNQUALIFIED';
        }

        return [
            'opensearch_version' => (string)($clusterInfo['version']['number'] ?? 'unknown'),
            'plugin_versions' => $pluginVersions,
            'human_workflow_ready' => $report->isCoreReady(),
            'llm_workflow_ready' => false,
            'reason_codes' => $reasonCodes,
        ];
    }
}
