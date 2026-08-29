<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\QuerySnapshot;

use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\CuratedQueryMetadataFactory;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;

class CuratedQueryMetadataFactoryTest extends TestCase
{
    public function testAllowsOnlyBoundedMerchantCuratedScalarFields(): void
    {
        $queryHash = hash('sha256', 'winter boots');

        self::assertSame(
            [
                $queryHash => [
                    'brand_value' => [
                        'value' => 'Northwind',
                        'provenance' => 'MERCHANT_CURATED',
                    ],
                    'category_id' => [
                        'value' => '42',
                        'provenance' => 'MERCHANT_CURATED',
                    ],
                ],
            ],
            (new CuratedQueryMetadataFactory())->create([
                $queryHash => [
                    'category_id' => '42',
                    'brand_value' => '  Northwind  ',
                ],
            ])
        );
    }

    #[DataProvider('invalidMetadataProvider')]
    public function testRejectsUnapprovedOrNonScalarMetadata(array $metadata): void
    {
        $this->expectException(InvalidArgumentException::class);

        (new CuratedQueryMetadataFactory())->create($metadata);
    }

    /**
     * @return array<string, array{array<string, mixed>}>
     */
    public static function invalidMetadataProvider(): array
    {
        $queryHash = hash('sha256', 'winter boots');

        return [
            'unknown field' => [[$queryHash => ['price_range' => '10-20']]],
            'non-scalar value' => [[$queryHash => ['brand_value' => ['Northwind']]]],
            'invalid category identity' => [[$queryHash => ['category_id' => 'shoes']]],
            'unknown query identity' => [['winter boots' => ['brand_value' => 'Northwind']]],
        ];
    }
}
