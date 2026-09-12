<?php
declare(strict_types=1);
require __DIR__.'/rehearsal_runtime.php';

function localThemeDdl(SimpleXMLElement $table,$connection):string
{
    $parts=[];
    foreach($table->column as $column){
        $type=(string)$column->attributes('http://www.w3.org/2001/XMLSchema-instance')['type'];
        requireRehearsal(in_array($type,['int','smallint','varchar','text','longtext','boolean','date','decimal'],true),'Unsupported local metadata type');
        $sqlType=$type==='boolean'?'TINYINT(1)':strtoupper($type);
        if($type==='varchar'){$sqlType.='('.(int)$column['length'].')';}
        if($type==='decimal'){$sqlType.='('.(int)$column['precision'].','.(int)$column['scale'].')';}
        $definition=$connection->quoteIdentifier((string)$column['name']).' '.$sqlType;
        if((string)$column['unsigned']==='true'){$definition.=' UNSIGNED';}
        $definition.=(string)$column['nullable']==='false'?' NOT NULL':' NULL';
        if(isset($column['default'])){
            $value=(string)$column['default'];if($value==='false'){$value='0';}if($value==='true'){$value='1';}
            $definition.=' DEFAULT '.$connection->quote($value);
        }
        if((string)$column['identity']==='true'){$definition.=' AUTO_INCREMENT';}
        $parts[]=$definition;
    }
    foreach($table->constraint as $constraint){
        $type=(string)$constraint->attributes('http://www.w3.org/2001/XMLSchema-instance')['type'];
        if($type==='primary'){
            $fields=[];foreach($constraint->column as $column){$fields[]=$connection->quoteIdentifier((string)$column['name']);}
            $parts[]='PRIMARY KEY ('.implode(',',$fields).')';
        }elseif($type==='foreign'){
            requireRehearsal(in_array((string)$constraint['referenceTable'],['theme','store'],true),'Unexpected metadata reference');
            requireRehearsal((string)$constraint['onDelete']==='CASCADE','Unsupported metadata delete behavior');
            $parts[]='FOREIGN KEY ('.$connection->quoteIdentifier((string)$constraint['column']).') REFERENCES '.$connection->quoteIdentifier((string)$constraint['referenceTable']).' ('.$connection->quoteIdentifier((string)$constraint['referenceColumn']).') ON DELETE CASCADE';
        }else{throw new RuntimeException('Unsupported metadata constraint');}
    }
    return 'CREATE TABLE '.$connection->quoteIdentifier((string)$table['name']).' ('.implode(',',$parts).') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4';
}
if(realpath($_SERVER['SCRIPT_FILENAME']??'')!==__FILE__){return;}
$a=getopt('',['root:','output:','plan:']);
try{
    [$om,$connection,$isolation,$entities]=openRehearsal($a);
    $sources=['module-theme'=>['theme','theme_file','design_change'],'module-directory'=>['directory_currency_rate']];
    $ddl=[];$hashes=[];
    foreach($sources as $module=>$tables){
        $path=$isolation['source'].'/vendor/mage-os/'.$module.'/etc/db_schema.xml';$xml=simplexml_load_file($path);$hashes[$path]=hash_file('sha256',$path);
        foreach($tables as $name){
            requireRehearsal(!$connection->isTableExists($name),'Never overwrite existing metadata table');
            $matches=$xml->xpath('/schema/table[@name="'.$name.'"]');requireRehearsal(count($matches)===1,'Native schema table missing');
            $ddl[$name]=localThemeDdl($matches[0],$connection);
        }
    }
    foreach($ddl as $sql){$connection->query($sql);}
    foreach([[1,null,'Magento/blank','Magento Blank'],[2,1,'Magento/luma','Magento Luma'],[3,null,'Hyva/default','Hyva Default']] as [$id,$parent,$path,$title]){
        $connection->insert('theme',['theme_id'=>$id,'parent_id'=>$parent,'theme_path'=>$path,'theme_title'=>$title,'is_featured'=>0,'area'=>'frontend','type'=>0,'code'=>$path]);
    }
    $connection->insert('directory_currency_rate',['currency_from'=>'USD','currency_to'=>'USD','rate'=>1]);
    saveRehearsal($a['output'],['database'=>$isolation['database'],'ddl'=>$ddl,'native_schema_hashes'=>$hashes,
        'synthetic_fixture_metadata'=>true,'theme_ids'=>[1,2,3],'tables_created'=>4,'rows_inserted'=>4,
        'description'=>'Local physical theme registrations and USD parity only; not captured live theme assignments',
        'live_writes'=>false,'helper_sha256'=>hash_file('sha256',__FILE__)]);
}catch(Throwable $e){rehearsalFailure($a,$e);}
