<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Configuration;

use DOMDocument;
use DOMElement;
use DOMXPath;
use PHPUnit\Framework\TestCase;

class DependencyInjectionTest extends TestCase
{
    public function testRegistersLateReadOnlyCapturePluginOnOpenSearchMapper(): void
    {
        $document = new DOMDocument();
        self::assertTrue($document->load(dirname(__DIR__, 3) . '/etc/di.xml'));
        $xpath = new DOMXPath($document);
        $plugins = $xpath->query(
            '/config/type[@name="Magento\OpenSearch\SearchAdapter\Mapper"]'
            . '/plugin[@name="mageos_opensearch_relevance_workbench_capture_mapped_query"]'
        );

        self::assertNotFalse($plugins);
        self::assertCount(1, $plugins);
        $plugin = $plugins->item(0);
        self::assertInstanceOf(DOMElement::class, $plugin);
        self::assertSame(
            'MageOS\OpenSearchRelevanceWorkbench\Plugin\OpenSearch\CaptureMappedQuery',
            $plugin->getAttribute('type')
        );
        self::assertSame('100000', $plugin->getAttribute('sortOrder'));
    }
}
