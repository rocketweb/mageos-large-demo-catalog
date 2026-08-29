<?php

declare(strict_types=1);

if ($argc !== 3) {
    fwrite(STDERR, "Usage: php prepare-large-catalog-profile.php source.xml target.xml\n");
    exit(2);
}

$sourcePath = (string)$argv[1];
$targetPath = (string)$argv[2];
$document = new DOMDocument();

if (!$document->load($sourcePath, LIBXML_NONET)) {
    throw new RuntimeException('Unable to load the Mage-OS performance profile.');
}

$xpath = new DOMXPath($document);
$catalogOnlyValues = [
    '/config/profile/admin_users' => '0',
    '/config/profile/customers' => '0',
    '/config/profile/catalog_price_rules' => '0',
    '/config/profile/cart_price_rules' => '0',
    '/config/profile/coupon_codes' => '0',
    '/config/profile/orders' => '0',
];

foreach ($catalogOnlyValues as $expression => $value) {
    $nodes = $xpath->query($expression);

    if ($nodes === false || $nodes->length !== 1 || !$nodes->item(0) instanceof DOMElement) {
        throw new RuntimeException('Required performance profile value is missing: ' . $expression);
    }

    $nodes->item(0)->nodeValue = $value;
}

$configurationNodes = $xpath->query('/config/profile/configs/config');

if ($configurationNodes === false) {
    throw new RuntimeException('Unable to inspect performance profile configuration changes.');
}

$configurationNodesToRemove = [];

foreach ($configurationNodes as $configurationNode) {
    $configurationNodesToRemove[] = $configurationNode;
}

foreach ($configurationNodesToRemove as $configurationNode) {
    $configurationNode->parentNode?->removeChild($configurationNode);
}

$document->formatOutput = true;

if ($document->save($targetPath) === false) {
    throw new RuntimeException('Unable to save the catalog-only Mage-OS performance profile.');
}
