<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch;

use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Api\IndexEvidenceCaptureInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use OpenSearch\Client;
use UnexpectedValueException;

class IndexEvidenceCapture implements IndexEvidenceCaptureInterface
{
    private const INDEX_NAME_PATTERN = '/\A[a-z0-9][a-z0-9._-]{0,254}\z/D';

    /** @var list<string> */
    private const RELEVANT_SETTING_KEYS = [
        'analysis',
        'max_ngram_diff',
        'max_shingle_diff',
        'number_of_shards',
        'query',
        'similarity',
        'sort',
    ];

    public function __construct(
        private readonly ConfiguredOpenSearchClientProvider $clientProvider,
        private readonly CanonicalJson $canonicalJson
    ) {
    }

    public function capture(string $targetAlias): IndexEvidence
    {
        $this->assertValidIndexName($targetAlias);
        $client = $this->clientProvider->get();
        $physicalIndex = $this->resolvePhysicalIndex($client, $targetAlias);
        $mapping = $this->readMapping($client, $physicalIndex);
        $settings = $this->readSettings($client, $physicalIndex);
        $indexUuid = $this->readIndexUuid($settings);
        $relevantSettings = $this->selectRelevantSettings($settings);
        [$documentCount, $primaryShardBoundaries] = $this->readStats($client, $physicalIndex);

        $identity = [
            'alias' => $targetAlias,
            'physical_index' => $physicalIndex,
            'index_uuid' => $indexUuid,
            'mapping_hash' => $this->canonicalJson->hash($mapping),
            'relevant_settings_hash' => $this->canonicalJson->hash($relevantSettings),
            'primary_shards' => $primaryShardBoundaries,
            'document_count' => $documentCount,
        ];

        return new IndexEvidence(
            $identity['alias'],
            $identity['physical_index'],
            $identity['index_uuid'],
            $identity['mapping_hash'],
            $identity['relevant_settings_hash'],
            $identity['primary_shards'],
            $identity['document_count'],
            $this->canonicalJson->hash($identity)
        );
    }

    private function resolvePhysicalIndex(Client $client, string $targetAlias): string
    {
        $response = $this->requestObject($client, '/' . rawurlencode($targetAlias) . '/_alias');
        $indices = array_keys($response);

        if (count($indices) !== 1) {
            throw new UnexpectedValueException('Target alias must resolve to exactly one physical index');
        }

        $this->assertValidIndexName($indices[0]);

        return $indices[0];
    }

    /**
     * @return array<string, mixed>
     */
    private function readMapping(Client $client, string $physicalIndex): array
    {
        $response = $this->requestObject(
            $client,
            '/' . rawurlencode($physicalIndex) . '/_mapping'
        );
        $mapping = $response[$physicalIndex]['mappings'] ?? null;

        if (!is_array($mapping)) {
            throw new UnexpectedValueException('Target index mapping response is invalid');
        }

        return $mapping;
    }

    /**
     * @return array<string, mixed>
     */
    private function readSettings(Client $client, string $physicalIndex): array
    {
        $response = $this->requestObject(
            $client,
            '/' . rawurlencode($physicalIndex) . '/_settings'
        );
        $settings = $response[$physicalIndex]['settings'] ?? null;

        if (!is_array($settings) || !isset($settings['index']) || !is_array($settings['index'])) {
            throw new UnexpectedValueException('Target index settings response is invalid');
        }

        return $settings;
    }

    /**
     * @param array<string, mixed> $settings
     */
    private function readIndexUuid(array $settings): string
    {
        $indexUuid = $settings['index']['uuid'] ?? null;

        if (!is_string($indexUuid) || $indexUuid === '') {
            throw new UnexpectedValueException('Target index UUID is missing');
        }

        return $indexUuid;
    }

    /**
     * @param array<string, mixed> $settings
     * @return array<string, mixed>
     */
    private function selectRelevantSettings(array $settings): array
    {
        $indexSettings = $settings['index'];
        $relevantSettings = [];

        foreach (self::RELEVANT_SETTING_KEYS as $key) {
            if (array_key_exists($key, $indexSettings)) {
                $relevantSettings[$key] = $indexSettings[$key];
            }
        }

        return $relevantSettings;
    }

    /**
     * @return array{0: int, 1: list<array{shard: int, max_sequence_number: int, global_checkpoint: int}>}
     */
    private function readStats(Client $client, string $physicalIndex): array
    {
        $response = $this->requestObject(
            $client,
            '/' . rawurlencode($physicalIndex) . '/_stats/docs',
            ['params' => ['level' => 'shards']]
        );
        $indexStats = $response['indices'][$physicalIndex] ?? null;

        if (!is_array($indexStats)) {
            throw new UnexpectedValueException('Target index statistics response is invalid');
        }

        $documentCount = $indexStats['primaries']['docs']['count'] ?? null;
        $shards = $indexStats['shards'] ?? null;

        if (!is_int($documentCount) || $documentCount < 0 || !is_array($shards)) {
            throw new UnexpectedValueException('Target index statistics response is invalid');
        }

        $primaryShardBoundaries = [];

        foreach ($shards as $shardId => $copies) {
            if (!ctype_digit((string)$shardId) || !is_array($copies)) {
                throw new UnexpectedValueException('Target index shard statistics are invalid');
            }

            $primaryBoundary = $this->findPrimaryBoundary($copies, (int)$shardId);
            $primaryShardBoundaries[] = $primaryBoundary;
        }

        usort(
            $primaryShardBoundaries,
            static fn (array $left, array $right): int => $left['shard'] <=> $right['shard']
        );

        return [$documentCount, $primaryShardBoundaries];
    }

    /**
     * @param array<array-key, mixed> $copies
     * @return array{shard: int, max_sequence_number: int, global_checkpoint: int}
     */
    private function findPrimaryBoundary(array $copies, int $shardId): array
    {
        $primaryBoundaries = [];

        foreach ($copies as $copy) {
            if (!is_array($copy) || ($copy['routing']['primary'] ?? null) !== true) {
                continue;
            }

            $maxSequenceNumber = $copy['seq_no']['max_seq_no'] ?? null;
            $globalCheckpoint = $copy['seq_no']['global_checkpoint'] ?? null;

            if (!is_int($maxSequenceNumber) || !is_int($globalCheckpoint)) {
                throw new UnexpectedValueException('Primary shard sequence statistics are invalid');
            }

            $primaryBoundaries[] = [
                'shard' => $shardId,
                'max_sequence_number' => $maxSequenceNumber,
                'global_checkpoint' => $globalCheckpoint,
            ];
        }

        if (count($primaryBoundaries) !== 1) {
            throw new UnexpectedValueException('Each shard must have exactly one primary sequence boundary');
        }

        return $primaryBoundaries[0];
    }

    /**
     * @param array<string, mixed> $attributes
     * @return array<string, mixed>
     */
    private function requestObject(Client $client, string $path, array $attributes = []): array
    {
        $response = $client->request('GET', $path, $attributes);

        if (!is_array($response) || array_is_list($response)) {
            throw new UnexpectedValueException('OpenSearch evidence response must be a JSON object');
        }

        return $response;
    }

    private function assertValidIndexName(string $indexName): void
    {
        if (preg_match(self::INDEX_NAME_PATTERN, $indexName) !== 1) {
            throw new InvalidArgumentException('OpenSearch target must be a concrete safe alias or index name');
        }
    }
}
