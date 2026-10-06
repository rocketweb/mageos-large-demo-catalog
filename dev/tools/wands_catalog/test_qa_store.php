<?php
declare(strict_types=1);
require __DIR__ . '/expansion_catalog_journal.php';

function qaStoreTests(): array
{
    $a = getopt('', ['root:', 'package:', 'manifest-sha256:']);
    $root = realpath($a['root'] ?? ''); $package = realpath($a['package'] ?? '');
    if (!in_array($root, ['/Users/matt/code/mageos-latest', '/var/www/html'], true) || !$package
        || hash_file('sha256', $package . '/manifest.json') !== ($a['manifest-sha256'] ?? '')) {
        throw new RuntimeException('Exact existing store and pinned QA package required');
    }
    $fixtures = json_decode(file_get_contents($package . '/fixtures.json'), true, 512, JSON_THROW_ON_ERROR);
    if (count($fixtures) !== 127) { throw new RuntimeException('Expected 127 fixtures'); }
    require $root . '/app/bootstrap.php';
    $om = \Magento\Framework\App\Bootstrap::create($root, $_SERVER)->getObjectManager();
    $om->get(\Magento\Framework\App\State::class)->setAreaCode('frontend');
    $manager = $om->get(\Magento\Store\Model\StoreManagerInterface::class);
    $store = $manager->getStore('wands'); $manager->setCurrentStore($store);
    $repo = $om->get(\Magento\Catalog\Api\ProductRepositoryInterface::class);
    $env = require $root . '/app/etc/env.php'; $c = $env['db']['connection']['default'];
    $dsn = 'mysql:host=' . $c['host'] . ';dbname=' . $c['dbname'] . ';charset=utf8mb4';
    if (!empty($c['port'])) { $dsn .= ';port=' . (int)$c['port']; }
    $pdo = new PDO($dsn, $c['username'], $c['password'], [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    $prefix = $env['db']['table_prefix'] ?? ''; $journal = new ExpansionCatalogJournal($pdo, $prefix);
    $before = $journal->protectedHashes(); $checks = []; $cases = []; $caseResults = [];
    foreach (['quote', 'order'] as $area) {
        $directory = $root . '/pub/media/custom_options/' . $area . '/wands-qa-test';
        if (!is_dir($directory) && !mkdir($directory, 0775, true)) { throw new RuntimeException('Cannot stage private test option'); }
        $target = $directory . '/sample.pdf'; $source = $package . '/media/import/wands-qa-downloads/sample.pdf';
        if (is_file($target) && hash_file('sha256', $target) !== hash_file('sha256', $source)) { throw new RuntimeException('Option test file collision'); }
        if (!is_file($target) && !copy($source, $target)) { throw new RuntimeException('Cannot copy fixture PDF'); }
    }
    $check = static function (bool $passed, string $id, $expected = null, $actual = null) use (&$checks): void {
        $checks[] = compact('id', 'passed', 'expected', 'actual');
    };
    $product = static fn(string $sku) => $repo->get($sku, false, (int)$store->getId(), true)->setCustomerGroupId(0);
    $cartCase = static function (string $id, string $sku, array $request, bool $accept, ?bool $shipping = null, ?float $price = null) use (&$cases): void {
        $cases[] = compact('id', 'sku', 'request', 'accept', 'shipping', 'price');
    };
    $index = [];
    foreach ($fixtures as $fixture) {
        $row = $fixture['product']; $sku = $row['sku']; $p = $product($sku); $index[$sku] = $fixture;
        $check($p->getTypeId() === $row['product_type'], $sku . ':type', $row['product_type'], $p->getTypeId());
        $check($p->getName() === $row['name'], $sku . ':name', $row['name'], $p->getName());
        $check((int)$p->getStatus() === ((int)$row['product_online'] ? 1 : 2), $sku . ':status');
        $check(array_map('intval', $p->getWebsiteIds()) === [(int)$store->getWebsiteId()], $sku . ':website');
        foreach (['color', 'wands_finish', 'wands_size'] as $code) {
            if (!empty($row[$code])) { $check((string)$p->getAttributeText($code) === $row[$code], $sku . ':' . $code, $row[$code], $p->getAttributeText($code)); }
        }
        if ($p->getTypeId() === 'simple' && $fixture['source_sku']) {
            $image = $root . '/pub/media/catalog/product' . $p->getImage();
            $lineage = json_decode(file_get_contents($package . '/media-lineage.json'), true, 512, JSON_THROW_ON_ERROR)[$sku];
            $check(is_file($image) && hash_file('sha256', $image) === $lineage['sha256'], $sku . ':image');
        }
        if (in_array($p->getTypeId(), ['virtual', 'downloadable'], true)) { $check($p->isVirtual(), $sku . ':nonphysical'); }
        if ($p->getTypeId() === 'downloadable') {
            $links = array_values($p->getTypeInstance()->getLinks($p));
            $check(count($links) === $fixture['expected']['links'], $sku . ':link-count');
            $check((int)$p->getLinksPurchasedSeparately() === (int)$row['links_purchased_separately'], $sku . ':link-selection');
            foreach ($links as $link) {
                $check((int)$link->getNumberOfDownloads() === $fixture['expected']['downloads_per_link'], $sku . ':limit');
                $check((int)$link->getIsShareable() === $fixture['expected']['shareable'], $sku . ':sharing');
                $check($link->getLinkType() === 'file' && is_file($root . '/pub/media/downloadable/files/links' . $link->getLinkFile()), $sku . ':download-file');
                $check($link->getSampleType() === 'file' && is_file($root . '/pub/media/downloadable/files/link_samples' . $link->getSampleFile()), $sku . ':link-sample');
            }
            $samples = $p->getTypeInstance()->getSamples($p);
            $check(count($samples) === 1, $sku . ':sample-count');
            foreach ($samples as $sample) { $check(is_file($root . '/pub/media/downloadable/files/samples' . $sample->getSampleFile()), $sku . ':sample-file'); }
            $cartCase($sku . ':no-links', $sku, ['qty' => 1], !(int)$row['links_purchased_separately'], false, (float)$row['price']);
            $cartCase($sku . ':selected-links', $sku, ['qty' => 1, 'links' => array_map(static fn($l) => (int)$l->getId(), $links)], true, false,
                (int)$row['links_purchased_separately'] ? array_sum(array_map(static fn($l) => (float)$l->getPrice(), $links)) : (float)$row['price']);
        } elseif ($p->getTypeId() === 'configurable') {
            $groups = array_map(static fn($s) => array_column(array_map(static fn($v) => explode('=', $v, 2), explode(',', $s)), 1, 0), explode('|', $row['configurable_variations']));
            $q = $pdo->prepare('SELECT c.sku FROM ' . $prefix . 'catalog_product_super_link l JOIN ' . $prefix . 'catalog_product_entity c ON c.entity_id=l.product_id WHERE l.parent_id=? ORDER BY c.sku');
            $q->execute([$p->getId()]); $actual = $q->fetchAll(PDO::FETCH_COLUMN); $expected = array_column($groups, 'sku'); sort($expected);
            $check($actual === $expected, $sku . ':child-links', $expected, $actual);
            $attributes = $p->getTypeInstance()->getConfigurableAttributes($p);
            $axes = array_map(static fn($x) => $x->getProductAttribute()->getAttributeCode(), $attributes->getItems()); sort($axes);
            $expectedAxes = $fixture['expected']['axes']; sort($expectedAxes); $check($axes === $expectedAxes, $sku . ':axes', $expectedAxes, $axes);
            $cartCase($sku . ':missing-selection', $sku, ['qty' => 1], false);
            foreach ($groups as $g) {
                $child = $product($g['sku']); $options = [];
                foreach ($g as $code => $value) {
                    if ($code === 'sku') { continue; }
                    $attr = $om->get(\Magento\Eav\Model\Config::class)->getAttribute('catalog_product', $code);
                    $options[(int)$attr->getAttributeId()] = $child->getData($code);
                }
                $expected = (int)$child->getStatus() === 1 && $g['sku'] !== 'WANDS-QA-CHILD-OUT-OF-STOCK-01';
                $cartCase($sku . ':' . $g['sku'], $sku, ['qty' => 1, 'super_attribute' => $options], $expected, $child->getTypeId() === 'simple', (float)$child->getPrice());
            }
        } elseif ($p->getTypeId() === 'bundle') {
            $options = $p->getTypeInstance()->getOptionsCollection($p);
            $selections = $p->getTypeInstance()->getSelectionsCollection($options->getAllIds(), $p);
            $check(count($options) === 2 && count($selections) === 4, $sku . ':bundle-shape');
            $check((int)$p->getPriceType() === ($row['bundle_price_type'] === 'fixed' ? 1 : 0), $sku . ':price-type');
            $chosen = []; $quantities = [];
            foreach ($options as $option) {
                foreach ($selections as $selection) {
                    if ((int)$selection->getOptionId() === (int)$option->getId() && (int)$selection->getIsDefault() === 1) {
                        $chosen[(int)$option->getId()] = in_array($option->getType(), ['checkbox', 'multi'], true) ? [(int)$selection->getSelectionId()] : (int)$selection->getSelectionId();
                        $quantities[(int)$option->getId()] = 1;
                    }
                }
            }
            $cartCase($sku . ':missing-options', $sku, ['qty' => 1], false);
            $cartCase($sku . ':selected-options', $sku, ['qty' => 1, 'bundle_option' => $chosen, 'bundle_option_qty' => $quantities], true, $fixture['expected']['shipping_required']);
        } elseif ($p->getTypeId() === 'grouped') {
            $q = $pdo->prepare('SELECT c.sku FROM ' . $prefix . 'catalog_product_link l JOIN ' . $prefix . 'catalog_product_entity c ON c.entity_id=l.linked_product_id WHERE l.product_id=? AND l.link_type_id=3 ORDER BY c.sku');
            $q->execute([$p->getId()]); $actual = $q->fetchAll(PDO::FETCH_COLUMN); $expected = $fixture['expected']['associated_skus']; sort($expected);
            $check($actual === $expected, $sku . ':grouped-links', $expected, $actual);
            $quantities = []; $shipping = false;
            foreach ($fixture['expected']['associated_skus'] as $childSku) {
                $child = $product($childSku);
                if ((int)$child->getStatus() === 1 && $childSku !== 'WANDS-QA-COMPONENT-11') {
                    $quantities[(int)$child->getId()] = 1; $shipping = $shipping || !$child->isVirtual();
                }
            }
            $zeroes = [];
            foreach ($fixture['expected']['associated_skus'] as $childSku) { $zeroes[(int)$product($childSku)->getId()] = 0; }
            $cartCase($sku . ':zero-quantities', $sku, ['qty' => 1, 'super_group' => $zeroes], false);
            $cartCase($sku . ':selected-quantities', $sku, ['qty' => 1, 'super_group' => $quantities], true, $shipping);
        } elseif (isset($row['custom_options'])) {
            $options = array_values($p->getOptions()); $check(count($options) === 1, $sku . ':option-count');
            if (!$options) { continue; }
            $option = $options[0]; $kind = $fixture['expected']['option_type']; $id = (int)$option->getId();
            $check($option->getType() === $kind, $sku . ':option-type');
            $check((int)$option->getIsRequire() === (int)$fixture['expected']['required'], $sku . ':required');
            $cartCase($sku . ':missing-option', $sku, ['qty' => 1], !$fixture['expected']['required'], true, 200);
            $value = 'Synthetic QA text';
            if (in_array($kind, ['drop_down', 'radio', 'checkbox', 'multiple'], true)) {
                $values = array_values($option->getValues()); $check(count($values) === 2, $sku . ':option-values');
                $value = (int)$values[0]->getId();
                if (in_array($kind, ['checkbox', 'multiple'], true)) { $value = [$value]; }
            } elseif (in_array($kind, ['date', 'date_time', 'time'], true)) {
                $value = ['date' => '10/06/2026', 'day' => 6, 'month' => 10, 'year' => 2026, 'hour' => 10, 'minute' => 30, 'day_part' => 'am'];
            } elseif ($kind === 'file') {
                // Exercise native existing-file validation without forging a PHP HTTP upload.
                $path = $root . '/pub/media/custom_options/quote/wands-qa-test/sample.pdf';
                $value = ['type' => 'application/pdf', 'title' => 'sample.pdf', 'quote_path' => 'custom_options/quote/wands-qa-test/sample.pdf',
                    'order_path' => 'custom_options/order/wands-qa-test/sample.pdf', 'fullpath' => $path, 'size' => filesize($path), 'secret_key' => substr(hash_file('sha256', $path), 0, 20)];
                $check($option->getFileExtension() === 'pdf,txt', $sku . ':file-extensions', 'pdf,txt', $option->getFileExtension());
            }
            $cartCase($sku . ':valid-option', $sku, ['qty' => 1, 'options' => [$id => $value]], true, true, 200 + $fixture['expected']['first_option_price_delta']);
        } elseif (isset($fixture['expected']['price_before_tax'])) {
            $cartCase($sku . ':price', $sku, ['qty' => 1], true, true, (float)$fixture['expected']['price_before_tax']);
            if (isset($fixture['expected']['quantity_five_price_per_unit'])) { $cartCase($sku . ':tier-five', $sku, ['qty' => 5], true, true, 70); }
        } elseif (str_starts_with($sku, 'WANDS-QA-STOCK-')) {
            $requests = match (substr($sku, 15)) {
                'OUT' => [[1, false]], 'BACKORDER', 'BACKORDER-NOTIFY', 'UNMANAGED' => [[1, true]],
                'MINIMUM' => [[1, false], [3, true]], 'MAXIMUM' => [[6, false], [5, true]],
                'INCREMENTS' => [[1, false], [2, true]], 'DECIMAL' => [[0.25, false], [0.5, true]],
                default => throw new RuntimeException('Unknown stock fixture'),
            };
            foreach ($requests as [$qty, $ok]) { $cartCase($sku . ':qty-' . $qty, $sku, ['qty' => $qty], $ok, true); }
        } elseif (isset($fixture['expected']['add_to_cart']) && (int)$row['product_online'] === 1) {
            $cartCase($sku . ':cart', $sku, ['qty' => 1], $fixture['expected']['add_to_cart'] === 'accepted', !$p->isVirtual(), (float)$row['price']);
        }
    }
    foreach ($cases as $case) {
        $p = $product($case['sku']);
        foreach ($p->getOptions() as $option) {
            if ($option->getType() === 'file') {
                $_FILES['options_' . $option->getId() . '_file'] = ['name' => '', 'type' => '', 'tmp_name' => '', 'size' => 0, 'error' => UPLOAD_ERR_NO_FILE];
            }
        }
        $quote = $om->create(\Magento\Quote\Model\Quote::class)->setStore($store)->setCustomerIsGuest(true)->setCustomerGroupId(0);
        $quote->setBaseCurrencyCode('USD')->setQuoteCurrencyCode('USD')->setStoreCurrencyCode('USD')->setBaseToQuoteRate(1)->setStoreToBaseRate(1);
        $accepted = false; $message = null; $items = [];
        try {
            $item = $quote->addProduct($p, new \Magento\Framework\DataObject($case['request']));
            if (is_string($item)) { $message = $item; }
            else {
                if ($case['price'] !== null) {
                    // New unsaved quotes have no address collection until initialized.
                    // Empty address objects let native subtotal collectors apply quantity prices.
                    $quote->getBillingAddress(); $quote->getShippingAddress(); $quote->collectTotals();
                }
                foreach ($quote->getAllItems() as $line) {
                    $line->calcRowTotal();
                    $items[] = ['sku' => $line->getSku(), 'qty' => (float)$line->getQty(), 'price' => (float)$line->getCalculationPrice(), 'error' => (bool)$line->getHasError()];
                }
                $accepted = !array_filter($items, static fn($x) => $x['error']);
                if (!$accepted) { $message = implode(';', $quote->getErrors()); }
            }
        } catch (Throwable $e) { $message = $e->getMessage(); }
        $passed = $accepted === $case['accept'];
        if ($accepted && $case['shipping'] !== null) { $passed = $passed && !$quote->isVirtual() === $case['shipping']; }
        if ($accepted && $case['price'] !== null) {
            $visible = $quote->getAllVisibleItems();
            $passed = $passed && count($visible) === 1 && abs((float)$visible[0]->getCalculationPrice() - $case['price']) < 0.001;
        }
        $passed = $passed && !$quote->getId();
        $caseResults[] = $case + ['passed' => $passed, 'accepted' => $accepted, 'shipping_required' => !$quote->isVirtual(), 'message' => $message, 'items' => $items];
    }
    $mixed = [];
    foreach ([['WANDS-QA-COMPONENT-01'], ['WANDS-QA-VIRTUAL-01'], ['WANDS-QA-DOWNLOAD-01'],
        ['WANDS-QA-COMPONENT-01', 'WANDS-QA-VIRTUAL-01', 'WANDS-QA-DOWNLOAD-01']] as $skus) {
        $quote = $om->create(\Magento\Quote\Model\Quote::class)->setStore($store)->setCustomerIsGuest(true)->setCustomerGroupId(0);
        foreach ($skus as $sku) { $quote->addProduct($product($sku), new \Magento\Framework\DataObject(['qty' => 1])); }
        $shipping = in_array('WANDS-QA-COMPONENT-01', $skus, true);
        $mixed[] = ['skus' => $skus, 'passed' => !$quote->getId() && !$quote->isVirtual() === $shipping, 'shipping_required' => !$quote->isVirtual()];
    }
    $after = $journal->protectedHashes();
    $failed = count(array_filter([...$checks, ...$caseResults, ...$mixed], static fn($x) => !$x['passed']));
    return ['schema' => 1, 'root' => $root, 'verified_at' => gmdate('c'), 'manifest_sha256' => $a['manifest-sha256'],
        'passed' => !$failed && $before === $after, 'failed_checks' => $failed, 'checks' => $checks, 'cart_cases' => $caseResults,
        'mixed_carts' => $mixed, 'protected_tables_unchanged' => $before === $after, 'quotes_saved' => 0, 'orders_created' => 0, 'reservations_created' => 0,
        'limits' => ['unsaved guest USD quotes; default totals collected for price checks without a customer address', 'file option uses existing-file metadata, not HTTP upload', 'no checkout/payment/order/download-entitlement qualification']];
}

try {
    $report = qaStoreTests(); echo json_encode($report, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES) . "\n";
    exit($report['passed'] ? 0 : 1);
} catch (Throwable $e) { fwrite(STDERR, 'QA store tests failed: ' . $e->getMessage() . "\n"); exit(1); }
