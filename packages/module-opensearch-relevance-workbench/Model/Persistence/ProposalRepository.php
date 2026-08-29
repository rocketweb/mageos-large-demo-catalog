<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Persistence;

use Magento\Framework\App\ResourceConnection;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\EvidenceReport;
use MageOS\OpenSearchRelevanceWorkbench\Model\Proposal\ProposalExport;
use RuntimeException;
use Throwable;
use UnexpectedValueException;

class ProposalRepository
{
    private const PROPOSAL_TABLE = 'osrw_proposal';
    private const AUDIT_TABLE = 'osrw_audit_event';

    public function __construct(
        private readonly ResourceConnection $resourceConnection,
        private readonly UuidGenerator $uuidGenerator,
        private readonly ProposalRecordFactory $recordFactory
    ) {
    }

    /**
     * @param list<string> $warnings
     */
    public function save(
        string $proposalUuid,
        string $experimentUuid,
        int $storeId,
        ProposalExport $export,
        EvidenceReport $evidence,
        array $warnings,
        int $actorId,
        string $createdAt,
        string $correlationId
    ): string {
        $existing = $this->getByExperimentId($experimentUuid);

        if ($existing !== null) {
            return $existing;
        }

        $records = $this->recordFactory->create(
            $proposalUuid,
            $experimentUuid,
            $storeId,
            $export,
            $evidence,
            $warnings,
            $actorId,
            $createdAt,
            $correlationId,
            $this->uuidGenerator->generate()
        );
        $connection = $this->resourceConnection->getConnection();
        $connection->beginTransaction();

        try {
            $connection->insert(
                $this->resourceConnection->getTableName(self::PROPOSAL_TABLE),
                $records->getProposal()
            );
            $connection->insert(
                $this->resourceConnection->getTableName(self::AUDIT_TABLE),
                $records->getAuditEvent()
            );
            $connection->commit();
        } catch (Throwable $exception) {
            $connection->rollBack();
            throw $exception;
        }

        return $proposalUuid;
    }

    public function getByExperimentId(string $experimentUuid): ?string
    {
        $connection = $this->resourceConnection->getConnection();
        $row = $connection->fetchRow(
            $connection->select()
                ->from(
                    $this->resourceConnection->getTableName(self::PROPOSAL_TABLE),
                    ['proposal_uuid']
                )
                ->where('source_experiment_uuid = ?', strtolower($experimentUuid))
                ->limit(1)
        );

        if (!is_array($row)) {
            return null;
        }

        $proposalUuid = $row['proposal_uuid'] ?? null;

        if (!is_string($proposalUuid) || $proposalUuid === '') {
            throw new UnexpectedValueException('Persisted proposal identity is invalid');
        }

        return $proposalUuid;
    }

    public function getArtifact(string $proposalUuid): ProposalExport
    {
        $connection = $this->resourceConnection->getConnection();
        $row = $connection->fetchRow(
            $connection->select()
                ->from($this->resourceConnection->getTableName(self::PROPOSAL_TABLE))
                ->where('proposal_uuid = ?', strtolower($proposalUuid))
                ->limit(1)
        );

        if (!is_array($row)) {
            throw new UnexpectedValueException('Review-only proposal does not exist');
        }

        $artifact = (string)$row['artifact_json'];
        $artifactHash = (string)$row['artifact_sha256'];

        if (!hash_equals($artifactHash, hash('sha256', $artifact))) {
            throw new RuntimeException('Persisted proposal artifact identity does not match its content');
        }

        $filename = 'osrw-proposal-' . strtolower($proposalUuid)
            . '-' . substr($artifactHash, 0, 12) . '.json';

        return new ProposalExport($artifact, $artifactHash, $filename);
    }

    /**
     * @return list<array<string, int|string>>
     */
    public function listRecent(int $limit = 20): array
    {
        $limit = max(1, min($limit, 100));
        $connection = $this->resourceConnection->getConnection();

        return array_values($connection->fetchAll(
            $connection->select()
                ->from(
                    $this->resourceConnection->getTableName(self::PROPOSAL_TABLE),
                    [
                        'proposal_uuid',
                        'store_id',
                        'source_experiment_uuid',
                        'target_type',
                        'artifact_sha256',
                        'created_by',
                        'created_at',
                    ]
                )
                ->order('created_at DESC')
                ->limit($limit)
        ));
    }
}
