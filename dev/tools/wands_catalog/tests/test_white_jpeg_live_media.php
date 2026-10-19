<?php
declare(strict_types=1);
require __DIR__ . '/../white_jpeg_live_media.php';

function checkLive(bool $value, string $message): void { if (!$value) { throw new RuntimeException($message); } }
function fixtureLive(): array {
    $db = new PDO('sqlite::memory:', null, null, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    $db->exec("CREATE TABLE catalog_product_entity_varchar(value_id INTEGER PRIMARY KEY,entity_id INT,attribute_id INT,store_id INT,value TEXT);
        CREATE TABLE catalog_product_entity_media_gallery(value_id INTEGER PRIMARY KEY AUTOINCREMENT,attribute_id INT,value TEXT,media_type TEXT,disabled INT);
        CREATE TABLE catalog_product_entity_media_gallery_value(record_id INTEGER PRIMARY KEY,entity_id INT,value_id INT,label TEXT,position INT,disabled INT);
        CREATE TABLE catalog_product_entity_media_gallery_value_to_entity(value_id INT,entity_id INT,PRIMARY KEY(value_id,entity_id));
        INSERT INTO catalog_product_entity_media_gallery VALUES(1,90,'/a/a/old.jpg','image',0);
        INSERT INTO catalog_product_entity_media_gallery_value VALUES(1,10,1,'Product',1,0),(2,20,1,'QA control',2,0);
        INSERT INTO catalog_product_entity_media_gallery_value_to_entity VALUES(1,10),(1,20);
        INSERT INTO catalog_product_entity_varchar VALUES(1,10,87,0,'/a/a/old.jpg'),(2,10,88,0,'/a/a/old.jpg'),(3,10,89,0,'/a/a/old.jpg'),(4,10,87,2,'/a/a/old.jpg'),(5,20,87,0,'/a/a/old.jpg');");
    $roles = [];
    foreach ($db->query('SELECT * FROM catalog_product_entity_varchar WHERE entity_id=10', PDO::FETCH_ASSOC) as $row) {
        $roles[] = ['value_id' => $row['value_id'], 'entity_id' => 10, 'attribute_id' => $row['attribute_id'],
            'store_id' => $row['store_id'], 'before' => $row['value'], 'after' => '/b/b/new.jpg'];
    }
    $master = $db->query('SELECT * FROM catalog_product_entity_media_gallery', PDO::FETCH_ASSOC)->fetch();
    return [$db, ['target' => 'https://latest.rocketcode.com/', 'roles' => $roles,
        'galleries' => [1 => ['before' => $master, 'after' => '/b/b/new.jpg', 'records' => [['record_id' => 1, 'entity_id' => 10]], 'entities' => [10]]]]];
}

$directory = sys_get_temp_dir() . '/white-live-test-' . bin2hex(random_bytes(6));mkdir($directory, 0700);
try {
    [$db, $plan] = fixtureLive();
    $beforeRoles = $db->query('SELECT * FROM catalog_product_entity_varchar ORDER BY value_id')->fetchAll(PDO::FETCH_ASSOC);
    $beforeRecords = $db->query('SELECT * FROM catalog_product_entity_media_gallery_value ORDER BY record_id')->fetchAll(PDO::FETCH_ASSOC);
    $applied = whiteLiveChange($db, $plan, $directory . '/apply.json');
    checkLive($applied['committed'], 'Apply did not commit');
    checkLive((int)$db->query("SELECT count(*) FROM catalog_product_entity_varchar WHERE entity_id=10 AND value='/b/b/new.jpg'")->fetchColumn() === 4, 'Default or store-specific roles missing');
    checkLive($db->query('SELECT value FROM catalog_product_entity_varchar WHERE value_id=5')->fetchColumn() === '/a/a/old.jpg', 'QA role changed');
    checkLive((int)$db->query('SELECT value_id FROM catalog_product_entity_media_gallery_value WHERE record_id=2')->fetchColumn() === 1, 'Shared QA gallery changed');
    checkLive((int)$db->query('SELECT value_id FROM catalog_product_entity_media_gallery_value_to_entity WHERE entity_id=20')->fetchColumn() === 1, 'Shared QA association changed');
    checkLive($db->query('SELECT value FROM catalog_product_entity_media_gallery WHERE value_id=1')->fetchColumn() === '/a/a/old.jpg', 'Original gallery master changed');
    whiteLiveChange($db, $plan, $directory . '/rollback.json', true, $applied);
    checkLive($db->query('SELECT * FROM catalog_product_entity_varchar ORDER BY value_id')->fetchAll(PDO::FETCH_ASSOC) === $beforeRoles, 'Role rollback differs');
    checkLive($db->query('SELECT * FROM catalog_product_entity_media_gallery_value ORDER BY record_id')->fetchAll(PDO::FETCH_ASSOC) === $beforeRecords, 'Gallery metadata rollback differs');
    checkLive((int)$db->query('SELECT count(*) FROM catalog_product_entity_media_gallery_value_to_entity WHERE value_id=1')->fetchColumn() === 2, 'Gallery links rollback differs');
    [$db, $plan] = fixtureLive();$db->exec("UPDATE catalog_product_entity_varchar SET value='user edit' WHERE value_id=2");
    $failed = false;
    try { whiteLiveChange($db, $plan, $directory . '/drift.json'); } catch (RuntimeException $e) { $failed = str_contains($e->getMessage(), 'drift'); }
    checkLive($failed && !$db->inTransaction(), 'Drift did not stop and roll back');
    checkLive((int)$db->query('SELECT count(*) FROM catalog_product_entity_media_gallery')->fetchColumn() === 1, 'Failed transaction leaked gallery master');
    checkLive($db->query('SELECT value FROM catalog_product_entity_varchar WHERE value_id=1')->fetchColumn() === '/a/a/old.jpg', 'Failed transaction leaked role update');
    echo json_encode(['passed' => true, 'checks' => 13, 'rollback_verified' => true, 'shared_qa_preserved' => true, 'drift_transaction_rollback_verified' => true]) . "\n";
} finally { foreach (glob($directory . '/*') as $path) { unlink($path); } rmdir($directory); }
