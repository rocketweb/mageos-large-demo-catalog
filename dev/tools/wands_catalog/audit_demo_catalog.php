<?php
declare(strict_types=1);
$args=getopt('', ['root:', 'output:']);
$env=require $args['root'].'/app/etc/env.php';
$db=$env['db']['connection']['default'];
$pdo=new PDO('mysql:host='.$db['host'].';dbname='.$db['dbname'].';charset=utf8mb4',$db['username'],$db['password'],[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
$pdo->exec('SET TRANSACTION READ ONLY'); $pdo->beginTransaction();
$queries=[
    'product_types'=>"SELECT type_id,COUNT(*) AS products FROM catalog_product_entity WHERE sku LIKE 'WANDS-%' GROUP BY type_id",
    'broken_bundle_selections'=>"SELECT COUNT(*) AS count FROM catalog_product_bundle_selection s JOIN catalog_product_entity b ON b.entity_id=s.parent_product_id LEFT JOIN catalog_product_entity p ON p.entity_id=s.product_id LEFT JOIN catalog_product_bundle_option o ON o.option_id=s.option_id WHERE b.sku LIKE 'WANDS-%' AND (p.entity_id IS NULL OR o.option_id IS NULL OR o.parent_id<>b.entity_id OR s.selection_qty<=0)",
    'empty_bundle_options'=>"SELECT COUNT(*) AS count FROM catalog_product_bundle_option o JOIN catalog_product_entity b ON b.entity_id=o.parent_id LEFT JOIN catalog_product_bundle_selection s ON s.option_id=o.option_id WHERE b.sku LIKE 'WANDS-%' AND s.selection_id IS NULL",
    'orphan_configurables'=>"SELECT COUNT(*) AS count FROM catalog_product_entity p LEFT JOIN catalog_product_super_link l ON l.parent_id=p.entity_id WHERE p.sku LIKE 'WANDS-%' AND p.type_id='configurable' AND l.link_id IS NULL",
    'bundle_assortments'=>"SELECT COUNT(DISTINCT s.parent_product_id) AS bundles,COUNT(*) AS selections FROM catalog_product_bundle_selection s JOIN catalog_product_entity p ON p.entity_id=s.parent_product_id WHERE p.sku LIKE 'WANDS-%'",
];
$result=['captured_at'=>gmdate('c')];
foreach ($queries as $name=>$sql) { $result[$name]=$pdo->query($sql)->fetchAll(PDO::FETCH_ASSOC); }
$pdo->rollBack();
file_put_contents($args['output'],json_encode($result,JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR).PHP_EOL);
