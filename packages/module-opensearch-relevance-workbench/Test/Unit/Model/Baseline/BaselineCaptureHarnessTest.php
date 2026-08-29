<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\Baseline;

use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineCaptureContext;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineCaptureHarness;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineTemplateCompiler;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use PHPUnit\Framework\TestCase;
use UnexpectedValueException;

class BaselineCaptureHarnessTest extends TestCase
{
    private const FIRST_SENTINEL = 'osrw-744466dd-a552-44ed-9263-3da65221c5a4';
    private const SECOND_SENTINEL = 'osrw-96d12f79-9e90-4218-b633-f366033f247f';

    public function testCapturesCompilesAndValidatesFiveFreshNativeRequests(): void
    {
        $canonicalJson = new CanonicalJson();
        $context = new BaselineCaptureContext();
        $mappedQueryTexts = [];
        $queries = ['boots', 'red dress', 'MUG-001', 'café table', 'winter coat'];
        $mapQueryText = function (string $queryText) use ($context, &$mappedQueryTexts): void {
            $mappedQueryTexts[] = $queryText;
            $context->record($this->buildCapture($queryText));
        };

        $result = $this->harness($context, $canonicalJson)->capture(
            $mapQueryText,
            self::FIRST_SENTINEL,
            self::SECOND_SENTINEL,
            $queries
        );

        self::assertSame(
            [self::FIRST_SENTINEL, self::SECOND_SENTINEL, ...$queries],
            $mappedQueryTexts
        );
        self::assertSame($this->buildCapture('boots'), $result->getTemplate()->render('boots'));
        self::assertSame(
            array_map(
                fn (string $queryText): array => [
                    'query_text_hash' => $canonicalJson->hash($queryText),
                    'mapped_request_hash' => $canonicalJson->hash($this->buildCapture($queryText)),
                ],
                $queries
            ),
            $result->getValidationEvidence()
        );
    }

    public function testRejectsNativeRoundTripDifferenceWithoutDisclosingQuery(): void
    {
        $context = new BaselineCaptureContext();
        $queries = ['boots', 'red dress', 'private-search-term', 'café table', 'winter coat'];
        $mapQueryText = function (string $queryText) use ($context): void {
            $capture = $this->buildCapture($queryText);

            if ($queryText === 'private-search-term') {
                $capture['body']['timeout'] = '2s';
            }

            $context->record($capture);
        };

        try {
            $this->harness($context, new CanonicalJson())->capture(
                $mapQueryText,
                self::FIRST_SENTINEL,
                self::SECOND_SENTINEL,
                $queries
            );
            self::fail('Expected native round-trip difference');
        } catch (UnexpectedValueException $exception) {
            self::assertSame(
                'Baseline round-trip differs at validation sample 3',
                $exception->getMessage()
            );
            self::assertStringNotContainsString('private-search-term', $exception->getMessage());
        }
    }

    public function testRequiresFiveDistinctNonEmptyValidationQueriesBeforeMapping(): void
    {
        $context = new BaselineCaptureContext();
        $mappingCalls = 0;

        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('Baseline validation requires at least five distinct non-empty queries');

        try {
            $this->harness($context, new CanonicalJson())->capture(
                static function () use (&$mappingCalls): void {
                    $mappingCalls++;
                },
                self::FIRST_SENTINEL,
                self::SECOND_SENTINEL,
                ['boots', 'boots', 'dress', 'mug', 'coat']
            );
        } finally {
            self::assertSame(0, $mappingCalls);
        }
    }

    private function harness(
        BaselineCaptureContext $context,
        CanonicalJson $canonicalJson
    ): BaselineCaptureHarness {
        return new BaselineCaptureHarness(
            $context,
            new BaselineTemplateCompiler($canonicalJson),
            $canonicalJson
        );
    }

    /**
     * @return array{
     *     index: string,
     *     body: array{
     *         query: array{multi_match: array{query: string, fields: list<string>}},
     *         size: int
     *     },
     *     track_total_hits: bool
     * }
     */
    private function buildCapture(string $queryText): array
    {
        return [
            'index' => 'catalogsearch_fulltext',
            'body' => [
                'query' => [
                    'multi_match' => [
                        'query' => $queryText,
                        'fields' => ['name^3', 'sku'],
                    ],
                ],
                'size' => 20,
            ],
            'track_total_hits' => true,
        ];
    }
}
