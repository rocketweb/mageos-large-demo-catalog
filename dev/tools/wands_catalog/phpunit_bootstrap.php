<?php

declare(strict_types=1);

// Use Mage-OS's test-only factory generator, not a compiled application cache.
$catalogRoot = dirname(__DIR__, 3);
$mageosRoot = getenv('WANDS_MAGEOS_ROOT') ?: $catalogRoot;
$unitBootstrap = rtrim($mageosRoot, '/') . '/dev/tests/unit/framework/bootstrap.php';
if (!is_readable($unitBootstrap)) {
    throw new RuntimeException('Set WANDS_MAGEOS_ROOT to a Mage-OS checkout with unit-test dependencies installed.');
}

$testDirectory = $catalogRoot . '/var/wands/phpunit/' . bin2hex(random_bytes(8));
if (!mkdir($testDirectory, 0700, true) && !is_dir($testDirectory)) {
    throw new RuntimeException('Cannot create the isolated catalog unit-test directory.');
}
define('TESTS_TEMP_DIR', $testDirectory);
require $unitBootstrap;
