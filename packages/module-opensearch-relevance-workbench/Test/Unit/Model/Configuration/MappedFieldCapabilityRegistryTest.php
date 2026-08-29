<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\Configuration;

use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineTemplate;
use MageOS\OpenSearchRelevanceWorkbench\Model\Configuration\MappedFieldCapabilityRegistry;
use PHPUnit\Framework\TestCase;

class MappedFieldCapabilityRegistryTest extends TestCase
{
    public function testOffersOnlyExplicitMappedSearchableApprovedFieldsFromCapturedQuery(): void
    {
        $template = new BaselineTemplate(
            [
                'index' => 'magento2_product_1_v1',
                'body' => [
                    'query' => [
                        'bool' => [
                            'should' => [
                                ['match' => ['name' => ['query' => '{{queryText}}']]],
                                ['match' => ['sku' => ['query' => '{{queryText}}']]],
                                ['match' => ['manufacturer_value' => ['query' => '{{queryText}}']]],
                                ['match' => ['customer_email' => ['query' => '{{queryText}}']]],
                                ['match' => ['dynamic_field' => ['query' => '{{queryText}}']]],
                                ['match' => ['disabled' => ['query' => '{{queryText}}']]],
                            ],
                        ],
                    ],
                ],
            ],
            [],
            str_repeat('a', 64)
        );
        $mapping = [
            'properties' => [
                'name' => ['type' => 'text'],
                'sku' => ['type' => 'keyword'],
                'manufacturer_value' => ['type' => 'text'],
                'customer_email' => ['type' => 'text'],
                'disabled' => ['type' => 'text', 'index' => false],
            ],
        ];

        $capabilities = (new MappedFieldCapabilityRegistry())->build(
            $template,
            $mapping,
            ['name', 'sku', 'manufacturer', 'customer_email', 'disabled']
        );

        self::assertSame(
            [
                'manufacturer_value' => [
                    'searchable' => true,
                    'sensitive' => false,
                    'dynamic' => false,
                    'type' => 'text',
                ],
                'name' => [
                    'searchable' => true,
                    'sensitive' => false,
                    'dynamic' => false,
                    'type' => 'text',
                ],
                'sku' => [
                    'searchable' => true,
                    'sensitive' => false,
                    'dynamic' => false,
                    'type' => 'keyword',
                ],
            ],
            $capabilities
        );
    }

    public function testReadsFieldsListClausesAndIgnoresSourceProjectionFields(): void
    {
        $template = new BaselineTemplate(
            [
                'index' => 'catalog',
                'body' => [
                    '_source' => ['name', 'private_note'],
                    'query' => [
                        'multi_match' => [
                            'query' => '{{queryText}}',
                            'fields' => ['name^3', 'description'],
                        ],
                    ],
                ],
            ],
            [],
            str_repeat('a', 64)
        );

        $capabilities = (new MappedFieldCapabilityRegistry())->build(
            $template,
            [
                'properties' => [
                    'name' => ['type' => 'text'],
                    'description' => ['type' => 'text'],
                    'private_note' => ['type' => 'text'],
                ],
            ],
            ['name', 'description', 'private_note']
        );

        self::assertSame(['description', 'name'], array_keys($capabilities));
    }
}
