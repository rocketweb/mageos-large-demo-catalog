<?php
declare(strict_types=1);

// Verify imported bytes and hide obsolete gallery views without deleting files.
$args = getopt('', ['root:', 'manifest:', 'output:', 'apply']);
try {
    if (file_exists($args['output'])) { throw new RuntimeException('Choose fresh receipt'); }
    $manifest = json_decode(file_get_contents($args['manifest']),true,512,JSON_THROW_ON_ERROR);
    if (count($manifest['assignments']) !== 507 || count($manifest['images']) !== 424) {
        throw new RuntimeException('Wrong media batch');
    }
    $env = require $args['root'].'/app/etc/env.php';
    $db = $env['db']['connection']['default'];
    $pdo = new PDO('mysql:host='.$db['host'].';dbname='.$db['dbname'].';charset=utf8mb4',$db['username'],$db['password'],[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
    $urls = $pdo->query("SELECT value FROM core_config_data WHERE path='web/secure/base_url'")->fetchAll(PDO::FETCH_COLUMN);
    if (!in_array('https://relevance.comtom.lab/',$urls,true) || !empty($env['db']['table_prefix'])) { throw new RuntimeException('Wrong destination'); }
    $pdo->beginTransaction();
    $lookup = $pdo->prepare("SELECT p.entity_id,a.attribute_code,v.store_id,v.value FROM catalog_product_entity p JOIN catalog_product_entity_varchar v ON v.entity_id=p.entity_id JOIN eav_attribute a ON a.attribute_id=v.attribute_id WHERE p.sku=? AND a.attribute_code IN ('image','small_image','thumbnail')");
    $gallery = $pdo->prepare('SELECT v.*,g.value AS file FROM catalog_product_entity_media_gallery_value v JOIN catalog_product_entity_media_gallery g ON g.value_id=v.value_id WHERE v.entity_id=? FOR UPDATE');
    $changes = []; $roles = 0;
    foreach ($manifest['assignments'] as $sku=>$imageSku) {
        if (!preg_match('/^WANDS-[A-Z0-9-]+$/',$sku)) { throw new RuntimeException('Wrong SKU'); }
        $expected=$manifest['images'][$imageSku]['sha256'];
        $lookup->execute([$sku]); $rows=$lookup->fetchAll(PDO::FETCH_ASSOC);
        $defaults=[];
        foreach ($rows as $row) {
            $file=$args['root'].'/pub/media/catalog/product'.$row['value'];
            if (str_contains($row['value'],'..') || !is_file($file) || hash_file('sha256',$file)!==$expected) {
                throw new RuntimeException('Media role does not match expected bytes: '.$sku.' '.$row['attribute_code'].' store '.$row['store_id']);
            }
            if ((int)$row['store_id']===0) { $defaults[$row['attribute_code']]=$row; }
            $roles++;
        }
        if (count($defaults)!==3) { throw new RuntimeException('Missing default media roles: '.$sku); }
        $base=$defaults['image'];
        $gallery->execute([$base['entity_id']]);
        foreach ($gallery->fetchAll(PDO::FETCH_ASSOC) as $row) {
            $desired = $row['file']===$base['value'] ? 0 : 1;
            if ((int)$row['disabled']!==$desired) { $changes[]=['before'=>$row,'disabled'=>$desired]; }
        }
    }
    $receipt=['verified_skus'=>count($manifest['assignments']),'verified_roles'=>$roles,'gallery_changes'=>count($changes),'changes'=>$changes,'files_deleted'=>0,'applied'=>isset($args['apply'])];
    $stream=fopen($args['output'],'x'); chmod($args['output'],0600);
    $data=json_encode($receipt,JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR).PHP_EOL;
    if (fwrite($stream,$data)!==strlen($data) || !fflush($stream) || !fsync($stream)) { throw new RuntimeException('Receipt write failed'); }
    fclose($stream);
    if (isset($args['apply'])) {
        $update=$pdo->prepare('UPDATE catalog_product_entity_media_gallery_value SET disabled=? WHERE record_id=? AND disabled=?');
        foreach ($changes as $change) {
            $update->execute([$change['disabled'],$change['before']['record_id'],$change['before']['disabled']]);
            if ($update->rowCount()!==1) { throw new RuntimeException('Gallery row drift'); }
        }
        $pdo->commit(); file_put_contents($args['output'].'.committed',hash_file('sha256',$args['output']));
    } else { $pdo->rollBack(); }
    unset($receipt['changes']);
    file_put_contents($args['output'].'.log',json_encode($receipt).PHP_EOL);
} catch (Throwable $error) {
    if (isset($pdo) && $pdo->inTransaction()) { $pdo->rollBack(); }
    file_put_contents($args['output'].'.log',$error->getMessage().PHP_EOL); exit(1);
}
