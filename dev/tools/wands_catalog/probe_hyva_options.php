<?php
declare(strict_types=1);
require __DIR__.'/rehearsal_runtime.php';

$a=getopt('',['root:','output:','plan:','candidate-label-plugin','captured-theme','browser-components']);
try{
    [$om,$connection,$isolation,$entities]=openRehearsal($a);
    requireRehearsal(($isolation['source_generated_code_excluded']??false)===true,'Fresh generated-code isolation required');
    requireRehearsal(($isolation['candidate_label_plugin']??false)===isset($a['candidate-label-plugin']),'Candidate root/flag mismatch');
    $om->configure($om->get(\Magento\Framework\ObjectManager\ConfigLoaderInterface::class)->load('frontend'));
    $candidateHashes=[];$candidateChain=null;
    if(isset($a['candidate-label-plugin'])){
        $module=dirname(__DIR__,3).'/app/code/RocketWeb/LabCatalog';
        $plugin=$module.'/Plugin/ConfigurableFamilyLabel.php';$config=$module.'/etc/frontend/di.xml';
        $dom=new DOMDocument();$dom->load($config);
        $validation=\Magento\Framework\Config\Dom::validateDomDocument($dom,$isolation['source'].'/vendor/mage-os/framework/ObjectManager/etc/config.xsd');
        requireRehearsal($validation===[],'Invalid candidate frontend XML');
        $plugins=$om->get(\Magento\Framework\Interception\PluginListInterface::class);
        $candidateChain=$plugins->getNext(\Magento\ConfigurableProduct\Block\Product\View\Type\Configurable::class,'getAllowAttributes');
        requireRehearsal(str_contains(json_encode($candidateChain),'rocketweb_lab_catalog_family_label'),'Candidate plugin is absent from native interception chain');
        $candidateHashes=[$plugin=>hash_file('sha256',$plugin),$config=>hash_file('sha256',$config)];
        requireRehearsal($candidateHashes===$isolation['candidate_hashes'],'Candidate changed after fixture preparation');
        requireRehearsal(hash_file('sha256',$isolation['root'].'/app/code/WandsRehearsal/CandidateLabel/etc/frontend/di.xml')===hash_file('sha256',$config),'Fixture frontend XML differs');
    }
    $themeId=$connection->fetchOne('SELECT theme_id FROM theme WHERE area=? AND theme_path=?',['frontend','Hyva/default']);
    requireRehearsal((int)$themeId>0,'Captured Hyva theme is missing');
    $configuredThemeId=$om->get(\Magento\Framework\App\Config\ScopeConfigInterface::class)->getValue('design/theme/theme_id','store',2);
    if(isset($a['captured-theme'])){requireRehearsal((string)$configuredThemeId===(string)$themeId,'Captured store assignment differs from selected theme');}
    $theme=$om->create(\Magento\Theme\Model\Theme::class);$theme->load($themeId);
    $om->get(\Magento\Framework\View\DesignInterface::class)->setDesignTheme($theme,'frontend');
    $before=rehearsalTableHashes($connection);$products=[];
    $template=$isolation['source'].'/vendor/hyva-themes/magento2-default-theme/Magento_ConfigurableProduct/templates/product/view/type/options/configurable.phtml';
    $engine=$om->get(\Magento\Framework\View\TemplateEngine\Php::class);
    $componentPaths=[];$componentHashes=[];$browserAssets=[];
    if(isset($a['browser-components'])){
        requireRehearsal(isset($a['captured-theme']),'Browser components require captured theme assignment');
        $componentPaths=[
            'options_js'=>$isolation['source'].'/vendor/hyva-themes/magento2-default-theme/Magento_ConfigurableProduct/templates/product/view/type/options/js/configurable-options.phtml',
            'price_html'=>$isolation['source'].'/vendor/hyva-themes/magento2-default-theme/Magento_Catalog/templates/product/view/price.phtml',
            'hyva_js'=>$isolation['source'].'/vendor/hyva-themes/magento2-theme-module/src/view/frontend/templates/page/js/hyva.phtml'];
        foreach($componentPaths as $path){$componentHashes[$path]=hash_file('sha256',$path);}
        $alpine=$om->get(\Hyva\Theme\ViewModel\ThemeLibrariesConfig::class)->getVersionIdFor('alpine');
        requireRehearsal(in_array($alpine,['3','3-csp'],true),'Unsupported browser rehearsal Alpine version');
        $browserAssets=['alpine'=>$isolation['source'].'/vendor/hyva-themes/magento2-theme-module/src/view/base/web/js/alpine'.$alpine.'.min.js',
            'styles'=>$isolation['source'].'/vendor/hyva-themes/magento2-default-theme/web/css/styles.css'];
        foreach($browserAssets as $path){requireRehearsal(is_file($path),'Installed browser asset missing');$componentHashes[$path]=hash_file('sha256',$path);}
    }
    foreach(['WANDS-030335','WANDS-035295'] as $sku){
        $product=$om->create(\Magento\Catalog\Model\Product::class)->setStoreId(2)->setCustomerGroupId(0);$product->load($product->getIdBySku($sku));
        $blockType=\Magento\ConfigurableProduct\Block\Product\View\Type\Configurable::class;
        $block=$om->get(\Magento\Framework\View\LayoutInterface::class)->createBlock($blockType)->setProduct($product);
        $labels=[];
        foreach($block->getAllowAttributes() as $attribute){$labels[]=['attribute_id'=>$attribute->getAttributeId(),'family_label'=>$attribute->getLabel(),'shared_label'=>$attribute->getProductAttribute()->getStoreLabel()];}
        $json=json_decode($block->getJsonConfig(),true,512,JSON_THROW_ON_ERROR);
        $variables=['escaper'=>$om->get(\Magento\Framework\Escaper::class),'hyvaCsp'=>$om->get(\Hyva\Theme\ViewModel\HyvaCsp::class),
            'viewModels'=>$om->get(\Hyva\Theme\Model\ViewModelRegistry::class)];
        $html=$engine->render($block,$template,$variables);$components=[];
        if($componentPaths){
            $om->get(\Hyva\Theme\ViewModel\CurrentProduct::class)->set($product);
            foreach($componentPaths as $key=>$path){$components[$key]=$engine->render($block,$path,$variables);}
        }
        $reflection=new ReflectionClass($block);
        requireRehearsal(str_starts_with($reflection->getFileName(),$isolation['root'].'/generated/'),'Block is not generated in isolated root');
        $products[]=['sku'=>$sku,'product_id'=>$product->getId(),'block_class'=>get_class($block),
            'block_file'=>$reflection->getFileName(),'attribute_method_file'=>$reflection->getMethod('getAllowAttributes')->getFileName(),
            'labels'=>$labels,'config'=>$json,'html'=>$html,'components'=>$components];
    }
    $after=rehearsalTableHashes($connection);requireRehearsal($before===$after,'Rendered option probe changed database rows');
    saveRehearsal($a['output'],['versions'=>$isolation['versions'],'database'=>$isolation['database'],'theme'=>'Hyva/default (explicit isolated selection)',
        'products'=>$products,'before_table_hashes'=>$before,'after_table_hashes'=>$after,'database_unchanged'=>true,
        'configured_theme_id'=>$configuredThemeId,'selected_theme_id'=>$themeId,'captured_theme_verified'=>isset($a['captured-theme']),
        'component_template_hashes'=>$componentHashes,'browser_assets'=>$browserAssets,'browser_components_rendered'=>isset($a['browser-components']),
        'template_path'=>$template,'template_sha256'=>hash_file('sha256',$template),'probe_sha256'=>hash_file('sha256',__FILE__),
        'runtime_sha256'=>hash_file('sha256',__DIR__.'/rehearsal_runtime.php'),'plan_sha256'=>hash_file('sha256',$a['plan']),
        'candidate_frontend_xml_discovered'=>isset($a['candidate-label-plugin']),'candidate_hashes'=>$candidateHashes,'candidate_chain'=>$candidateChain,'module_deployment_verified'=>false,
        'isolated_root'=>$isolation['root'],'source_generated_code_excluded'=>true,'autoload_isolation_sha256'=>$isolation['autoload_isolation_sha256'],
        'shared_piece_count_label_after'=>$om->get(\Magento\Eav\Model\Config::class)->getAttribute('catalog_product','wands_piece_count')->getStoreLabel(),
        'native_template_rendered'=>true,'browser_verified'=>false,'full_storefront_verified'=>false,'media_verified'=>false,'live_writes'=>false]);
}catch(Throwable $e){rehearsalFailure($a,$e,isset($before,$connection)?['before_table_hashes'=>$before,'after_table_hashes'=>rehearsalTableHashes($connection),'accepted'=>false,'live_writes'=>false]:[]);}
