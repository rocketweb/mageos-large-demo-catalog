<?php
declare(strict_types=1);

// Read actual product options and exercise unsaved guest quotes in the two
// existing installations. No quotes, orders or reservations are persisted.
function expansionLiveProbe(): void
{
    $a = getopt('', ['root:', 'request:', 'request-sha256:', 'quarantine:', 'quarantine-sha256:', 'output:']);
    $root = realpath($a['root'] ?? ''); $request = realpath($a['request'] ?? '');
    $parent = realpath(dirname($a['output'] ?? ''));
    if (!in_array($root, ['/Users/matt/code/mageos-latest', '/var/www/html'], true)
        || !$request || !str_starts_with($request, $root . '/var/')
        || hash_file('sha256', $request) !== ($a['request-sha256'] ?? '')
        || !$parent || !str_starts_with($parent, $root . '/var/') || (fileperms($parent) & 0077)
        || file_exists($a['output'])) { throw new RuntimeException('Exact existing root and private pinned probe required'); }
    $cases = json_decode(file_get_contents($request), true, 512, JSON_THROW_ON_ERROR);
    if (!$cases || count($cases) > 25) { throw new RuntimeException('Bounded storefront sample required'); }
    foreach ($cases as $case) {
        if (!str_starts_with($case['sku'], 'WANDS-') || !str_starts_with($case['selected_sku'], 'WANDS-')) {
            throw new RuntimeException('Product outside WANDS scope');
        }
    }
    require $root . '/app/bootstrap.php';
    require __DIR__ . '/expansion_catalog_journal.php';
    $om = Magento\Framework\App\Bootstrap::create(BP, $_SERVER)->getObjectManager();
    $om->get(Magento\Framework\App\State::class)->setAreaCode('frontend');
    $store = $om->get(Magento\Store\Model\StoreManagerInterface::class)->getStore('wands');
    $om->get(Magento\Store\Model\StoreManagerInterface::class)->setCurrentStore($store);
    $env = require $root . '/app/etc/env.php'; $c = $env['db']['connection']['default'];
    $dsn = 'mysql:host=' . $c['host'] . ';dbname=' . $c['dbname'] . ';charset=utf8mb4';
    if (!empty($c['port'])) { $dsn .= ';port=' . (int)$c['port']; }
    $pdo = new PDO($dsn, $c['username'], $c['password'], [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    $journal = new ExpansionCatalogJournal($pdo, $env['db']['table_prefix'] ?? '');
    $before = $journal->protectedHashes(); $results = [];
    $repo = $om->get(Magento\Catalog\Api\ProductRepositoryInterface::class);
    foreach ($cases as $case) {
        $product = $repo->get($case['sku'], false, (int)$store->getId(), true);
        $child = $repo->get($case['selected_sku'], false, (int)$store->getId(), true);
        if ($product->getTypeId() !== $case['type'] || (isset($case['name']) && $product->getName() !== $case['name']) || !$product->isVisibleInSiteVisibility()
            || (int)$product->getStatus() !== 1 || !in_array((int)$store->getWebsiteId(), array_map('intval', $product->getWebsiteIds()), true)) {
            throw new RuntimeException('Sample type, visibility or website mismatch: ' . $case['sku']);
        }
        $options = [];
        foreach ($case['options'] as $code => $label) {
            $attribute = $om->get(Magento\Eav\Model\Config::class)->getAttribute('catalog_product', $code);
            if ((string)$child->getAttributeText($code) !== $label) { throw new RuntimeException('Variant label mismatch'); }
            $options[(string)$attribute->getAttributeId()] = $child->getData($code);
        }
        if ($product->getTypeId() === 'configurable') {
            $children = $product->getTypeInstance()->getUsedProducts($product);
            if (!in_array($case['selected_sku'], array_map(static fn($p) => $p->getSku(), $children), true)) {
                throw new RuntimeException('Selected child missing from configurable');
            }
        }
        $quote = $om->create(Magento\Quote\Model\Quote::class)->setStore($store)
            ->setCustomerIsGuest(true)->setCustomerGroupId(0);
        $quote->setBaseCurrencyCode('USD')->setQuoteCurrencyCode('USD')->setStoreCurrencyCode('USD')
            ->setBaseToQuoteRate(1)->setStoreToBaseRate(1);
        $item = $quote->addProduct($product, new Magento\Framework\DataObject(['qty' => 1, 'super_attribute' => $options]));
        if (is_string($item) || $quote->getId() || !$quote->getAllItems()) { throw new RuntimeException('Unsaved cart rejected the sample'); }
        foreach ($quote->getAllItems() as $line) { if ($line->getHasError()) { throw new RuntimeException('Unsaved cart item has errors'); } }
        $selected = array_map(static fn($line) => $line->getProduct()->getSku(), $quote->getAllItems());
        if (!in_array($case['selected_sku'], $selected, true)) { throw new RuntimeException('Cart selected the wrong child'); }
        $quote->getAllVisibleItems()[0]->calcRowTotal();
        $price = (float)$quote->getAllVisibleItems()[0]->getCalculationPrice();
        if (abs($price - (float)$case['price']) > .011) { throw new RuntimeException('Cart price differs from exported specification for '
            . $case['sku'] . ': expected ' . $case['price'] . ', observed ' . $price . ', loaded final ' . $child->getFinalPrice()); }
        $missingRejected = null;
        if ($product->getTypeId() === 'configurable') {
            $empty = $om->create(Magento\Quote\Model\Quote::class)->setStore($store)->setCustomerIsGuest(true)->setCustomerGroupId(0);
            try { $missingRejected = is_string($empty->addProduct($product, new Magento\Framework\DataObject(['qty' => 1]))); }
            catch (Magento\Framework\Exception\LocalizedException $e) { $missingRejected = true; }
            if (!$missingRejected || $empty->getId()) { throw new RuntimeException('Missing configurable selections did not fail'); }
        }
        $results[] = $case + ['name' => $product->getName(), 'product_id' => (int)$product->getId(), 'url' => $product->getProductUrl(),
            'image' => $product->getImage(), 'cart_price' => $price, 'cart_selected_correct_child' => true,
            'missing_options_rejected' => $missingRejected];
    }
    $quarantineResult = null;
    if (!empty($a['quarantine'])) {
        $qpath = realpath($a['quarantine']);
        if (!$qpath || !str_starts_with($qpath, $root . '/var/') || hash_file('sha256', $qpath) !== ($a['quarantine-sha256'] ?? '')) {
            throw new RuntimeException('Pinned quarantine probe required');
        }
        $q = json_decode(file_get_contents($qpath), true, 512, JSON_THROW_ON_ERROR);
        if (count($q['entries'] ?? []) !== 213 || $q['proposal_sha256'] !== '27a78eca69ecd2b31b3d97983238d0aeb3b3aefb54d571fb3dbd7c041e72dd79') {
            throw new RuntimeException('Unapproved quarantine probe scope');
        }
        $parents = []; $checked = [];
        foreach ($q['entries'] as $entry) {
            foreach ([0, (int)$store->getId()] as $scope) {
                $p = $repo->get($entry['sku'], false, $scope, true);
                if ($p->getTypeId() !== 'simple' || (int)$p->getStatus() !== 2 || (int)$p->getVisibility() !== 1) {
                    throw new RuntimeException('Quarantined product remains enabled or visible: ' . $entry['sku']);
                }
            }
            $checked[] = $entry['sku'];
            if ($entry['parent_skus']) { foreach (explode(';', $entry['parent_skus']) as $parent) { $parents[$parent] = true; } }
        }
        $families = [];
        foreach (array_keys($parents) as $sku) {
            $parent = $repo->get($sku, false, (int)$store->getId(), true); $healthy = [];
            if ((int)$parent->getStatus() !== 1 || $parent->getTypeId() !== 'configurable') { throw new RuntimeException('Affected family disabled'); }
            foreach ($parent->getTypeInstance()->getUsedProducts($parent) as $child) {
                if ((int)$child->getStatus() === 1 && $child->isSalable()) { $healthy[] = $child->getSku(); }
            }
            if (!$healthy) { throw new RuntimeException('Affected family has no healthy saleable choices'); }
            $families[$sku] = $healthy;
        }
        $bundles = [];
        foreach (['WANDS-BUNDLE-043', 'WANDS-BUNDLE-044'] as $sku) {
            $bundle = $repo->get($sku, false, (int)$store->getId(), true);
            $options = $bundle->getTypeInstance()->getOptionsCollection($bundle);
            $selections = $bundle->getTypeInstance()->getSelectionsCollection($options->getAllIds(), $bundle); $healthy = [];
            foreach ($selections as $selection) {
                if ((int)$selection->getStatus() === 1 && $selection->isSalable()) { $healthy[(int)$selection->getOptionId()][] = $selection->getSku(); }
                elseif ((int)$selection->getIsDefault() === 1) { throw new RuntimeException('Bundle default is unavailable'); }
            }
            foreach ($options as $option) {
                if ((int)$option->getRequired() === 1 && empty($healthy[(int)$option->getId()])) { throw new RuntimeException('Bundle required option has no healthy choice'); }
            }
            if ((int)$bundle->getStatus() !== 1 || !$bundle->isSalable()) { throw new RuntimeException('Affected bundle unavailable'); }
            $bundles[$sku] = $healthy;
        }
        $keep = $repo->get('WANDS-SYN-S-KITCHEN-TABLETOP-02007', false, (int)$store->getId(), true);
        if ((int)$keep->getStatus() !== 1 || !$keep->isVisibleInSiteVisibility()
            || !str_contains((string)$keep->getImage(), 'c5664c84eea08cc7789bcfc45e266dc1dfe3bb7f61ef57fc4b9880d5574d8a9e')) {
            throw new RuntimeException('Approved canister cleanup not installed');
        }
        $quarantineResult = ['checked_skus' => $checked, 'configurable_families' => $families, 'bundles' => $bundles,
            'protected_keep' => $keep->getSku(), 'quarantine_sha256' => $a['quarantine-sha256'], 'passed' => true];
    }
    $after = $journal->protectedHashes();
    if ($before !== $after) { throw new RuntimeException('Cart probe changed protected data'); }
    $result = ['passed' => true, 'root' => $root, 'cases' => $results, 'quotes_saved' => 0,
        'orders_created' => 0, 'reservations_created' => 0, 'protected_before' => $before,
        'protected_after' => $after, 'quarantine' => $quarantineResult, 'request_sha256' => $a['request-sha256'], 'tool_sha256' => hash_file('sha256', __FILE__)];
    $file = fopen($a['output'], 'x'); chmod($a['output'], 0600);
    fwrite($file, json_encode($result, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR) . "\n"); fclose($file);
    echo json_encode(['passed' => true, 'cases' => count($results), 'quotes_saved' => 0]) . "\n";
}

if (realpath($_SERVER['SCRIPT_FILENAME'] ?? '') === __FILE__) { expansionLiveProbe(); }
