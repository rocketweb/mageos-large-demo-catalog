<?php
declare(strict_types=1);

require '/var/www/html/app/bootstrap.php';
$om=Magento\Framework\App\Bootstrap::create(BP,$_SERVER)->getObjectManager();
$resource=$om->get(Magento\Framework\App\ResourceConnection::class);
$db=$resource->getConnection();
$config=$om->get(Magento\Framework\App\Config\ScopeConfigInterface::class);
if ($db->fetchOne('SELECT DATABASE()')!=='magento'
    || parse_url((string)$config->getValue('web/secure/base_url'),PHP_URL_HOST)!=='relevance.comtom.lab') {
    throw new RuntimeException('Wrong stock restoration destination');
}
$root=BP.'/var/catalog-enriched-20260913-v2';
$changes=json_decode(file_get_contents($root.'/stock-diff.json'),true,512,JSON_THROW_ON_ERROR);
$plan=json_decode(file_get_contents($root.'/plan.json'),true,512,JSON_THROW_ON_ERROR);
$fields=[];
foreach ($changes as $change) {
    foreach (array_keys($change['before']) as $key) { $fields[$key]=($fields[$key]??0)+1; }
}
ksort($fields);
if (count($changes)!==90 || $fields!==['is_in_stock'=>49,'low_stock_date'=>40,'stock_status_changed_auto'=>50]) {
    throw new RuntimeException('Stock restoration scope differs from inspected 90 rows / 139 fields');
}
$receipt=fopen($root.'/stock-restoration.json','x');
if (!$receipt) { throw new RuntimeException('Restoration already attempted'); }
$db->beginTransaction();
try {
    foreach ($changes as $id=>$change) {
        $row=$db->fetchRow($db->select()->from('cataloginventory_stock_item')->where('item_id = ?',$id)->forUpdate(true));
        foreach ($change['after'] as $key=>$value) {
            if ($row[$key]!==$value) { throw new RuntimeException('Stock row changed since inspection: '.$id); }
        }
        $db->update('cataloginventory_stock_item',$change['before'],['item_id = ?'=>$id]);
    }
    $context=hash_init('sha256');
    foreach ($db->fetchAll('SELECT * FROM cataloginventory_stock_item ORDER BY item_id') as $row) {
        hash_update($context,json_encode($row,JSON_THROW_ON_ERROR)."\n");
    }
    $digest=hash_final($context);
    if ($digest!==$plan['protected']['cataloginventory_stock_item']['sha256']) {
        throw new RuntimeException('Restored stock table does not exactly match the original plan');
    }
    $db->commit();
    fwrite($receipt,json_encode(['status'=>'passed','restored_rows'=>90,'restored_fields'=>$fields,
        'stock_table_sha256'=>$digest],JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR));
} catch (Throwable $error) {
    $db->rollBack();
    fwrite($receipt,json_encode(['status'=>'failed','error'=>$error->getMessage()],JSON_THROW_ON_ERROR));
    throw $error;
} finally { fclose($receipt); }
