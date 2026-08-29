<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch;

class CapabilityDetector
{
    private const MINIMUM_VERSION = '3.8.0';
    private const EXCLUDED_VERSION = '4.0.0';
    private const SEARCH_RELEVANCE_PLUGIN = 'opensearch-search-relevance';
    private const ML_COMMONS_PLUGIN = 'opensearch-ml';

    /**
     * @param list<string> $pluginNames
     */
    public function detect(
        string $version,
        array $pluginNames,
        bool $workbenchReachable
    ): CapabilityReport {
        $reasonCodes = [];

        if (!$this->isSupportedVersion($version)) {
            $reasonCodes[] = 'OPENSEARCH_VERSION_UNSUPPORTED';
        }

        if (!$this->hasPlugin($pluginNames, self::SEARCH_RELEVANCE_PLUGIN)) {
            $reasonCodes[] = 'SEARCH_RELEVANCE_PLUGIN_MISSING';
        }

        if (!$workbenchReachable) {
            $reasonCodes[] = 'WORKBENCH_UNAVAILABLE';
        }

        $coreReady = $reasonCodes === [];

        if (!$this->hasPlugin($pluginNames, self::ML_COMMONS_PLUGIN)) {
            $reasonCodes[] = 'ML_COMMONS_PLUGIN_MISSING';
        }

        return new CapabilityReport(
            $coreReady,
            $coreReady && $reasonCodes === [],
            $reasonCodes
        );
    }

    private function isSupportedVersion(string $version): bool
    {
        return version_compare($version, self::MINIMUM_VERSION, '>=')
            && version_compare($version, self::EXCLUDED_VERSION, '<');
    }

    /**
     * @param list<string> $pluginNames
     */
    private function hasPlugin(array $pluginNames, string $requiredPlugin): bool
    {
        foreach ($pluginNames as $pluginName) {
            if ($pluginName === $requiredPlugin) {
                return true;
            }
        }

        return false;
    }
}
