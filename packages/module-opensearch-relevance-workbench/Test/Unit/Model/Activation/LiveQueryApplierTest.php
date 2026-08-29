<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\Activation;

use Magento\Store\Api\Data\StoreInterface;
use Magento\Store\Model\StoreManagerInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Activation\LiveActivation;
use MageOS\OpenSearchRelevanceWorkbench\Model\Activation\LiveQueryApplier;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\LiveActivationRepository;
use PHPUnit\Framework\TestCase;

class LiveQueryApplierTest extends TestCase
{
    public function testAppliesTheCurrentStoreFieldBoostToMappedQueries(): void
    {
        $activation = new LiveActivation(
            '11111111-1111-4111-8111-111111111111',
            1,
            'APPLY',
            '22222222-2222-4222-8222-222222222222',
            '33333333-3333-4333-8333-333333333333',
            null,
            ['type' => 'FIELD_BOOST', 'boosts' => ['name' => 6.0, 'sku' => 2.5]],
            str_repeat('a', 64),
            str_repeat('b', 64),
            'catalog_product_1',
            7,
            '2026-08-28 12:00:00'
        );
        $repository = $this->createMock(LiveActivationRepository::class);
        $repository->expects(self::once())->method('getCurrent')->with(1)->willReturn($activation);
        $store = $this->createStub(StoreInterface::class);
        $store->method('getId')->willReturn(1);
        $storeManager = $this->createStub(StoreManagerInterface::class);
        $storeManager->method('getStore')->willReturn($store);
        $applier = new LiveQueryApplier($repository, $storeManager);

        $mapped = [
            'query' => [
                'bool' => [
                    'should' => [
                        ['multi_match' => ['query' => 'shoe', 'fields' => ['name^3', 'sku', 'description']]],
                        ['match' => ['name' => ['query' => 'shoe', 'boost' => 3]]],
                    ],
                ],
            ],
        ];
        $applied = $applier->apply($mapped);

        self::assertSame(
            ['name^6', 'sku^2.5', 'description'],
            $applied['query']['bool']['should'][0]['multi_match']['fields']
        );
        self::assertSame(6.0, $applied['query']['bool']['should'][1]['match']['name']['boost']);
    }

    public function testLeavesTheMappedQueryUnchangedWhenTheStoreUsesStockSearch(): void
    {
        $repository = $this->createMock(LiveActivationRepository::class);
        $repository->method('getCurrent')->with(1)->willReturn(null);
        $store = $this->createStub(StoreInterface::class);
        $store->method('getId')->willReturn(1);
        $storeManager = $this->createStub(StoreManagerInterface::class);
        $storeManager->method('getStore')->willReturn($store);
        $applier = new LiveQueryApplier($repository, $storeManager);
        $mapped = ['query' => ['match_all' => []]];

        self::assertSame($mapped, $applier->apply($mapped));
    }
}
