<?php
declare(strict_types=1);
require __DIR__ . '/expansion_media.php';

function demand(bool $condition, string $message): void
{
    if (!$condition) { throw new RuntimeException($message); }
}
function mustFail(callable $operation, string $message): void
{
    try { $operation(); } catch (RuntimeException $error) {
        demand(str_contains($error->getMessage(), $message), 'Unexpected failure: ' . $error->getMessage());
        return;
    }
    throw new RuntimeException('Expected failure: ' . $message);
}
$root = sys_get_temp_dir() . '/wands-media-test-' . bin2hex(random_bytes(8));
mkdir($root . '/pub/media/catalog/product', 0700, true);
file_put_contents($root . '/pub/media/catalog/product/accepted.jpg', 'immutable accepted fixture bytes');
$db = new PDO('sqlite::memory:', null, null, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
$db->exec("CREATE TABLE catalog_product_entity(entity_id INTEGER PRIMARY KEY,sku TEXT);
CREATE TABLE catalog_product_website(product_id INT,website_id INT);
CREATE TABLE store_website(website_id INTEGER PRIMARY KEY,code TEXT);
CREATE TABLE eav_attribute(attribute_id INTEGER PRIMARY KEY,attribute_code TEXT);
CREATE TABLE catalog_product_entity_varchar(value_id INTEGER PRIMARY KEY,entity_id INT,attribute_id INT,store_id INT,value TEXT);
CREATE TABLE catalog_product_entity_media_gallery(value_id INTEGER PRIMARY KEY,value TEXT);
CREATE TABLE catalog_product_entity_media_gallery_value(record_id INTEGER PRIMARY KEY,value_id INT,entity_id INT,store_id INT,disabled INT);
INSERT INTO catalog_product_entity VALUES(1,'WANDS-SYN-SAMPLE'),(2,'UNRELATED');
INSERT INTO catalog_product_website VALUES(1,5),(2,1);
INSERT INTO store_website VALUES(5,'wands'),(1,'main');
INSERT INTO eav_attribute VALUES(1,'image'),(2,'small_image'),(3,'thumbnail');
INSERT INTO catalog_product_entity_varchar VALUES(1,1,1,0,'/accepted.jpg'),(2,1,2,0,'/accepted.jpg'),(3,1,3,0,'/accepted.jpg'),(4,1,1,2,'/old.jpg'),(5,2,1,0,'/other.jpg');
INSERT INTO catalog_product_entity_media_gallery VALUES(1,'/accepted.jpg'),(2,'/old.jpg'),(3,'/other.jpg');
INSERT INTO catalog_product_entity_media_gallery_value VALUES(1,1,1,0,1),(2,2,1,0,0),(3,3,2,0,0);");
$manager = new ExpansionMedia($db, $root);
$assignments = ['WANDS-SYN-SAMPLE' => ['sha256' => hash_file('sha256', $root . '/pub/media/catalog/product/accepted.jpg')]];
$state = fn(): array => [$db->query('SELECT * FROM catalog_product_entity_varchar ORDER BY value_id')->fetchAll(PDO::FETCH_ASSOC),
    $db->query('SELECT * FROM catalog_product_entity_media_gallery_value ORDER BY record_id')->fetchAll(PDO::FETCH_ASSOC)];
try {
    $before = $state();
    $inspection = $manager->inspect($assignments, 1);
    demand(count($inspection['operations']) === 3, 'Expected one override, old gallery hide and accepted image enable');
    demand($before === $state(), 'Inspection wrote data');
    mustFail(fn() => $manager->change($inspection['operations']), 'enclosing transaction');
    $db->beginTransaction();
    $manager->change($inspection['operations']);
    demand($manager->inspect($assignments, 1)['operations'] === [], 'Media target not reached');
    $after = $state();
    demand($before[0][4] === $after[0][4] && $before[1][2] === $after[1][2], 'Unrelated data changed');
    $manager->change($inspection['operations'], true);
    demand($state() === $before, 'Inverse did not restore exact original rows');
    $db->rollBack();
    $db->beginTransaction();
    $db->exec("UPDATE catalog_product_entity_varchar SET value='/concurrent.jpg' WHERE value_id=4");
    mustFail(fn() => $manager->change($inspection['operations']), 'changed since inspection');
    $db->rollBack();
    demand($state() === $before, 'Failed operation leaked changes');
    $db->exec('INSERT INTO catalog_product_website VALUES(1,1)');
    mustFail(fn() => $manager->inspect($assignments, 1), 'shared WANDS');
    $db->exec('DELETE FROM catalog_product_website WHERE product_id=1 AND website_id=1');
    mustFail(fn() => $manager->inspect(['WANDS-SYN-SAMPLE' => ['sha256' => str_repeat('0', 64)]], 1), 'differ from accepted');
    $db->exec('DELETE FROM catalog_product_entity_media_gallery_value WHERE record_id=1');
    mustFail(fn() => $manager->inspect($assignments, 1), 'absent from native gallery');
    $db->exec("INSERT INTO catalog_product_entity_media_gallery_value VALUES(1,1,1,0,1);
        CREATE TABLE catalog_product_entity_int(value_id INTEGER PRIMARY KEY,entity_id INT,attribute_id INT,store_id INT,value INT);
        INSERT INTO eav_attribute VALUES(4,'status');
        INSERT INTO catalog_product_entity VALUES(3,'WANDS-RETIRED');
        INSERT INTO catalog_product_website VALUES(3,5);
        INSERT INTO catalog_product_entity_int VALUES(1,3,4,0,2);");
    $excluded = $manager->inspect($assignments, 2, ['WANDS-RETIRED']);
    demand($excluded['verified_products'] === 1 && $excluded['excluded_disabled_skus'] === ['WANDS-RETIRED'], 'Retired imageless record not accounted for');
    $db->exec('UPDATE catalog_product_entity_int SET value=1 WHERE value_id=1');
    mustFail(fn() => $manager->inspect($assignments, 2, ['WANDS-RETIRED']), 'target is enabled');
    echo "PASS: read-only plan, exact apply/inverse, unrelated preservation, transaction gate, concurrency conflict, shared website, image hash, missing gallery rejection, disabled exclusion and enabled-exclusion rejection\n";
} finally {
    unlink($root . '/pub/media/catalog/product/accepted.jpg');
    foreach (['/pub/media/catalog/product', '/pub/media/catalog', '/pub/media', '/pub', ''] as $suffix) { rmdir($root . $suffix); }
}
