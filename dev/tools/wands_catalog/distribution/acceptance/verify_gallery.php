<?php
declare(strict_types=1);
require '/var/www/html/app/bootstrap.php';
$om=\Magento\Framework\App\Bootstrap::create(BP,$_SERVER)->getObjectManager();
$deployment=$om->get(\Magento\Framework\App\DeploymentConfig::class);
if ($deployment->get('db/connection/default/dbname')!=='lab_enriched_full'
    || $deployment->get('db/connection/default/host')!=='db') {
    throw new RuntimeException('Gallery acceptance requires the isolated full database');
}
$phase=$argv[1]??'';
if (!in_array($phase,['before','after'],true)) { throw new RuntimeException('Choose before or after'); }
$provenance=json_decode(file_get_contents('/packages/gallery-staged/data/gallery-provenance.json'),true,512,JSON_THROW_ON_ERROR);
$expected=[];
foreach ($provenance as $image) { $expected[$image['sku']][$image['sha256']]=$image['view']; }
if (count($expected)!==7 || count($provenance)!==14) { throw new RuntimeException('Unexpected gallery scope'); }
$repository=$om->get(\Magento\Catalog\Api\ProductRepositoryInterface::class);
$products=[];
foreach ($expected as $sku=>$images) {
    $product=$repository->get($sku,false,0,true);
    $row=['roles'=>[], 'entries'=>[]];
    foreach (['image','small_image','thumbnail'] as $role) { $row['roles'][$role]=$product->getData($role); }
    foreach ($product->getMediaGalleryEntries() as $entry) {
        $file=$entry->getFile();
        $row['entries'][$file]=['id'=>$entry->getId(),'position'=>$entry->getPosition(),
            'label'=>$entry->getLabel(),'disabled'=>$entry->isDisabled(),
            'sha256'=>hash_file('sha256',BP.'/pub/media/catalog/product'.$file)];
    }
    $products[$sku]=$row;
}
$report=['phase'=>$phase,'products'=>$products,'checks'=>0,'failures'=>[]];
if ($phase==='after') {
    $before=json_decode(file_get_contents(BP.'/var/gallery-before.json'),true,512,JSON_THROW_ON_ERROR)['products'];
    $check=static function(bool $valid,string $message) use (&$report): void {
        $report['checks']++; if (!$valid) { $report['failures'][]=$message; }
    };
    $addedCount=0;
    foreach ($products as $sku=>$row) {
        $check($row['roles']===$before[$sku]['roles'],'Hero roles unchanged: '.$sku);
        foreach ($before[$sku]['entries'] as $file=>$entry) {
            $check(($row['entries'][$file]??null)===$entry,'Existing gallery entry unchanged: '.$sku.':'.$file);
        }
        $added=array_diff_key($row['entries'],$before[$sku]['entries']);
        $addedCount+=count($added);
        $check(count($added)===2,'Exactly two appended images: '.$sku);
        $hashes=array_column($added,'sha256'); sort($hashes);
        $wanted=array_keys($expected[$sku]); sort($wanted);
        $check($hashes===$wanted,'Exact generated image hashes: '.$sku);
        foreach ($added as $entry) {
            $view=$expected[$sku][$entry['sha256']]??'unknown';
            $check($entry['label']==='Synthetic '.$view.' illustration; styling not included','Gallery label: '.$sku);
            $check(!$entry['disabled'],'Appended image enabled: '.$sku);
            $check($entry['position']>max(array_column($before[$sku]['entries'],'position')),'Appended image order: '.$sku);
        }
    }
    $report['added_images']=$addedCount;
    $check($addedCount===14,'Exactly 14 additions');
}
$report['status']=$report['failures']===[]?'passed':'failed';
$path=BP.'/var/gallery-'.$phase.'.json';
$stream=fopen($path,'x');
if (!$stream) { throw new RuntimeException('Gallery receipt already exists'); }
fwrite($stream,json_encode($report,JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR)); fclose($stream);
exit($report['status']==='passed'?0:1);
