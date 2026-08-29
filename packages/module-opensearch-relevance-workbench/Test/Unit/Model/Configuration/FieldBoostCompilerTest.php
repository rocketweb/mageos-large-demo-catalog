<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\Configuration;

use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineTemplate;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\Configuration\FieldBoostCompiler;
use PHPUnit\Framework\TestCase;

class FieldBoostCompilerTest extends TestCase
{
    public function testCompilesOnlyMappedSearchableAllowlistedFields(): void
    {
        $baseline = new BaselineTemplate(
            [
                'index' => 'catalogsearch_fulltext',
                'body' => [
                    'query' => [
                        'bool' => [
                            'must' => [
                                ['multi_match' => [
                                    'query' => '{{queryText}}',
                                    'fields' => ['name^3', 'sku', 'description'],
                                ]],
                                ['simple_query_string' => [
                                    'query' => '{{queryText}}',
                                    'fields' => ['name^3', 'sku'],
                                ]],
                            ],
                        ],
                    ],
                ],
            ],
            [
                '/body/query/bool/must/0/multi_match/query',
                '/body/query/bool/must/1/simple_query_string/query',
            ],
            str_repeat('a', 64)
        );
        $compiler = new FieldBoostCompiler(new CanonicalJson());

        $candidate = $compiler->compile(
            $baseline,
            [
                'name' => ['searchable' => true, 'sensitive' => false, 'dynamic' => false, 'type' => 'text'],
                'sku' => ['searchable' => true, 'sensitive' => false, 'dynamic' => false, 'type' => 'keyword'],
                'description' => ['searchable' => true, 'sensitive' => false, 'dynamic' => false, 'type' => 'text'],
            ],
            ['name' => 5.0, 'sku' => 2.5]
        );

        self::assertSame(
            ['name^5', 'sku^2.5', 'description'],
            $candidate->getTemplate()['body']['query']['bool']['must'][0]['multi_match']['fields']
        );
        self::assertSame(
            ['name^5', 'sku^2.5'],
            $candidate->getTemplate()['body']['query']['bool']['must'][1]['simple_query_string']['fields']
        );
        self::assertSame(
            [
                'type' => 'FIELD_BOOST',
                'boosts' => ['name' => 5.0, 'sku' => 2.5],
            ],
            $candidate->getTransformation()
        );
        self::assertMatchesRegularExpression('/\A[0-9a-f]{64}\z/', $candidate->getConfigurationHash());
    }

    public function testCompilesStockMageOsPerFieldMatchClauses(): void
    {
        $baseline = new BaselineTemplate(
            [
                'index' => 'magento2_product_1_v1',
                'body' => [
                    'query' => [
                        'bool' => [
                            'should' => [
                                ['match' => ['name' => ['query' => '{{queryText}}', 'boost' => 3]]],
                                ['match' => ['sku' => ['query' => '{{queryText}}']]],
                                ['match_phrase_prefix' => [
                                    'name' => ['query' => '{{queryText}}', 'boost' => 4],
                                ]],
                            ],
                        ],
                    ],
                ],
            ],
            [
                '/body/query/bool/should/0/match/name/query',
                '/body/query/bool/should/1/match/sku/query',
                '/body/query/bool/should/2/match_phrase_prefix/name/query',
            ],
            str_repeat('a', 64)
        );

        $candidate = (new FieldBoostCompiler(new CanonicalJson()))->compile(
            $baseline,
            [
                'name' => ['searchable' => true, 'sensitive' => false, 'dynamic' => false, 'type' => 'text'],
                'sku' => ['searchable' => true, 'sensitive' => false, 'dynamic' => false, 'type' => 'text'],
            ],
            ['name' => 5.0, 'sku' => 2.5]
        );
        $should = $candidate->getTemplate()['body']['query']['bool']['should'];

        self::assertSame(5.0, $should[0]['match']['name']['boost']);
        self::assertSame(2.5, $should[1]['match']['sku']['boost']);
        self::assertSame(5.0, $should[2]['match_phrase_prefix']['name']['boost']);
        self::assertSame('{{queryText}}', $should[0]['match']['name']['query']);
    }

    public function testCandidateIdentityIncludesThePersistedBaselineIdentity(): void
    {
        $baseline = new BaselineTemplate(
            [
                'body' => [
                    'size' => 12,
                    'query' => ['match' => ['name' => ['query' => '{{queryText}}']]],
                ],
            ],
            ['/body/query/match/name/query'],
            str_repeat('a', 64)
        );
        $compiler = new FieldBoostCompiler(new CanonicalJson());
        $capabilities = [
            'name' => ['searchable' => true, 'sensitive' => false, 'dynamic' => false, 'type' => 'text'],
        ];

        $first = $compiler->compile($baseline, $capabilities, ['name' => 2.0], str_repeat('1', 64));
        $second = $compiler->compile($baseline, $capabilities, ['name' => 2.0], str_repeat('2', 64));

        self::assertNotSame($first->getConfigurationHash(), $second->getConfigurationHash());
    }

    /**
     * @return iterable<string, array{array<string, array<string, bool|string>>, array<string, float>, string}>
     */
    public static function invalidCapabilities(): iterable
    {
        yield 'unknown' => [[], ['secret' => 2.0], 'Candidate field is not in the approved mapping registry: secret'];
        yield 'not searchable' => [
            ['secret' => ['searchable' => false, 'sensitive' => false, 'dynamic' => false, 'type' => 'text']],
            ['secret' => 2.0],
            'Candidate field is not eligible for boosting: secret',
        ];
        yield 'sensitive' => [
            ['secret' => ['searchable' => true, 'sensitive' => true, 'dynamic' => false, 'type' => 'text']],
            ['secret' => 2.0],
            'Candidate field is not eligible for boosting: secret',
        ];
        yield 'dynamic' => [
            ['secret' => ['searchable' => true, 'sensitive' => false, 'dynamic' => true, 'type' => 'text']],
            ['secret' => 2.0],
            'Candidate field is not eligible for boosting: secret',
        ];
    }

    #[\PHPUnit\Framework\Attributes\DataProvider('invalidCapabilities')]
    public function testRejectsUnknownOrUnsafeFields(
        array $capabilities,
        array $boosts,
        string $message
    ): void {
        $baseline = new BaselineTemplate(
            ['body' => ['query' => ['multi_match' => ['query' => '{{queryText}}', 'fields' => ['secret']]]]],
            ['/body/query/multi_match/query'],
            str_repeat('a', 64)
        );

        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage($message);

        (new FieldBoostCompiler(new CanonicalJson()))->compile($baseline, $capabilities, $boosts);
    }

    public function testRejectsFieldThatDoesNotExistInCapturedQuery(): void
    {
        $baseline = new BaselineTemplate(
            ['body' => ['query' => ['match' => ['description' => '{{queryText}}']]]],
            ['/body/query/match/description'],
            str_repeat('a', 64)
        );

        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('Candidate boost does not match a captured query field: name');

        (new FieldBoostCompiler(new CanonicalJson()))->compile(
            $baseline,
            ['name' => ['searchable' => true, 'sensitive' => false, 'dynamic' => false, 'type' => 'text']],
            ['name' => 2.0]
        );
    }
}
