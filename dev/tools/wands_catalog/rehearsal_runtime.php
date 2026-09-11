<?php
declare(strict_types=1);

/** Shared boundary for new local-only lifecycle probes. */
function requireRehearsal(bool $condition,string $message):void {if(!$condition){throw new RuntimeException($message);}}
function openRehearsal(array $args):array
{
    requireRehearsal(!file_exists($args['output']),'Choose fresh output');
    $root=realpath($args['root']);$isolation=json_decode(file_get_contents($root.'/isolation.json'),true,512,JSON_THROW_ON_ERROR);
    $env=require $root.'/app/etc/env.php';$db=$env['db']['connection']['default'];
    requireRehearsal($root===$isolation['root'] && $db['host']==='127.0.0.1:13380' && !isset($db['port']) && $db['dbname']===$isolation['database'] && (bool)preg_match('/^wands_rehearsal_[a-z0-9_]+$/',$db['dbname']),'Isolation guard failed');
    requireRehearsal(hash_file('sha256',$args['plan'])==='91cff3d0c405006285921e6f7e90d3499fb60a8e23e91def55ef840ebc121828','Wrong approved plan');
    $plan=json_decode(file_get_contents($args['plan']),true,512,JSON_THROW_ON_ERROR);
    putenv('WANDS_REHEARSAL_CRYPT_KEY='.bin2hex(random_bytes(16)));
    require $root.'/app/bootstrap.php';
    $om=\Magento\Framework\App\Bootstrap::create($root,['MAGE_MODE'=>'developer'])->getObjectManager();
    $om->get(\Magento\Framework\App\State::class)->setAreaCode('frontend');
    $om->get(\Magento\Store\Model\StoreManagerInterface::class)->setCurrentStore(2);
    $connection=$om->get(\Magento\Framework\App\ResourceConnection::class)->getConnection();
    requireRehearsal($connection->fetchOne('SELECT DATABASE()')===$db['dbname'],'Wrong database');
    $entities=$connection->fetchAll('SELECT entity_id,sku,type_id FROM catalog_product_entity ORDER BY entity_id');
    $actual=array_column($entities,'sku');sort($actual);$expected=$plan['approved_products'];sort($expected);
    requireRehearsal(count($actual)===17 && $actual===$expected,'Fixture must contain exactly the seventeen approved products');
    return [$om,$connection,$isolation,$entities];
}
function rehearsalTableHashes($connection):array
{
    $result=[];
    foreach($connection->fetchCol('SHOW TABLES') as $table){
        $encoded=[];
        foreach($connection->fetchAll('SELECT * FROM '.$connection->quoteIdentifier($table)) as $row){ksort($row);$encoded[]=json_encode(array_map(static fn($v)=>$v===null?null:(string)$v,$row),JSON_THROW_ON_ERROR);}
        sort($encoded);$result[$table]=hash('sha256',json_encode($encoded,JSON_THROW_ON_ERROR));
    }
    ksort($result);return $result;
}
function rehearsalFailure(array $args,Throwable $error,array $diagnostic=[]):never
{
    $messages=[];do{$messages[]=get_class($error).': '.$error->getMessage();$error=$error->getPrevious();}while($error);
    file_put_contents($args['output'].'.log',gmdate('c').' Failed: '.implode(' caused by ',$messages).PHP_EOL,FILE_APPEND);
    if($diagnostic){file_put_contents($args['output'].'.failed.json',json_encode($diagnostic,JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR).PHP_EOL);}
    exit(1);
}
function saveRehearsal(string $path,array $result):void
{
    $f=fopen($path,'x');requireRehearsal($f!==false,'Choose fresh output');chmod($path,0600);
    fwrite($f,json_encode($result,JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR).PHP_EOL);fclose($f);
    file_put_contents($path.'.log',gmdate('c')." Local rehearsal evidence captured; inspect acceptance result\n");
}
