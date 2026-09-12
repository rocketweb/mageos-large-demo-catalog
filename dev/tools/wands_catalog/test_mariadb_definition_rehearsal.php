<?php
declare(strict_types=1);

// Local disposable-schema integration test. Never reads a Magento env.php.
$a = getopt('', ['schema:', 'plan:', 'output-dir:']);
function requireCheck(bool $yes, string $message): void { if (!$yes) { throw new RuntimeException($message); } }
function qi(string $s): string { requireCheck((bool)preg_match('/^[a-zA-Z0-9_]+$/',$s),'Invalid identifier'); return '`'.$s.'`'; }
function tableState(PDO $pdo, array $tables): array {
    $state=[];
    foreach ($tables as $t) {
        $rows=$pdo->query('SELECT * FROM '.qi($t))->fetchAll(PDO::FETCH_ASSOC); $encoded=[];
        foreach ($rows as $r) { ksort($r); $encoded[]=json_encode(array_map(static fn($v)=>$v===null?null:(string)$v,$r),JSON_THROW_ON_ERROR); }
        sort($encoded);$state[$t]=hash('sha256',json_encode($encoded,JSON_THROW_ON_ERROR));
    }
    ksort($state);return $state;
}
function foreignKeyAudit(PDO $pdo, array $keys): void {
    foreach ($keys as $table=>$rows) {
        $groups=[];foreach($rows as $r){$groups[$r['CONSTRAINT_NAME']][]=$r;}
        foreach($groups as $fk){
            $join=[];$nonnull=[];foreach($fk as $r){$join[]='c.'.qi($r['COLUMN_NAME']).'=p.'.qi($r['REFERENCED_COLUMN_NAME']);$nonnull[]='c.'.qi($r['COLUMN_NAME']).' IS NOT NULL';}
            $sql='SELECT COUNT(*) FROM '.qi($table).' c LEFT JOIN '.qi($fk[0]['REFERENCED_TABLE_NAME']).' p ON '.implode(' AND ',$join).' WHERE '.implode(' AND ',$nonnull).' AND p.'.qi($fk[0]['REFERENCED_COLUMN_NAME']).' IS NULL';
            requireCheck((int)$pdo->query($sql)->fetchColumn()===0,'Foreign-key orphan in '.$table);
        }
    }
}
try {
    $out=$a['output-dir']; requireCheck(!file_exists($out),'Choose fresh output');mkdir($out,0700,true);
    $schema=json_decode(file_get_contents($a['schema']),true,512,JSON_THROW_ON_ERROR);
    $plan=json_decode(file_get_contents($a['plan']),true,512,JSON_THROW_ON_ERROR);$hash=hash_file('sha256',$a['plan']);
    requireCheck($schema['plan_sha256']===$hash && $schema['host']==='relevance.comtom.lab' && $schema['consistent_read_only']===true,'Wrong snapshot');
    requireCheck(time()-strtotime($schema['captured_at'])<=86400,'Stale schema');
    $dsn=(string)getenv('WANDS_REHEARSAL_DSN');
    requireCheck((bool)preg_match('/^mysql:host=127\.0\.0\.1;port=[0-9]+;dbname=(wands_rehearsal_[a-z0-9_]+);charset=utf8mb4$/',$dsn,$m),'Only loopback disposable database accepted');
    $name=$m[1];$serverDsn=preg_replace('/;dbname=[^;]+/','',$dsn);
    $pdo=new PDO($serverDsn,'root',(string)getenv('WANDS_REHEARSAL_PASSWORD'),[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
    $s=$pdo->prepare('SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=?');$s->execute([$name]);requireCheck((int)$s->fetchColumn()===0,'Never overwrite an existing database');
    $pdo->exec('CREATE DATABASE '.qi($name).' CHARACTER SET utf8mb4');$pdo->exec('USE '.qi($name));
    // Magento's admin store is ID zero; ordinary INSERT would otherwise allocate a new ID.
    $pdo->exec("SET SESSION sql_mode=CONCAT(@@SESSION.sql_mode,',NO_AUTO_VALUE_ON_ZERO')");
    $pdo->exec('SET FOREIGN_KEY_CHECKS=0');
    foreach($schema['ddl'] as $table=>$ddl){requireCheck(str_starts_with($ddl,'CREATE TABLE '.qi($table).' ('),'Unexpected DDL');$pdo->exec($ddl);}
    foreach($schema['rows'] as $table=>$rows){foreach($rows as $r){
        $s=$pdo->prepare('INSERT INTO '.qi($table).' ('.implode(',',array_map('qi',array_keys($r))).') VALUES ('.implode(',',array_fill(0,count($r),'?')).')');$s->execute(array_values($r));
    }}
    $pdo->exec('SET FOREIGN_KEY_CHECKS=1');
    requireCheck($pdo->query('SELECT code FROM store WHERE store_id=0')->fetchColumn()==='admin','Admin store ID zero was not preserved');
    foreignKeyAudit($pdo,$schema['foreign_keys']);
    $tables=array_keys($schema['ddl']);$before=tableState($pdo,$tables);$checks=['actual_schema_loaded','all_initial_foreign_keys_valid'];
    $call=static function(string $action,string $receipt,int $expected=0,array $extra=[]) use($a,$hash):void{
        $cmd=[PHP_BINARY,__DIR__.'/rehearse_definition_migration.php','--plan='.$a['plan'],'--plan-sha256='.$hash,'--action='.$action,'--receipt='.$receipt,...$extra];
        $p=proc_open($cmd,[0=>['pipe','r'],1=>['pipe','w'],2=>['pipe','w']],$pipes);fclose($pipes[0]);$stdout=stream_get_contents($pipes[1]);$stderr=stream_get_contents($pipes[2]);fclose($pipes[1]);fclose($pipes[2]);$code=proc_close($p);
        requireCheck($code===$expected,'Unexpected runner result: '.$action.'; inspect receipt log');requireCheck($stdout===''&&$stderr==='','Runner leaked terminal output');
    };
    $call('dry-run',$out.'/dry-run.json');requireCheck(tableState($pdo,$tables)===$before,'Dry-run changed database');$checks[]='dry_run_zero_writes';
    $call('apply',$out.'/interrupted.json',1,['--fail-after=40']);requireCheck(tableState($pdo,$tables)===$before,'Interrupted transaction persisted rows');$checks[]='interruption_atomic';
    $receipt=$out.'/applied.json';$call('apply',$receipt);foreignKeyAudit($pdo,$schema['foreign_keys']);
    $record=json_decode(file_get_contents($receipt),true,512,JSON_THROW_ON_ERROR);requireCheck(count($record['operations'])===105,'Wrong operation count');$checks[]='105_operations_with_foreign_keys_enabled';
    $after=tableState($pdo,$tables);requireCheck($after!==$before,'Apply had no effect');
    $call('apply',$out.'/duplicate.json',1);requireCheck(tableState($pdo,$tables)===$after,'Duplicate apply changed database');$checks[]='duplicate_apply_blocked';
    $original=file_get_contents($receipt);$altered=json_decode($original,true,512,JSON_THROW_ON_ERROR);$altered['state']='altered';file_put_contents($receipt,json_encode($altered));
    $call('rollback',$receipt,1);requireCheck(tableState($pdo,$tables)===$after,'Changed receipt allowed inverse');file_put_contents($receipt,$original);$checks[]='receipt_integrity_enforced';
    $set=(int)$pdo->query('SELECT attribute_set_id FROM catalog_product_entity LIMIT 1')->fetchColumn();
    $s=$pdo->prepare('INSERT INTO catalog_product_entity (attribute_set_id,type_id,sku,has_options,required_options) VALUES (?,"simple","WANDS-REHEARSAL-OUTSIDER",0,0)');$s->execute([$set]);$outsider=$pdo->lastInsertId();
    $s=$pdo->prepare('INSERT INTO catalog_product_entity_int (entity_id,attribute_id,store_id,value) VALUES (?,?,0,?)');$s->execute([$outsider,$plan['new_option_attribute_id'],$record['bindings']['new_option']]);
    $external=tableState($pdo,$tables);$call('rollback',$receipt,1);requireCheck(tableState($pdo,$tables)===$external,'Outside consumer altered');$checks[]='outside_option_consumer_blocks_inverse';
    $s=$pdo->prepare('DELETE FROM catalog_product_entity_int WHERE entity_id=?');$s->execute([$outsider]);$s=$pdo->prepare('DELETE FROM catalog_product_entity WHERE entity_id=?');$s->execute([$outsider]);
    $call('rollback',$receipt);foreignKeyAudit($pdo,$schema['foreign_keys']);requireCheck(tableState($pdo,$tables)===$before,'Full-table inverse parity failed');$checks[]='complete_table_row_parity_after_inverse';
    $call('rollback',$receipt,1);requireCheck(tableState($pdo,$tables)===$before,'Duplicate inverse changed rows');$checks[]='duplicate_inverse_blocked';
    $result=['checks'=>$checks,'count'=>count($checks),'database'=>$name,'engine'=>$pdo->query('SELECT VERSION()')->fetchColumn(),'source_engine'=>$schema['engine'],
        'tables'=>count($tables),'initial_rows'=>array_sum(array_map('count',$schema['rows'])),'plan_sha256'=>$hash,'schema_sha256'=>hash_file('sha256',$a['schema']),
        'runner_sha256'=>hash_file('sha256',__DIR__.'/rehearse_definition_migration.php'),'harness_sha256'=>hash_file('sha256',__FILE__),
        'before_table_hashes'=>$before,'after_table_hashes'=>$after,'restored_table_hashes'=>tableState($pdo,$tables),
        'foreign_keys_checked'=>true,'triggers_copied'=>false,'magento_bootstrapped'=>false,'storefront_verified'=>false,'live_writes'=>false];
    file_put_contents($out.'/result.json',json_encode($result,JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR).PHP_EOL);
    file_put_contents($out.'.log',gmdate('c')." MariaDB database-only rehearsal passed\n");
} catch(Throwable $e) {
    file_put_contents(($a['output-dir'] ?? sys_get_temp_dir().'/wands-mariadb').'.log',gmdate('c').' Failed: '.$e->getMessage().PHP_EOL,FILE_APPEND);exit(1);
}
