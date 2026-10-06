<?php
declare(strict_types=1);

// Read-only snapshot of the two existing destinations. No framework bootstrap,
// cache writes, credentials in output, or deployment actions.
$options = getopt('', ['root:']);
$root = realpath($options['root'] ?? '');
if (!in_array($root, ['/Users/matt/code/mageos-latest', '/var/www/html'], true)) {
    throw new RuntimeException('Unexpected installation root');
}
$env = require $root . '/app/etc/env.php';
$connection = $env['db']['connection']['default'];
$prefix = $env['db']['table_prefix'] ?? '';
if (!preg_match('/^[a-zA-Z0-9_]*$/', $prefix)) { throw new RuntimeException('Unexpected table prefix'); }
$table = static fn(string $name): string => '`' . $prefix . $name . '`';
$dsn = 'mysql:host=' . $connection['host'] . ';dbname=' . $connection['dbname'] . ';charset=utf8mb4';
if (!empty($connection['port'])) { $dsn .= ';port=' . $connection['port']; }
$db = new PDO($dsn, $connection['username'], $connection['password'], [PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
$db->exec('SET TRANSACTION READ ONLY');
$db->beginTransaction();
try {
    $websites = $db->query('SELECT website_id,code FROM ' . $table('store_website'))->fetchAll(PDO::FETCH_KEY_PAIR);
    $website = array_search('wands', $websites, true);
    if ($website === false) { throw new RuntimeException('Existing WANDS website not found'); }
    $stores = $db->query('SELECT store_id,website_id,code FROM ' . $table('store'))->fetchAll(PDO::FETCH_ASSOC);
    $wandsStores = array_values(array_filter($stores, static fn(array $r): bool => $r['code']==='wands' && (int)$r['website_id']===(int)$website));
    if (count($wandsStores)!==1) { throw new RuntimeException('Ambiguous WANDS store'); }
    $membership = [];
    foreach ($db->query('SELECT product_id,website_id FROM ' . $table('catalog_product_website') . ' ORDER BY product_id,website_id') as $r) {
        $membership[(int)$r['product_id']][] = (int)$r['website_id'];
    }
    $products=[];$targetIds=[];$shared=[];$otherIds=[];$types=[];$targetSkus=[];
    foreach ($db->query('SELECT entity_id,sku,type_id FROM ' . $table('catalog_product_entity') . ' ORDER BY entity_id') as $r) {
        $id=(int)$r['entity_id'];$target=in_array((int)$website,$membership[$id]??[],true);
        $products[$r['sku']]=['id'=>$id,'type'=>$r['type_id'],'websites'=>$membership[$id]??[],'wands'=>$target];
        if ($target) {
            if (!str_starts_with($r['sku'],'WANDS-')) { throw new RuntimeException('Unexpected SKU assigned to WANDS'); }
            $targetIds[]=$id;$targetSkus[$r['sku']]=true;$types[$r['type_id']]=($types[$r['type_id']]??0)+1;
            if (count($membership[$id])!==1) { $shared[]=$r['sku']; }
        } else { $otherIds[$id]=true; }
    }
    $protected=[];
    foreach (['varchar','int','text','decimal','datetime'] as $type) {
        $name='catalog_product_entity_'.$type;$hash=hash_init('sha256');$count=0;
        foreach ($db->query('SELECT * FROM '.$table($name).' ORDER BY value_id',PDO::FETCH_ASSOC) as $r) {
            if (isset($otherIds[(int)$r['entity_id']])) { hash_update($hash,json_encode($r,JSON_THROW_ON_ERROR)."\n");++$count; }
        }
        $protected[$name]=['rows'=>$count,'sha256'=>hash_final($hash)];
    }
    foreach (['core_config_data','customer_entity','sales_order','sales_order_item','inventory_reservation'] as $name) {
        $hash=hash_init('sha256');$count=0;
        foreach ($db->query('SELECT * FROM '.$table($name).' ORDER BY 1',PDO::FETCH_ASSOC) as $r) {
            hash_update($hash,json_encode($r,JSON_THROW_ON_ERROR)."\n");++$count;
        }
        $protected[$name]=['rows'=>$count,'sha256'=>hash_final($hash)];
    }
    $targetLookup=array_fill_keys($targetIds,true);
    $existingStock=[];
    foreach (['cataloginventory_stock_item'=>'product_id','inventory_source_item'=>'sku'] as $name=>$key) {
        $existingStock[$name]=[];$otherHash=hash_init('sha256');$otherCount=0;
        foreach ($db->query('SELECT * FROM '.$table($name).' ORDER BY 1',PDO::FETCH_ASSOC) as $r) {
            $target=$key==='sku' ? isset($targetSkus[$r[$key]]) : isset($targetLookup[(int)$r[$key]]);
            if ($target) {
                $existingStock[$name][]=$r;
            } else {
                hash_update($otherHash,json_encode($r,JSON_THROW_ON_ERROR)."\n");++$otherCount;
            }
        }
        $protected[$name]=['rows'=>$otherCount,'sha256'=>hash_final($otherHash)];
    }
    foreach (['catalog_product_entity'=>'entity_id','catalog_product_website'=>'product_id',
        'catalog_category_product'=>'product_id','catalog_product_entity_media_gallery_value_to_entity'=>'entity_id'] as $name=>$key) {
        $hash=hash_init('sha256');$count=0;
        // Full column ordering makes joins and composite-key tables deterministic.
        $columns=$db->query('SHOW COLUMNS FROM '.$table($name))->fetchAll(PDO::FETCH_COLUMN);
        $order=implode(',',array_map(static fn(string $column):string=>'`'.$column.'`',$columns));
        foreach ($db->query('SELECT * FROM '.$table($name).' ORDER BY '.$order,PDO::FETCH_ASSOC) as $r) {
            if (isset($otherIds[(int)$r[$key]])) {
                hash_update($hash,json_encode($r,JSON_THROW_ON_ERROR)."\n");++$count;
            }
        }
        $protected[$name]=['rows'=>$count,'sha256'=>hash_final($hash)];
    }
    $links=$db->query('SELECT p.sku parent,c.sku child FROM '.$table('catalog_product_super_link').' l JOIN '.
        $table('catalog_product_entity').' p ON p.entity_id=l.parent_id JOIN '.$table('catalog_product_entity').
        ' c ON c.entity_id=l.product_id ORDER BY p.sku,c.sku')->fetchAll(PDO::FETCH_ASSOC);
    $result=['schema'=>2,'root'=>$root,'database_writes'=>false,'website_id'=>(int)$website,
        'store_id'=>(int)$wandsStores[0]['store_id'],'wands_products'=>count($targetIds),'wands_types'=>$types,
        'other_products'=>count($otherIds),'shared_wands_skus'=>$shared,'products'=>$products,
        'configurable_links'=>$links,'protected'=>$protected,'existing_wands_stock'=>$existingStock];
    $db->rollBack();
    echo json_encode($result,JSON_THROW_ON_ERROR|JSON_UNESCAPED_SLASHES)."\n";
} catch (Throwable $error) {
    if ($db->inTransaction()) { $db->rollBack(); }
    throw $error;
}
