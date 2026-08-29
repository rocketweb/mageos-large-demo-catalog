<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\Persistence;

use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\UuidGenerator;
use PHPUnit\Framework\TestCase;

class UuidGeneratorTest extends TestCase
{
    public function testGeneratesDistinctVersionFourVariantOneUuids(): void
    {
        $generator = new UuidGenerator();
        $first = $generator->generate();
        $second = $generator->generate();

        self::assertMatchesRegularExpression(
            '/\A[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\z/',
            $first
        );
        self::assertNotSame($first, $second);
    }
}
