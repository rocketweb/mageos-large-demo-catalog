<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\RemoteResource;

use MageOS\OpenSearchRelevanceWorkbench\Api\SearchRelevanceClientInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\BaselineConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\CandidateConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\ExperimentRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\HumanJudgmentRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\QuerySnapshotRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\RemoteArtifactRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\ApprovedQuerySnapshot;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\QuerySnapshotEntry;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\SnapshotPolicy;
use MageOS\OpenSearchRelevanceWorkbench\Model\RemoteResource\OwnedResourceCleanupGuard;
use MageOS\OpenSearchRelevanceWorkbench\Model\RemoteResource\OwnedResourceCleanupPreviewService;
use MageOS\OpenSearchRelevanceWorkbench\Model\RemoteResource\OwnedResourceNameFactory;
use MageOS\OpenSearchRelevanceWorkbench\Model\RemoteResource\QuerySetContentIdentityFactory;
use PHPUnit\Framework\TestCase;

class OwnedResourceCleanupPreviewServiceTest extends TestCase
{
    public function testExactBoundQuerySetIsEligibleInPreviewWithoutDeletion(): void
    {
        $snapshotUuid = '11111111-1111-4111-8111-111111111111';
        $remoteId = '22222222-2222-4222-8222-222222222222';
        $snapshot = new ApprovedQuerySnapshot(
            1,
            [
                new QuerySnapshotEntry(
                    1,
                    'boots',
                    hash('sha256', 'boots'),
                    10,
                    3,
                    '2026-08-26 12:00:00'
                ),
            ],
            new SnapshotPolicy(1, 10, 5, 15, false, 128, 'osrw-privacy-v1'),
            ['updated_at' => '2026-08-26 12:00:00', 'query_id' => 1],
            str_repeat('a', 64),
            1,
            '2026-08-26 13:00:00'
        );
        $nameFactory = new OwnedResourceNameFactory();
        $remoteRepository = $this->createMock(RemoteArtifactRepository::class);
        $remoteRepository->expects(self::once())->method('listBoundResources')->with(20)->willReturn([
            [
                'local_uuid' => $snapshotUuid,
                'remote_id' => $remoteId,
                'resource_type' => 'QUERY_SET',
                'resource_kind' => 'query-set',
            ],
        ]);
        $snapshotRepository = $this->createMock(QuerySnapshotRepository::class);
        $snapshotRepository->expects(self::once())->method('getApproved')->with($snapshotUuid)->willReturn($snapshot);
        $client = $this->createMock(SearchRelevanceClientInterface::class);
        $client->expects(self::once())->method('getQuerySet')->with($remoteId)->willReturn([
            'hits' => [
                'hits' => [[
                    '_id' => $remoteId,
                    '_source' => [
                        'name' => $nameFactory->create('query-set', $snapshotUuid),
                        'description' => 'Owned MageOS relevance workbench query snapshot',
                        'sampling' => 'manual',
                        'querySetQueries' => [['queryText' => 'boots']],
                    ],
                ]],
            ],
        ]);
        $service = new OwnedResourceCleanupPreviewService(
            $remoteRepository,
            $snapshotRepository,
            $this->createStub(BaselineConfigurationRepository::class),
            $this->createStub(CandidateConfigurationRepository::class),
            $this->createStub(HumanJudgmentRepository::class),
            $this->createStub(ExperimentRepository::class),
            $client,
            new QuerySetContentIdentityFactory(new CanonicalJson()),
            $nameFactory,
            new CanonicalJson(),
            new OwnedResourceCleanupGuard()
        );

        self::assertSame(
            [[
                'local_uuid' => $snapshotUuid,
                'remote_id' => $remoteId,
                'resource_type' => 'QUERY_SET',
                'resource_kind' => 'query-set',
                'remote_name' => $nameFactory->create('query-set', $snapshotUuid),
                'eligible' => true,
                'reason_codes' => [],
            ]],
            $service->preview()
        );
    }
}
