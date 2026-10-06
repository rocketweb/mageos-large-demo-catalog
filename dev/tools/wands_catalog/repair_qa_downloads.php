<?php
declare(strict_types=1);
require __DIR__ . '/expansion_catalog_journal.php';
$a = getopt('', ['root:', 'package:', 'manifest-sha256:']);
$root = realpath($a['root'] ?? ''); $package = realpath($a['package'] ?? '');
if (!in_array($root, ['/Users/matt/code/mageos-latest', '/var/www/html'], true) || !$package
    || hash_file('sha256', $package . '/manifest.json') !== ($a['manifest-sha256'] ?? '')) { throw new RuntimeException('Pinned fixture repair required'); }
$fixtures = json_decode(file_get_contents($package . '/fixtures.json'), true, 512, JSON_THROW_ON_ERROR);
$downloads = array_values(array_filter($fixtures, static fn($f) => $f['product']['product_type'] === 'downloadable'));
if (count($downloads) !== 12) { throw new RuntimeException('Exactly 12 QA downloads required'); }
require $root . '/app/bootstrap.php';
$om = \Magento\Framework\App\Bootstrap::create($root, $_SERVER)->getObjectManager();
$om->get(\Magento\Framework\App\State::class)->setAreaCode('adminhtml');
$repo = $om->get(\Magento\Catalog\Api\ProductRepositoryInterface::class);
$resource = $om->get(\Magento\Catalog\Model\ResourceModel\Product::class);
$e = require $root . '/app/etc/env.php'; $c = $e['db']['connection']['default'];
$dsn = 'mysql:host=' . $c['host'] . ';dbname=' . $c['dbname']; if (!empty($c['port'])) { $dsn .= ';port=' . (int)$c['port']; }
$pdo = new PDO($dsn, $c['username'], $c['password']); $journal = new ExpansionCatalogJournal($pdo, $e['db']['table_prefix'] ?? '');
$before = $journal->protectedHashes(); $changes = [];
foreach ($downloads as $i => $f) {
    $r = $f['product']; $sku = sprintf('WANDS-QA-DOWNLOAD-%02d', $i + 1);
    if ($r['sku'] !== $sku) { throw new RuntimeException('Repair outside exact download SKU list'); }
    $p = $repo->get($sku, false, 0, true);
    if ($p->getTypeId() !== 'downloadable') { throw new RuntimeException('Unexpected fixture type'); }
    foreach (['links_purchased_separately', 'links_title', 'samples_title'] as $attribute) {
        $old = $p->getData($attribute); $p->setData($attribute, $r[$attribute]); $resource->saveAttribute($p, $attribute);
        $changes[] = ['sku' => $sku, 'attribute' => $attribute, 'before' => $old, 'after' => $r[$attribute]];
    }
}
$prefix = $e['db']['table_prefix'] ?? '';
$website = (int)$pdo->query('SELECT website_id FROM ' . $prefix . "store_website WHERE code='wands'")->fetchColumn();
$pdo->beginTransaction();
try {
    foreach (['WANDS-QA-PRICE-TIER-ALL' => [5, 70], 'WANDS-QA-PRICE-GROUP-GUEST' => [1, 80]] as $sku => [$qty, $price]) {
        $q = $pdo->prepare('SELECT t.* FROM ' . $prefix . 'catalog_product_entity_tier_price t JOIN ' . $prefix . 'catalog_product_entity p ON p.entity_id=t.entity_id WHERE p.sku=? FOR UPDATE');
        $q->execute([$sku]); $rows = $q->fetchAll(PDO::FETCH_ASSOC);
        if (count($rows) !== 1 || (float)$rows[0]['qty'] !== (float)$qty || (float)$rows[0]['value'] !== (float)$price) { throw new RuntimeException('Exact QA tier row differs'); }
        if (!in_array((int)$rows[0]['website_id'], [0, $website], true)) { throw new RuntimeException('Unexpected QA tier website'); }
        $pdo->prepare('UPDATE ' . $prefix . 'catalog_product_entity_tier_price SET website_id=? WHERE value_id=? AND entity_id=?')
            ->execute([$website, $rows[0]['value_id'], $rows[0]['entity_id']]);
        $changes[] = ['sku' => $sku, 'attribute' => 'tier_price_website', 'before' => $rows[0]['website_id'], 'after' => $website];
    }
    $pdo->commit();
} catch (Throwable $e) { $pdo->rollBack(); throw $e; }
if ($before !== $journal->protectedHashes()) { throw new RuntimeException('Fixture repair changed protected rows'); }
echo json_encode(['root' => $root, 'products' => 14, 'changes' => $changes, 'protected_unchanged' => true], JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR) . "\n";
