<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Configuration;

use DOMDocument;
use DOMElement;
use DOMXPath;
use PHPUnit\Framework\TestCase;

class DeclarativeSchemaTest extends TestCase
{
    /**
     * @return list<string>
     */
    private function requiredTables(): array
    {
        return [
            'osrw_snapshot_schedule',
            'osrw_query_snapshot',
            'osrw_query_snapshot_entry',
            'osrw_index_evidence',
            'osrw_search_configuration',
            'osrw_human_rating',
            'osrw_judgment_run',
            'osrw_experiment',
            'osrw_proposal',
            'osrw_live_activation',
            'osrw_live_state',
            'osrw_audit_event',
        ];
    }

    public function testDeclaresAllCanonicalPhaseOneTables(): void
    {
        $document = new DOMDocument();
        self::assertTrue($document->load(dirname(__DIR__, 3) . '/etc/db_schema.xml'));
        self::assertSame(
            'urn:magento:framework:Setup/Declaration/Schema/etc/schema.xsd',
            $document->documentElement?->getAttributeNS(
                'http://www.w3.org/2001/XMLSchema-instance',
                'noNamespaceSchemaLocation'
            )
        );
        $xpath = new DOMXPath($document);

        foreach ($this->requiredTables() as $tableName) {
            $tables = $xpath->query('/schema/table[@name="' . $tableName . '"]');
            self::assertNotFalse($tables);
            self::assertCount(1, $tables, 'Missing declarative table ' . $tableName);
        }
    }

    public function testSnapshotEntriesCascadeOnlyWithTheirOwnedSnapshot(): void
    {
        $document = new DOMDocument();
        self::assertTrue($document->load(dirname(__DIR__, 3) . '/etc/db_schema.xml'));
        $xpath = new DOMXPath($document);
        $xpath->registerNamespace('xsi', 'http://www.w3.org/2001/XMLSchema-instance');
        $constraints = $xpath->query(
            '/schema/table[@name="osrw_query_snapshot_entry"]'
            . '/constraint[@xsi:type="foreign" and @referenceTable="osrw_query_snapshot"]'
        );

        self::assertNotFalse($constraints);
        self::assertCount(1, $constraints);
        $constraint = $constraints->item(0);
        self::assertInstanceOf(DOMElement::class, $constraint);
        self::assertSame('CASCADE', $constraint->getAttribute('onDelete'));
    }

    public function testLiveConfigurationTablesContainOnlyBoundedApplicationState(): void
    {
        $document = new DOMDocument();
        self::assertTrue($document->load(dirname(__DIR__, 3) . '/etc/db_schema.xml'));
        $xpath = new DOMXPath($document);
        $columns = $xpath->query(
            '/schema/table[@name="osrw_live_activation" or @name="osrw_live_state"]/column'
        );
        self::assertNotFalse($columns);

        $columnNames = [];

        foreach ($columns as $column) {
            self::assertInstanceOf(DOMElement::class, $column);
            $columnNames[] = $column->getAttribute('name');
            self::assertDoesNotMatchRegularExpression(
                '/credential|api_key|provider_token|raw_vector|password|secret/i',
                $column->getAttribute('name')
            );
        }

        self::assertContains('transformation_json', $columnNames);
        self::assertContains('candidate_sha256', $columnNames);
        self::assertContains('activation_uuid', $columnNames);
    }

    public function testDraftSnapshotsKeepTheirApprovedScheduleProvenance(): void
    {
        $document = new DOMDocument();
        self::assertTrue($document->load(dirname(__DIR__, 3) . '/etc/db_schema.xml'));
        $xpath = new DOMXPath($document);
        $xpath->registerNamespace('xsi', 'http://www.w3.org/2001/XMLSchema-instance');
        $columns = $xpath->query(
            '/schema/table[@name="osrw_query_snapshot"]/column[@name="schedule_uuid"]'
        );
        $constraints = $xpath->query(
            '/schema/table[@name="osrw_query_snapshot"]'
            . '/constraint[@xsi:type="foreign" and @referenceTable="osrw_snapshot_schedule"]'
        );

        self::assertNotFalse($columns);
        self::assertCount(1, $columns);
        self::assertNotFalse($constraints);
        self::assertCount(1, $constraints);
    }
}
