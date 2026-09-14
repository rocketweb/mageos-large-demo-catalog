<?php

declare(strict_types=1);

/** Compare normalized, store-zero values. No Magento dependency or writes. */
function wandsVerifyEnrichment(array $rows, array $values, array $metadata, array $links, callable $check): void
{
    $required = [];
    foreach ($rows as $sku => $row) {
        foreach ($row as $code => $expected) {
            if (!str_starts_with($code, 'lab_spec_')
                && !in_array($code, ['description', 'short_description', 'url_key'], true)) {
                continue;
            }
            if (str_starts_with($code, 'lab_spec_')) {
                $required[$code] = true;
            }
            $actual = $values[$sku][$code] ?? null;
            if ($expected === '') {
                $valid = $actual === null || $actual === '';
            } elseif (($metadata[$code]['backend_type'] ?? '') === 'decimal') {
                $valid = is_numeric($expected) && is_numeric($actual)
                    && is_finite((float)$actual) && abs((float)$expected - (float)$actual) < 0.00005;
            } else {
                $valid = $actual !== null && (string)$actual === (string)$expected;
            }
            $check($valid, 'Enriched value mismatch: ' . $sku . ':' . $code);
        }
        foreach (['related_skus', 'crosssell_skus', 'upsell_skus'] as $code) {
            if (!array_key_exists($code, $row)) {
                continue;
            }
            $expected = $row[$code] === '' ? [] : explode(',', $row[$code]);
            $actual = $links[$sku][$code] ?? [];
            sort($expected);
            sort($actual);
            $check($expected === $actual, 'Merchandising link mismatch: ' . $sku . ':' . $code);
        }
    }
    foreach (array_keys($required) as $code) {
        $check(isset($metadata[$code]), 'Missing specification attribute: ' . $code);
    }
    if (isset($required['lab_spec_disclosure'])) {
        $notice = $metadata['lab_spec_disclosure'] ?? [];
        $check(($notice['backend_type'] ?? '') === 'text'
            && (int)($notice['is_visible_on_front'] ?? 0) === 1
            && (int)($notice['is_comparable'] ?? 0) === 1,
            'Synthetic disclosure attribute must remain visible and comparable');
    }
}
