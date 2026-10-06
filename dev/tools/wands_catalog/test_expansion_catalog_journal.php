<?php
declare(strict_types=1);
require __DIR__ . '/expansion_catalog_journal.php';

function must(bool $ok, string $message): void { if (!$ok) { throw new RuntimeException($message); } }
$db = new PDO('sqlite::memory:', null, null, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
$db->exec('CREATE TABLE catalog_product_entity(entity_id INTEGER PRIMARY KEY,sku TEXT,type_id TEXT);
    INSERT INTO catalog_product_entity VALUES(1,"WANDS-000001","configurable"),(2,"other-product","simple"),(3,"WANDS-SYN-TEST","simple")');
$manager = new ExpansionCatalogJournal($db);
$old = ['entity_id' => '1', 'sku' => 'WANDS-000001', 'type_id' => 'simple'];
$after = [...$old, 'type_id' => 'configurable'];
$changed = ['table' => 'catalog_product_entity', 'selector' => ['entity_id' => '1'], 'before' => $old, 'after' => $after];
$inserted = ['table' => 'catalog_product_entity', 'selector' => ['entity_id' => '3'], 'before' => null,
    'after' => ['entity_id' => '3', 'sku' => 'WANDS-SYN-TEST', 'type_id' => 'simple']];
$db->beginTransaction(); $manager->compensate($changed); $manager->compensate($inserted); $db->commit();
must($db->query('SELECT type_id FROM catalog_product_entity WHERE entity_id=1')->fetchColumn() === 'simple', 'Original type not restored');
must((int)$db->query('SELECT COUNT(*) FROM catalog_product_entity WHERE entity_id=3')->fetchColumn() === 0, 'Exact addition not removed');
must($db->query('SELECT sku FROM catalog_product_entity WHERE entity_id=2')->fetchColumn() === 'other-product', 'Unrelated record changed');
// A later edit must abort the entire compensation, including prior row changes.
$db->exec('UPDATE catalog_product_entity SET type_id="configurable" WHERE entity_id=1;
    INSERT INTO catalog_product_entity VALUES(3,"WANDS-SYN-LATER-EDIT","simple")');
$db->beginTransaction();
try { $manager->compensate($changed); $manager->compensate($inserted); throw new RuntimeException('Drift was accepted'); }
catch (RuntimeException $e) { $db->rollBack(); must(str_contains($e->getMessage(), 'changed after'), 'Unexpected failure'); }
must($db->query('SELECT type_id FROM catalog_product_entity WHERE entity_id=1')->fetchColumn() === 'configurable', 'Partial inverse committed');
try { $manager->compensate($changed); throw new RuntimeException('Missing transaction accepted'); }
catch (RuntimeException $e) { must(str_contains($e->getMessage(), 'Transactional'), 'Missing transaction did not fail'); }
foreach ([['table' => 'sales_order', 'selector' => ['entity_id' => '1'], 'before' => $old, 'after' => $after],
          [...$changed, 'selector' => []], [...$changed, 'selector' => ['entity_id' => '2']]] as $bad) {
    try { $manager->validateOperation($bad); throw new RuntimeException('Invalid operation accepted'); }
    catch (RuntimeException $e) { must($e->getMessage() !== 'Invalid operation accepted', 'Unbounded inverse accepted'); }
}
echo "PASS: exact row restoration, exact new-row removal, unrelated preservation, drift abort, atomic rollback, transaction and scope checks\n";
