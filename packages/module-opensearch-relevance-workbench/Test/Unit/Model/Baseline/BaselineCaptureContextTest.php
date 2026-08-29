<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\Baseline;

use InvalidArgumentException;
use LogicException;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineCaptureContext;
use PHPUnit\Framework\TestCase;
use RuntimeException;
use UnexpectedValueException;

class BaselineCaptureContextTest extends TestCase
{
    public function testCapturesOnlyWhileOperationIsActiveAndPreservesOrder(): void
    {
        $context = new BaselineCaptureContext();
        $context->record(['outside' => 'ignored']);

        $captures = $context->capture(2, static function () use ($context): void {
            $context->record(['query' => 'first']);
            $context->record(['query' => 'second']);
        });

        self::assertSame(
            [
                ['query' => 'first'],
                ['query' => 'second'],
            ],
            $captures
        );
    }

    public function testRejectsFewerMapperCallsThanExpected(): void
    {
        $context = new BaselineCaptureContext();

        $this->expectException(UnexpectedValueException::class);
        $this->expectExceptionMessage('Baseline capture observed an unexpected Mapper request count');

        $context->capture(2, static function () use ($context): void {
            $context->record(['query' => 'only-one']);
        });
    }

    public function testRejectsMoreMapperCallsThanExpected(): void
    {
        $context = new BaselineCaptureContext();

        $this->expectException(UnexpectedValueException::class);
        $this->expectExceptionMessage('Baseline capture exceeded its expected Mapper request count');

        $context->capture(1, static function () use ($context): void {
            $context->record(['query' => 'first']);
            $context->record(['query' => 'unexpected-second']);
        });
    }

    public function testRejectsNestedCapture(): void
    {
        $context = new BaselineCaptureContext();

        $this->expectException(LogicException::class);
        $this->expectExceptionMessage('Baseline capture context is already active');

        $context->capture(1, static function () use ($context): void {
            $context->capture(1, static function (): void {
            });
        });
    }

    public function testResetsContextAfterCapturedOperationThrows(): void
    {
        $context = new BaselineCaptureContext();

        try {
            $context->capture(1, static function () use ($context): void {
                $context->record(['query' => 'discarded']);
                throw new RuntimeException('probe failed');
            });
            self::fail('Expected captured operation to throw');
        } catch (RuntimeException $exception) {
            self::assertSame('probe failed', $exception->getMessage());
        }

        $captures = $context->capture(1, static function () use ($context): void {
            $context->record(['query' => 'fresh']);
        });

        self::assertSame([['query' => 'fresh']], $captures);
    }

    public function testRejectsUnboundedExpectedCaptureCount(): void
    {
        $context = new BaselineCaptureContext();

        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('Expected Mapper request count must be between 1 and 20');

        $context->capture(21, static function (): void {
        });
    }
}
