<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model;

use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use PHPUnit\Framework\TestCase;
use stdClass;

class CanonicalJsonTest extends TestCase
{
    public function testEncodesNestedObjectsWithStableKeyOrder(): void
    {
        $canonicalJson = new CanonicalJson();

        $encoded = $canonicalJson->encode([
            'z' => ['second' => 2, 'first' => 1],
            'a' => 'value',
        ]);

        self::assertSame('{"a":"value","z":{"first":1,"second":2}}', $encoded);
    }

    public function testPreservesListOrderAndNumericTypes(): void
    {
        $canonicalJson = new CanonicalJson();

        $encoded = $canonicalJson->encode([
            'values' => [2, 1.0, 0.5],
        ]);

        self::assertSame('{"values":[2,1.0,0.5]}', $encoded);
    }

    public function testPreservesObjectSemanticsForNumericKeys(): void
    {
        $canonicalJson = new CanonicalJson();

        $encoded = $canonicalJson->encode([
            1 => 'one',
            0 => 'zero',
        ]);

        self::assertSame('{"0":"zero","1":"one"}', $encoded);
    }

    public function testNormalizesUnicodeKeysAndValuesToNfc(): void
    {
        $canonicalJson = new CanonicalJson();

        $encoded = $canonicalJson->encode([
            "cafe\u{0301}" => "re\u{0301}sume\u{0301}",
        ]);

        self::assertSame('{"café":"résumé"}', $encoded);
    }

    public function testHashUsesCanonicalRepresentation(): void
    {
        $canonicalJson = new CanonicalJson();
        $first = ['store_id' => 2, 'entries' => [['query' => 'boots']]];
        $second = ['entries' => [['query' => 'boots']], 'store_id' => 2];

        self::assertSame($canonicalJson->hash($first), $canonicalJson->hash($second));
        self::assertSame(hash('sha256', $canonicalJson->encode($first)), $canonicalJson->hash($first));
    }

    public function testRejectsKeysThatCollideAfterUnicodeNormalization(): void
    {
        $canonicalJson = new CanonicalJson();

        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('Duplicate object key after Unicode normalization');

        $canonicalJson->encode([
            'café' => 1,
            "cafe\u{0301}" => 2,
        ]);
    }

    public function testRejectsNonJsonValues(): void
    {
        $canonicalJson = new CanonicalJson();

        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('Canonical JSON accepts only JSON values');

        $canonicalJson->encode(new stdClass());
    }
}
