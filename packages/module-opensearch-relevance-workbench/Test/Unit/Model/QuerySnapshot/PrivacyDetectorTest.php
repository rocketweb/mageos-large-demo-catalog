<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\QuerySnapshot;

use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\PrivacyDetector;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;

class PrivacyDetectorTest extends TestCase
{
    /**
     * @return iterable<string, array{string, list<string>}>
     */
    public static function unsafeTerms(): iterable
    {
        yield 'email' => ['matt@example.com', ['EMAIL_ADDRESS']];
        yield 'phone' => ['call 317-555-0123', ['PHONE_NUMBER']];
        yield 'long numeric identifier' => ['order 12345678901', ['LONG_NUMERIC_IDENTIFIER']];
        yield 'control character' => ["boots\nadmin", ['CONTROL_CHARACTER']];
        yield 'blank' => ['  ', ['BLANK_TERM']];
    }

    #[DataProvider('unsafeTerms')]
    public function testClassifiesUnsafeTermsWithoutReturningTheirContent(
        string $term,
        array $expectedReasons
    ): void {
        $result = (new PrivacyDetector())->inspect($term, 128);

        self::assertFalse($result->isAllowed());
        self::assertSame($expectedReasons, $result->getReasonCodes());
        self::assertStringNotContainsString($term, implode(' ', $result->getReasonCodes()));
    }

    public function testAllowsOrdinaryCommerceSearchTerms(): void
    {
        $result = (new PrivacyDetector())->inspect('women’s waterproof hiking boots', 128);

        self::assertTrue($result->isAllowed());
        self::assertSame([], $result->getReasonCodes());
    }

    public function testRejectsOverLimitTerm(): void
    {
        $result = (new PrivacyDetector())->inspect(str_repeat('a', 129), 128);

        self::assertFalse($result->isAllowed());
        self::assertSame(['TERM_TOO_LONG'], $result->getReasonCodes());
    }
}
