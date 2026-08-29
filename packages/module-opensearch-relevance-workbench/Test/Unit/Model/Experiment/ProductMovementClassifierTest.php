<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\Experiment;

use MageOS\OpenSearchRelevanceWorkbench\Model\Experiment\ProductMovementClassifier;
use PHPUnit\Framework\TestCase;

class ProductMovementClassifierTest extends TestCase
{
    public function testClassifiesMovementAndKeepsUnavailableDocumentsVisible(): void
    {
        $rows = (new ProductMovementClassifier())->classify(
            ['a', 'b', 'c', 'missing'],
            ['b', 'a', 'd', 'missing'],
            [
                'a' => ['name' => 'Alpha', 'sku' => 'A'],
                'b' => ['name' => 'Bravo', 'sku' => 'B'],
                'c' => ['name' => 'Charlie', 'sku' => 'C'],
                'd' => ['name' => 'Delta', 'sku' => 'D'],
            ]
        );
        $byDocument = [];

        foreach ($rows as $row) {
            $byDocument[$row['document_id']] = $row;
        }

        self::assertSame(['b', 'a', 'd', 'missing', 'c'], array_column($rows, 'document_id'));
        self::assertSame('MOVED_UP', $byDocument['b']['movement']);
        self::assertSame(1, $byDocument['b']['rank_delta']);
        self::assertSame('MOVED_DOWN', $byDocument['a']['movement']);
        self::assertSame(-1, $byDocument['a']['rank_delta']);
        self::assertSame('ADDED', $byDocument['d']['movement']);
        self::assertSame('DROPPED', $byDocument['c']['movement']);
        self::assertSame('UNCHANGED', $byDocument['missing']['movement']);
        self::assertFalse($byDocument['missing']['available']);
        self::assertSame('Product unavailable', $byDocument['missing']['name']);
        self::assertSame('', $byDocument['missing']['sku']);
    }
}
