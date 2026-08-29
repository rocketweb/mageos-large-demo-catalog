<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\OpenSearch;

use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\ConfiguredOpenSearchClientProvider;
use MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch\IndexEvidenceCapture;
use OpenSearch\Client;
use PHPUnit\Framework\TestCase;
use UnexpectedValueException;

class IndexEvidenceCaptureTest extends TestCase
{
    private ConfiguredOpenSearchClientProvider $clientProvider;
    private Client $openSearchClient;

    protected function setUp(): void
    {
        $this->clientProvider = $this->createStub(ConfiguredOpenSearchClientProvider::class);
        $this->openSearchClient = $this->getMockBuilder(Client::class)
            ->disableOriginalConstructor()
            ->onlyMethods(['request'])
            ->getMock();
        $this->clientProvider
            ->method('get')
            ->willReturn($this->openSearchClient);
    }

    public function testCapturesCanonicalPhysicalIndexEvidenceFromPrimaryShards(): void
    {
        $physicalIndex = 'catalog_product_20260825';
        $mapping = [
            'properties' => [
                'name' => ['type' => 'text', 'analyzer' => 'catalog_text'],
                'category' => ['type' => 'keyword'],
            ],
        ];
        $settings = [
            'index' => [
                'uuid' => 'W7vVYb7eQ46J8AlnN4no2Q',
                'creation_date' => '1787625000000',
                'provided_name' => $physicalIndex,
                'version' => ['created' => '138227827'],
                'number_of_shards' => '2',
                'number_of_replicas' => '1',
                'analysis' => [
                    'analyzer' => [
                        'catalog_text' => ['type' => 'standard', 'stopwords' => '_english_'],
                    ],
                ],
                'similarity' => [
                    'catalog_bm25' => ['type' => 'BM25', 'k1' => '1.2'],
                ],
            ],
        ];
        $stats = [
            'indices' => [
                $physicalIndex => [
                    'primaries' => ['docs' => ['count' => 42]],
                    'shards' => [
                        '1' => [
                            [
                                'routing' => ['primary' => false],
                                'seq_no' => ['max_seq_no' => 18, 'global_checkpoint' => 17],
                            ],
                            [
                                'routing' => ['primary' => true],
                                'seq_no' => ['max_seq_no' => 20, 'global_checkpoint' => 20],
                            ],
                        ],
                        '0' => [
                            [
                                'routing' => ['primary' => true],
                                'seq_no' => ['max_seq_no' => 21, 'global_checkpoint' => 21],
                            ],
                        ],
                    ],
                ],
            ],
        ];

        $this->openSearchClient
            ->expects($this->exactly(4))
            ->method('request')
            ->willReturnCallback(
                static fn (string $method, string $path, array $attributes): array => match ([$method, $path]) {
                    ['GET', '/catalogsearch_fulltext/_alias'] => [
                        $physicalIndex => ['aliases' => ['catalogsearch_fulltext' => []]],
                    ],
                    ['GET', '/' . $physicalIndex . '/_mapping'] => [$physicalIndex => ['mappings' => $mapping]],
                    ['GET', '/' . $physicalIndex . '/_settings'] => [$physicalIndex => ['settings' => $settings]],
                    ['GET', '/' . $physicalIndex . '/_stats/docs'] => $stats,
                    default => self::fail(sprintf('Unexpected request %s %s', $method, $path)),
                }
            );

        $canonicalJson = new CanonicalJson();
        $evidence = (new IndexEvidenceCapture($this->clientProvider, $canonicalJson))
            ->capture('catalogsearch_fulltext');

        self::assertSame('catalogsearch_fulltext', $evidence->getAlias());
        self::assertSame($physicalIndex, $evidence->getPhysicalIndex());
        self::assertSame('W7vVYb7eQ46J8AlnN4no2Q', $evidence->getIndexUuid());
        self::assertSame($canonicalJson->hash($mapping), $evidence->getMappingHash());
        self::assertSame(42, $evidence->getDocumentCount());
        self::assertSame(
            [
                ['shard' => 0, 'max_sequence_number' => 21, 'global_checkpoint' => 21],
                ['shard' => 1, 'max_sequence_number' => 20, 'global_checkpoint' => 20],
            ],
            $evidence->getPrimaryShardBoundaries()
        );
        self::assertSame(
            $canonicalJson->hash([
                'analysis' => $settings['index']['analysis'],
                'number_of_shards' => '2',
                'similarity' => $settings['index']['similarity'],
            ]),
            $evidence->getRelevantSettingsHash()
        );
        self::assertSame(
            $canonicalJson->hash($evidence->toIdentityArray()),
            $evidence->getEvidenceHash()
        );
    }

    public function testRejectsWildcardTargetsBeforeCallingOpenSearch(): void
    {
        $this->openSearchClient
            ->expects($this->never())
            ->method('request');

        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('OpenSearch target must be a concrete safe alias or index name');

        (new IndexEvidenceCapture($this->clientProvider, new CanonicalJson()))
            ->capture('catalog*');
    }

    public function testRejectsAliasThatResolvesToMoreThanOnePhysicalIndex(): void
    {
        $this->openSearchClient
            ->expects($this->once())
            ->method('request')
            ->with('GET', '/catalogsearch_fulltext/_alias', [])
            ->willReturn([
                'catalog_product_a' => ['aliases' => ['catalogsearch_fulltext' => []]],
                'catalog_product_b' => ['aliases' => ['catalogsearch_fulltext' => []]],
            ]);

        $this->expectException(UnexpectedValueException::class);
        $this->expectExceptionMessage('Target alias must resolve to exactly one physical index');

        (new IndexEvidenceCapture($this->clientProvider, new CanonicalJson()))
            ->capture('catalogsearch_fulltext');
    }
}
