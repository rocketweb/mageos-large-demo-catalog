<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\Persistence;

use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\EvidenceReport;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\ProposalRecordFactory;
use MageOS\OpenSearchRelevanceWorkbench\Model\Proposal\ProposalExporter;
use PHPUnit\Framework\TestCase;

class ProposalRecordFactoryTest extends TestCase
{
    public function testCreatesReviewOnlyProposalAndAuditRecords(): void
    {
        $canonicalJson = new CanonicalJson();
        $evidence = new EvidenceReport('NDCG@10', 0.4, 0.6, 0.2, 1.0, [], 'WINNER', []);
        $proposalId = '11111111-1111-4111-8111-111111111111';
        $experimentId = '22222222-2222-4222-8222-222222222222';
        $warnings = ['Offline evidence does not establish revenue lift.'];
        $export = (new ProposalExporter($canonicalJson))->export(
            $proposalId,
            '2026-08-26T19:00:00+00:00',
            1,
            $experimentId,
            str_repeat('a', 64),
            str_repeat('b', 64),
            str_repeat('c', 64),
            str_repeat('d', 64),
            str_repeat('e', 64),
            ['type' => 'FIELD_BOOST', 'boosts' => ['name' => 5.0]],
            $evidence,
            $warnings
        );
        $records = (new ProposalRecordFactory($canonicalJson))->create(
            $proposalId,
            $experimentId,
            1,
            $export,
            $evidence,
            $warnings,
            42,
            '2026-08-26T19:00:00+00:00',
            'proposal-correlation',
            '33333333-3333-4333-8333-333333333333'
        );

        self::assertSame('review_only', $records->getProposal()['target_type']);
        self::assertSame($export->getArtifactHash(), $records->getProposal()['artifact_sha256']);
        self::assertSame('PROPOSAL_EXPORTED', $records->getAuditEvent()['action']);
        self::assertSame('REVIEW_ONLY_ARTIFACT_CREATED', $records->getAuditEvent()['reason_code']);
    }
}
