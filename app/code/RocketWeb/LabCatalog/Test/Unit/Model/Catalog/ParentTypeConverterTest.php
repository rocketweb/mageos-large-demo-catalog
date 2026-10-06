<?php
declare(strict_types=1);

namespace RocketWeb\LabCatalog\Test\Unit\Model\Catalog;

use PHPUnit\Framework\TestCase;
use RocketWeb\LabCatalog\Model\Catalog\ParentTypeConverter;

require_once dirname(__DIR__, 4) . '/Model/Catalog/ParentTypeConverter.php';

class ParentTypeConverterTest extends TestCase
{
    private function validate(array $children): void
    {
        $object=(new \ReflectionClass(ParentTypeConverter::class))->newInstanceWithoutConstructor();
        (new \ReflectionMethod($object,'validateRecord'))->invoke($object,[
            'sku'=>'WANDS-000001','source_product_id'=>'1','expected_type'=>'simple',
            'target_type'=>'configurable','child_skus'=>$children,
        ],1);
    }

    public function testAcceptedEnrichmentSupportsTwoChildFamilies(): void
    {
        $this->validate(['WANDS-000001-BLACK','WANDS-000001-WHITE']);
        $this->addToAssertionCount(1);
    }

    public function testOneChildCannotBeConverted(): void
    {
        $this->expectException(\RuntimeException::class);
        $this->validate(['WANDS-000001-BLACK']);
    }

    public function testForeignChildrenRemainRejected(): void
    {
        $this->expectException(\RuntimeException::class);
        $this->validate(['WANDS-000001-BLACK','WANDS-000002-WHITE']);
    }
}
