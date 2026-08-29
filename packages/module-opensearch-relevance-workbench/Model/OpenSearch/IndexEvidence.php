<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch;

class IndexEvidence
{
    /**
     * @param list<array{shard: int, max_sequence_number: int, global_checkpoint: int}> $primaryShardBoundaries
     */
    public function __construct(
        private readonly string $alias,
        private readonly string $physicalIndex,
        private readonly string $indexUuid,
        private readonly string $mappingHash,
        private readonly string $relevantSettingsHash,
        private readonly array $primaryShardBoundaries,
        private readonly int $documentCount,
        private readonly string $evidenceHash
    ) {
    }

    public function getAlias(): string
    {
        return $this->alias;
    }

    public function getPhysicalIndex(): string
    {
        return $this->physicalIndex;
    }

    public function getIndexUuid(): string
    {
        return $this->indexUuid;
    }

    public function getMappingHash(): string
    {
        return $this->mappingHash;
    }

    public function getRelevantSettingsHash(): string
    {
        return $this->relevantSettingsHash;
    }

    /**
     * @return list<array{shard: int, max_sequence_number: int, global_checkpoint: int}>
     */
    public function getPrimaryShardBoundaries(): array
    {
        return $this->primaryShardBoundaries;
    }

    public function getDocumentCount(): int
    {
        return $this->documentCount;
    }

    public function getEvidenceHash(): string
    {
        return $this->evidenceHash;
    }

    /**
     * @return array{
     *     alias: string,
     *     physical_index: string,
     *     index_uuid: string,
     *     mapping_hash: string,
     *     relevant_settings_hash: string,
     *     primary_shards: list<array{shard: int, max_sequence_number: int, global_checkpoint: int}>,
     *     document_count: int
     * }
     */
    public function toIdentityArray(): array
    {
        return [
            'alias' => $this->alias,
            'physical_index' => $this->physicalIndex,
            'index_uuid' => $this->indexUuid,
            'mapping_hash' => $this->mappingHash,
            'relevant_settings_hash' => $this->relevantSettingsHash,
            'primary_shards' => $this->primaryShardBoundaries,
            'document_count' => $this->documentCount,
        ];
    }
}
