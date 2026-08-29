<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot;

use InvalidArgumentException;

class PrivacyDetector
{
    public function inspect(string $queryText, int $maximumLength): PrivacyInspection
    {
        if ($maximumLength < 1) {
            throw new InvalidArgumentException('Maximum query length must be positive');
        }

        $reasonCodes = [];

        if (trim($queryText) === '') {
            $reasonCodes[] = 'BLANK_TERM';
        } elseif (preg_match('/[[:cntrl:]]/u', $queryText) === 1) {
            $reasonCodes[] = 'CONTROL_CHARACTER';
        } elseif (mb_strlen($queryText) > $maximumLength) {
            $reasonCodes[] = 'TERM_TOO_LONG';
        } elseif (filter_var($queryText, FILTER_VALIDATE_EMAIL) !== false) {
            $reasonCodes[] = 'EMAIL_ADDRESS';
        } elseif (
            preg_match(
                '/(?<!\d)(?:\+?\d{1,3}[-.\s])?(?:\(\d{3}\)|\d{3})[-.\s]\d{3}[-.\s]\d{4}(?!\d)/',
                $queryText
            ) === 1
        ) {
            $reasonCodes[] = 'PHONE_NUMBER';
        } elseif (preg_match('/(?<!\d)\d{9,}(?!\d)/', $queryText) === 1) {
            $reasonCodes[] = 'LONG_NUMERIC_IDENTIFIER';
        }

        return new PrivacyInspection($reasonCodes);
    }
}
