<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\Persistence;

use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineCaptureResult;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineTemplate;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\StockBaselineCapture;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\IndexEvidence;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\BaselineRecordFactory;
use PHPUnit\Framework\TestCase;

class BaselineRecordFactoryTest extends TestCase
{
    public function testCreatesImmutableEvidenceConfigurationAndAuditRecords(): void
    {
        $canonicalJson = new CanonicalJson();
        $templateValue = [
            'index' => 'magento2_product_1',
            'body' => [
                'query' => [
                    'match' => ['name' => ['query' => BaselineTemplate::QUERY_TEXT_VARIABLE]],
                ],
            ],
        ];
        $template = new BaselineTemplate(
            $templateValue,
            ['/body/query/match/name/query'],
            $canonicalJson->hash($templateValue)
        );
        $captureResult = new BaselineCaptureResult(
            $template,
            [
                [
                    'query_text_hash' => str_repeat('1', 64),
                    'mapped_request_hash' => str_repeat('2', 64),
                ],
            ]
        );
        $indexEvidence = new IndexEvidence(
            'magento2_product_1',
            'magento2_product_1_v3',
            'index-uuid',
            str_repeat('3', 64),
            str_repeat('4', 64),
            [['shard' => 0, 'max_sequence_number' => 10, 'global_checkpoint' => 10]],
            25,
            str_repeat('5', 64)
        );
        $capture = new StockBaselineCapture(
            $captureResult,
            $indexEvidence,
            [
                'name' => [
                    'searchable' => true,
                    'sensitive' => false,
                    'dynamic' => false,
                    'type' => 'text',
                ],
            ],
            [
                'index' => 'magento2_product_1_v3',
                'query' => $canonicalJson->encode($templateValue['body']),
                'searchPipeline' => '',
            ],
            str_repeat('6', 64)
        );

        $records = (new BaselineRecordFactory($canonicalJson))->create(
            $capture,
            1,
            '11111111-1111-4111-8111-111111111111',
            '22222222-2222-4222-8222-222222222222',
            '33333333-3333-4333-8333-333333333333',
            42,
            '2026-08-26T16:00:00+00:00',
            'baseline-correlation'
        );

        self::assertSame('magento2_product_1', $records->getIndexEvidence()['alias_name']);
        self::assertSame('magento2_product_1_v3', $records->getIndexEvidence()['physical_index']);
        self::assertSame('BASELINE', $records->getConfiguration()['kind']);
        self::assertSame('VALID', $records->getConfiguration()['validation_state']);
        self::assertSame(str_repeat('6', 64), $records->getConfiguration()['canonical_sha256']);
        self::assertStringContainsString(
            'field_capabilities',
            (string)$records->getConfiguration()['transformation_json']
        );
        self::assertSame('BASELINE_CAPTURED', $records->getAuditEvent()['action']);
        self::assertSame('BASELINE_ROUND_TRIP_VALID', $records->getAuditEvent()['reason_code']);
    }
}
