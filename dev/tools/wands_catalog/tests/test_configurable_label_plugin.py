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
 class Option {public function __construct(public $attribute){}public function getProductAttribute(){return $this->attribute;}public function setProductAttribute($a){$this->attribute=$a;}public function getLabel(){return 'Furniture pieces';}}
 class Product {public $sku='WANDS-030335';public $website='wands';public function getSku(){return $this->sku;}public function getStore(){return $this;}public function getWebsite(){return $this;}public function getCode(){return $this->website;}}
 require $argv[1];
 $attribute=new LabelAttribute();$option=new Option($attribute);$collection=new \Magento\ConfigurableProduct\Model\ResourceModel\Product\Type\Configurable\Attribute\Collection([$option]);
 $product=new Product();$block=new \Magento\ConfigurableProduct\Block\Product\View\Type\Configurable($product);
 $plugin=new \RocketWeb\LabCatalog\Plugin\ConfigurableFamilyLabel();$fixed=$plugin->afterGetAllowAttributes($block,$collection);
 $result=[$fixed!==$collection,$fixed[0]!==$option,$fixed[0]->getProductAttribute()!==$attribute,$fixed[0]->getProductAttribute()->getStoreLabel(),$attribute->getStoreLabel()];
 $product->sku='OTHER';$result[]=$plugin->afterGetAllowAttributes($block,$collection)===$collection;
 $product->sku='WANDS-030335';$product->website='base';$result[]=$plugin->afterGetAllowAttributes($block,$collection)===$collection;
 echo json_encode($result);
}
'''
        result=subprocess.run([str(PHP),'-r',code,str(plugin)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),[True,True,True,'Furniture pieces','Piece Count',True,True])
