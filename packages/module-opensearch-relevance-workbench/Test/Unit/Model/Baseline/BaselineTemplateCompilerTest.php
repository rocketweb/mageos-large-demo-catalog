<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\Baseline;

use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineTemplateCompiler;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use PHPUnit\Framework\TestCase;
use UnexpectedValueException;

class BaselineTemplateCompilerTest extends TestCase
{
    private const FIRST_SENTINEL = 'osrw-4bb2c857-7e69-4de8-84d5-1ed3bbedfd5a';
    private const SECOND_SENTINEL = 'osrw-fb1fb5c5-b55e-421f-b2d4-87cd2118cb68';

    public function testCompilesExactSentinelChangesAndRendersFiveQueries(): void
    {
        $firstCapture = $this->buildCapture(self::FIRST_SENTINEL);
        $secondCapture = [
            'body' => [
                'sort' => $firstCapture['body']['sort'],
                'query' => [
                    'bool' => [
                        'filter' => $firstCapture['body']['query']['bool']['filter'],
                        'must' => [
                            [
                                'multi_match' => [
                                    'fields' => ['name^3', 'sku'],
                                    'query' => self::SECOND_SENTINEL,
                                ],
                            ],
                            ['match_phrase' => ['name' => self::SECOND_SENTINEL]],
                        ],
                    ],
                ],
            ],
            'index' => 'catalogsearch_fulltext',
            'params' => ['preference' => 'store-1'],
        ];

        $template = $this->compiler()->compile(
            $firstCapture,
            self::FIRST_SENTINEL,
            $secondCapture,
            self::SECOND_SENTINEL
        );

        self::assertSame(
            [
                '/body/query/bool/must/0/multi_match/query',
                '/body/query/bool/must/1/match_phrase/name',
            ],
            $template->getQueryTextPaths()
        );
        self::assertSame(
            hash('sha256', (new CanonicalJson())->encode($template->getTemplate())),
            $template->getTemplateHash()
        );

        foreach (['boots', 'red dress', 'MUG-001', 'café table', '{{queryText}}'] as $queryText) {
            $expected = $this->buildCapture($queryText);

            self::assertSame($expected, $template->render($queryText));
        }
    }

    public function testProducesStableHashWhenObjectKeyOrderChanges(): void
    {
        $compiler = $this->compiler();
        $first = $compiler->compile(
            ['index' => 'catalog', 'body' => ['query' => self::FIRST_SENTINEL, 'size' => 10]],
            self::FIRST_SENTINEL,
            ['body' => ['size' => 10, 'query' => self::SECOND_SENTINEL], 'index' => 'catalog'],
            self::SECOND_SENTINEL
        );
        $second = $compiler->compile(
            ['body' => ['size' => 10, 'query' => self::FIRST_SENTINEL], 'index' => 'catalog'],
            self::FIRST_SENTINEL,
            ['index' => 'catalog', 'body' => ['query' => self::SECOND_SENTINEL, 'size' => 10]],
            self::SECOND_SENTINEL
        );

        self::assertSame($first->getTemplateHash(), $second->getTemplateHash());
        self::assertSame($first->getQueryTextPaths(), $second->getQueryTextPaths());
    }

    public function testRejectsNondeterministicScalarChangeWithoutDisclosingValues(): void
    {
        try {
            $this->compiler()->compile(
                ['body' => ['preference' => 'private-first-value']],
                self::FIRST_SENTINEL,
                ['body' => ['preference' => 'private-second-value']],
                self::SECOND_SENTINEL
            );
            self::fail('Expected nondeterministic capture to be rejected');
        } catch (UnexpectedValueException $exception) {
            self::assertSame('Baseline captures differ at path /body/preference', $exception->getMessage());
            self::assertStringNotContainsString('private-first-value', $exception->getMessage());
            self::assertStringNotContainsString('private-second-value', $exception->getMessage());
        }
    }

    public function testEscapesDifferencePathAsJsonPointer(): void
    {
        $this->expectException(UnexpectedValueException::class);
        $this->expectExceptionMessage('Baseline captures differ at path /secret~1value~0token');

        $this->compiler()->compile(
            ['secret/value~token' => 1],
            self::FIRST_SENTINEL,
            ['secret/value~token' => 2],
            self::SECOND_SENTINEL
        );
    }

    public function testRejectsStructuralKeyChange(): void
    {
        $this->expectException(UnexpectedValueException::class);
        $this->expectExceptionMessage('Baseline captures differ at path /body');

        $this->compiler()->compile(
            ['body' => ['query' => self::FIRST_SENTINEL]],
            self::FIRST_SENTINEL,
            ['body' => ['query' => self::SECOND_SENTINEL, 'timeout' => '1s']],
            self::SECOND_SENTINEL
        );
    }

    public function testRejectsStructuralListChange(): void
    {
        $this->expectException(UnexpectedValueException::class);
        $this->expectExceptionMessage('Baseline captures differ at path /body/must');

        $this->compiler()->compile(
            ['body' => ['must' => [self::FIRST_SENTINEL]]],
            self::FIRST_SENTINEL,
            ['body' => ['must' => [self::SECOND_SENTINEL, ['term' => ['status' => 1]]]]],
            self::SECOND_SENTINEL
        );
    }

    public function testRejectsEmbeddedSentinelChange(): void
    {
        $this->expectException(UnexpectedValueException::class);
        $this->expectExceptionMessage('Baseline captures differ at path /body/query');

        $this->compiler()->compile(
            ['body' => ['query' => 'name:' . self::FIRST_SENTINEL]],
            self::FIRST_SENTINEL,
            ['body' => ['query' => 'name:' . self::SECOND_SENTINEL]],
            self::SECOND_SENTINEL
        );
    }

    public function testRejectsCaptureWithoutExactSentinelChange(): void
    {
        $this->expectException(UnexpectedValueException::class);
        $this->expectExceptionMessage('Baseline captures contain no exact query sentinel change');

        $this->compiler()->compile(
            ['body' => ['size' => 10]],
            self::FIRST_SENTINEL,
            ['body' => ['size' => 10]],
            self::SECOND_SENTINEL
        );
    }

    public function testRejectsReservedMustacheVariableOutsideQueryPath(): void
    {
        $this->expectException(UnexpectedValueException::class);
        $this->expectExceptionMessage('Baseline capture contains reserved query variable at path /body/literal');

        $this->compiler()->compile(
            ['body' => ['query' => self::FIRST_SENTINEL, 'literal' => '{{queryText}}']],
            self::FIRST_SENTINEL,
            ['body' => ['query' => self::SECOND_SENTINEL, 'literal' => '{{queryText}}']],
            self::SECOND_SENTINEL
        );
    }

    public function testRejectsSentinelCollisionOutsideQueryChange(): void
    {
        $this->expectException(UnexpectedValueException::class);
        $this->expectExceptionMessage('Baseline sentinel collision at path /body/literal');

        $this->compiler()->compile(
            ['body' => ['query' => self::FIRST_SENTINEL, 'literal' => self::FIRST_SENTINEL]],
            self::FIRST_SENTINEL,
            ['body' => ['query' => self::SECOND_SENTINEL, 'literal' => self::FIRST_SENTINEL]],
            self::SECOND_SENTINEL
        );
    }

    public function testRejectsEmptySentinel(): void
    {
        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('Baseline sentinels must be non-empty and distinct');

        $this->compiler()->compile([], '', [], self::SECOND_SENTINEL);
    }

    public function testRejectsEqualSentinels(): void
    {
        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('Baseline sentinels must be non-empty and distinct');

        $this->compiler()->compile([], self::FIRST_SENTINEL, [], self::FIRST_SENTINEL);
    }

    public function testRejectsReservedMustacheVariableAsSentinel(): void
    {
        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('Baseline sentinels must not use the reserved query variable');

        $this->compiler()->compile(
            ['query' => '{{queryText}}'],
            '{{queryText}}',
            ['query' => self::SECOND_SENTINEL],
            self::SECOND_SENTINEL
        );
    }

    private function compiler(): BaselineTemplateCompiler
    {
        return new BaselineTemplateCompiler(new CanonicalJson());
    }

    /**
     * @return array{
     *     index: string,
     *     params: array{preference: string},
     *     body: array{
     *         query: array{bool: array{
     *             must: list<array<string, array<string, string|list<string>>>>,
     *             filter: list<array{term: array{visibility: int}}>
     *         }},
     *         sort: list<array{entity_id: string}>
     *     }
     * }
     */
    private function buildCapture(string $queryText): array
    {
        return [
            'index' => 'catalogsearch_fulltext',
            'params' => ['preference' => 'store-1'],
            'body' => [
                'query' => [
                    'bool' => [
                        'must' => [
                            [
                                'multi_match' => [
                                    'query' => $queryText,
                                    'fields' => ['name^3', 'sku'],
                                ],
                            ],
                            ['match_phrase' => ['name' => $queryText]],
                        ],
                        'filter' => [
                            ['term' => ['visibility' => 4]],
                        ],
                    ],
                ],
                'sort' => [['entity_id' => 'asc']],
            ],
        ];
    }
}
