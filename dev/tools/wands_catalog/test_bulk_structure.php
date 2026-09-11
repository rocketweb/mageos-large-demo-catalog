<?php
declare(strict_types=1);
require __DIR__.'/bulk_structure.php';

$pdo = new PDO('sqlite::memory:', null, null, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
$pdo->exec('CREATE TABLE catalog_product_entity(entity_id INTEGER PRIMARY KEY,sku TEXT,type_id TEXT,has_options INT,required_options INT);
CREATE TABLE eav_entity_type(entity_type_id INT,entity_type_code TEXT);
CREATE TABLE eav_attribute(attribute_id INT,entity_type_id INT,attribute_code TEXT,backend_type TEXT);
CREATE TABLE eav_attribute_option(option_id INTEGER PRIMARY KEY AUTOINCREMENT,attribute_id INT,sort_order INT);
CREATE TABLE eav_attribute_option_value(value_id INTEGER PRIMARY KEY AUTOINCREMENT,option_id INT,store_id INT,value TEXT);
CREATE TABLE catalog_product_super_link(link_id INTEGER PRIMARY KEY,parent_id INT,product_id INT);
CREATE TABLE catalog_product_relation(parent_id INT,child_id INT);
CREATE TABLE catalog_product_super_attribute(product_super_attribute_id INTEGER PRIMARY KEY,product_id INT,attribute_id INT);
CREATE TABLE catalog_product_super_attribute_label(value_id INTEGER PRIMARY KEY,product_super_attribute_id INT,store_id INT,value TEXT);
CREATE TABLE catalog_product_bundle_selection(selection_id INT,product_id INT);
CREATE TABLE catalog_product_entity_int(value_id INT,entity_id INT,attribute_id INT,value INT);
INSERT INTO catalog_product_entity VALUES(1,"WANDS-000001","configurable",1,1),(2,"WANDS-000001-A","simple",0,0);
INSERT INTO eav_entity_type VALUES(4,"catalog_product");
INSERT INTO eav_attribute VALUES(100,4,"wands_size","int");
INSERT INTO catalog_product_super_link VALUES(1,1,2);
INSERT INTO catalog_product_relation VALUES(1,2);
INSERT INTO catalog_product_super_attribute VALUES(1,1,100);
INSERT INTO catalog_product_super_attribute_label VALUES(1,1,0,"Size");');
$structure = ['all_skus' => ['WANDS-000001','WANDS-000001-A'], 'attribute_options' => ['wands_size' => ['Small']],
    'retired_skus' => ['WANDS-000001-A'], 'conversions' => ['WANDS-000001'], 'parent_axes' => []];
$state = static function () use ($pdo): array {
    $tables = $pdo->query("SELECT name FROM sqlite_master WHERE type='table' AND name<>'sqlite_sequence' ORDER BY name")->fetchAll(PDO::FETCH_COLUMN);
    $result = [];
    foreach ($tables as $table) {
        $result[$table] = $pdo->query('SELECT * FROM '.$table)->fetchAll(PDO::FETCH_ASSOC);
    }
    return $result;
};
$before = $state();
$manager = new BulkCatalogStructure($pdo);
$plan = $manager->inspect($structure);
assert($state() === $before);
$pdo->beginTransaction();
$journal = $manager->apply($structure, $plan);
assert(count($journal) === 7);
assert($pdo->query('SELECT type_id FROM catalog_product_entity WHERE entity_id=1')->fetchColumn() === 'simple');
$manager->rollback($journal);
assert($state() === $before);
$pdo->commit();
$pdo->exec('INSERT INTO catalog_product_bundle_selection VALUES(1,2)');
$blocked = false;
try {
    $manager->inspect($structure);
} catch (RuntimeException $error) {
    $blocked = str_contains($error->getMessage(), 'bundle');
}
assert($blocked);
$pdo->exec('DELETE FROM catalog_product_bundle_selection; ALTER TABLE catalog_product_super_attribute ADD position INT DEFAULT 0; ALTER TABLE catalog_product_super_attribute_label ADD use_default INT DEFAULT 1; INSERT INTO eav_attribute VALUES(101,4,"wands_length","int")');
$axisStructure = ['parent_axes' => ['WANDS-000001' => ['wands_size','wands_length']]];
$beforeAxes = $state();
$axisManager = new BulkCatalogStructure($pdo);
$pdo->beginTransaction();
$axisJournal = $axisManager->reconcileAxes($axisStructure, ['WANDS-000001' => ['wands_size' => 'Size', 'wands_length' => 'Width']]);
assert((int)$pdo->query('SELECT product_super_attribute_id FROM catalog_product_super_attribute WHERE attribute_id=100')->fetchColumn() === 1);
assert((int)$pdo->query('SELECT COUNT(*) FROM catalog_product_super_attribute')->fetchColumn() === 2);
$axisManager->rollback($axisJournal);
assert($state() === $beforeAxes);
$pdo->commit();
echo "Structure inspect, apply, exact inverse, bundle guard and ID-preserving axis reconciliation passed\n";
