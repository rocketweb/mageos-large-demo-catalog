import json
from pathlib import Path
import subprocess
import unittest

PHP=Path('/opt/homebrew/Cellar/php@8.4/8.4.24/bin/php')
ROOT=Path(__file__).resolve().parents[4]


class FamilyLabelPluginTest(unittest.TestCase):
    @unittest.skipUnless(PHP.is_file(),'Local PHP unavailable')
    def test_scoped_label_without_mutating_shared_objects(self):
        plugin=ROOT/'app/code/RocketWeb/LabCatalog/Plugin/ConfigurableFamilyLabel.php'
        code=r'''
namespace Magento\ConfigurableProduct\Block\Product\View\Type {
 class Configurable {public function __construct(public $product){} public function getProduct(){return $this->product;}}
}
namespace Magento\ConfigurableProduct\Model\ResourceModel\Product\Type\Configurable\Attribute {
 class Collection extends \ArrayObject {public function getItems(){return $this->getArrayCopy();} public function removeAllItems(){$this->exchangeArray([]);} public function addItem($item){$this->append($item);}}
}
namespace {
 class LabelAttribute {public $label='Piece Count';public function getAttributeCode(){return 'wands_piece_count';}public function getStoreLabel(){return $this->label;}public function setStoreLabel($label){$this->label=$label;}}
 class Option {public $options=[['store_label'=>'4 Pieces'],['store_label'=>'5 Pieces'],['store_label'=>'7 Pieces'],['store_label'=>'6 Pieces']];public function __construct(public $attribute){}public function getProductAttribute(){return $this->attribute;}public function setProductAttribute($a){$this->attribute=$a;}public function getLabel(){return 'Furniture pieces';}public function getOptions(){return $this->options;}public function setOptions($options){$this->options=$options;}}
 class Product {public $sku='WANDS-030335';public $website='wands';public function getSku(){return $this->sku;}public function getStore(){return $this;}public function getWebsite(){return $this;}public function getCode(){return $this->website;}}
 require $argv[1];
 $attribute=new LabelAttribute();$option=new Option($attribute);$collection=new \Magento\ConfigurableProduct\Model\ResourceModel\Product\Type\Configurable\Attribute\Collection([$option]);
 $product=new Product();$block=new \Magento\ConfigurableProduct\Block\Product\View\Type\Configurable($product);
 $plugin=new \RocketWeb\LabCatalog\Plugin\ConfigurableFamilyLabel();$fixed=$plugin->afterGetAllowAttributes($block,$collection);
 $result=[$fixed!==$collection,$fixed[0]!==$option,$fixed[0]->getProductAttribute()!==$attribute,$fixed[0]->getProductAttribute()->getStoreLabel(),$attribute->getStoreLabel(),array_column($fixed[0]->getOptions(),'store_label'),array_column($option->getOptions(),'store_label')];
 $product->sku='OTHER';$result[]=$plugin->afterGetAllowAttributes($block,$collection)===$collection;
 $product->sku='WANDS-030335';$product->website='base';$result[]=$plugin->afterGetAllowAttributes($block,$collection)===$collection;
 echo json_encode($result);
}
'''
        result=subprocess.run([str(PHP),'-r',code,str(plugin)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),[True,True,True,'Furniture pieces','Piece Count',['4 Pieces','5 Pieces','6 Pieces','7 Pieces'],['4 Pieces','5 Pieces','7 Pieces','6 Pieces'],True,True])

    @unittest.skipUnless(PHP.is_file(),'Local PHP unavailable')
    def test_json_label_order_price_and_script_safety(self):
        code=r'''
namespace Magento\ConfigurableProduct\Block\Product\View\Type {
 class Configurable {public function __construct(public $product){}public function getProduct(){return $this->product;}public function getAllowAttributes(){return [new \Option()];}}
}
namespace {
 class Option {public function getAttributeId(){return '215';}public function getLabel(){return 'Furniture pieces';}}
 class Product {public $sku='WANDS-030335';public $website='wands';public function getSku(){return $this->sku;}public function getStore(){return $this;}public function getWebsite(){return $this;}public function getCode(){return $this->website;}}
 require $argv[1];$product=new Product();$block=new \Magento\ConfigurableProduct\Block\Product\View\Type\Configurable($product);
 $plugin=new \RocketWeb\LabCatalog\Plugin\ConfigurableFamilyLabel();
 $data=['attributes'=>['215'=>['code'=>'wands_piece_count','label'=>'Piece Count','options'=>[]]],'prices'=>['finalPrice'=>['amount'=>189.99]],'caption'=>'</script><script>unexpected</script>'];
 foreach([4,5,7,6] as $count){$data['attributes']['215']['options'][]=['id'=>(string)$count,'label'=>$count.' Pieces','products'=>[(string)($count+10)]];}
 $raw=json_encode($data,JSON_UNESCAPED_SLASHES);
 $updated=method_exists($plugin,'afterGetJsonConfig')?$plugin->afterGetJsonConfig($block,$raw):$raw;
 $actual=json_decode($updated,true);$result=[$actual['attributes']['215']['label'],array_column($actual['attributes']['215']['options'],'id'),$actual['prices']===$data['prices'],$actual['caption']===$data['caption'],!str_contains($updated,'</script>')];
 $product->sku='OTHER';$result[]=method_exists($plugin,'afterGetJsonConfig')?$plugin->afterGetJsonConfig($block,$raw)===$raw:true;
 $product->sku='WANDS-030335';$product->website='base';$result[]=method_exists($plugin,'afterGetJsonConfig')?$plugin->afterGetJsonConfig($block,$raw)===$raw:true;
 echo json_encode($result);
}
'''
        result=subprocess.run([str(PHP),'-r',code,str(ROOT/'app/code/RocketWeb/LabCatalog/Plugin/ConfigurableFamilyLabel.php')],capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(result.stdout),['Furniture pieces',['4','5','6','7'],True,True,True,True,True])
