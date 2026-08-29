<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Configuration;

use PHPUnit\Framework\TestCase;

class ToolingConfigurationTest extends TestCase
{
    public function testPhpStanDoesNotUsePlatformSpecificAbsoluteTemporaryDirectory(): void
    {
        $configuration = file_get_contents(dirname(__DIR__, 3) . '/phpstan.neon.dist');

        self::assertNotFalse($configuration);
        self::assertDoesNotMatchRegularExpression(
            '/^\s*tmpDir:\s*(?:\/|[A-Za-z]:[\\\\\/])/m',
            $configuration
        );
    }
}
