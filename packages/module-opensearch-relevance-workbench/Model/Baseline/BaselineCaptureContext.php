<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Baseline;

use InvalidArgumentException;
use LogicException;
use UnexpectedValueException;

class BaselineCaptureContext
{
    private const MAX_CAPTURE_COUNT = 20;

    private bool $active = false;

    private int $expectedCaptureCount = 0;

    /**
     * @var list<array<array-key, mixed>>
     */
    private array $captures = [];

    /**
     * @param callable(): void $operation
     * @return list<array<array-key, mixed>>
     */
    public function capture(int $expectedCaptureCount, callable $operation): array
    {
        if ($expectedCaptureCount < 1 || $expectedCaptureCount > self::MAX_CAPTURE_COUNT) {
            throw new InvalidArgumentException('Expected Mapper request count must be between 1 and 20');
        }

        if ($this->active) {
            throw new LogicException('Baseline capture context is already active');
        }

        $this->active = true;
        $this->expectedCaptureCount = $expectedCaptureCount;
        $this->captures = [];

        try {
            $operation();

            $this->assertExpectedCaptureCount();

            return $this->captures;
        } finally {
            $this->active = false;
            $this->expectedCaptureCount = 0;
            $this->captures = [];
        }
    }

    /**
     * @param array<array-key, mixed> $mappedQuery
     */
    public function record(array $mappedQuery): void
    {
        if (!$this->active) {
            return;
        }

        if (count($this->captures) >= $this->expectedCaptureCount) {
            throw new UnexpectedValueException(
                'Baseline capture exceeded its expected Mapper request count'
            );
        }

        $this->captures[] = $mappedQuery;
    }

    private function assertExpectedCaptureCount(): void
    {
        if (count($this->captures) !== $this->expectedCaptureCount) {
            throw new UnexpectedValueException(
                'Baseline capture observed an unexpected Mapper request count'
            );
        }
    }
}
