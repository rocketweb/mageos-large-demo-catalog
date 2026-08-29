<?php

declare(strict_types=1);

use Magento\Framework\App\Bootstrap;
use Magento\Framework\App\Config\Storage\WriterInterface;
use Magento\Framework\View\DesignInterface;
use Magento\Theme\Model\ResourceModel\Theme\CollectionFactory;

if ($argc !== 3) {
    fwrite(STDERR, "Usage: php activate-theme.php /path/to/mageos Vendor/theme\n");
    exit(2);
}

$fixtureRoot = rtrim((string)$argv[1], DIRECTORY_SEPARATOR);
$themePath = (string)$argv[2];

if (!preg_match('/\A[A-Z][A-Za-z0-9_]*\/[a-z][a-z0-9_-]*\z/D', $themePath)) {
    fwrite(STDERR, "Theme path must use Vendor/theme format.\n");
    exit(2);
}

if (!is_file($fixtureRoot . '/app/bootstrap.php')) {
    fwrite(STDERR, "Mage-OS bootstrap not found: {$fixtureRoot}\n");
    exit(2);
}

require $fixtureRoot . '/app/bootstrap.php';

$bootstrap = Bootstrap::create(BP, $_SERVER);
$objectManager = $bootstrap->getObjectManager();
/** @var CollectionFactory $collectionFactory */
$collectionFactory = $objectManager->get(CollectionFactory::class);
$theme = $collectionFactory->create()->getThemeByFullPath('frontend/' . $themePath);
$themeId = (int)$theme->getId();

if ($themeId < 1 || $theme->getThemePath() !== $themePath) {
    throw new RuntimeException("Registered frontend theme not found: {$themePath}");
}

$objectManager->get(WriterInterface::class)->save(
    DesignInterface::XML_PATH_THEME_ID,
    (string)$themeId
);

fwrite(STDOUT, "Activated {$themePath} as fixture theme {$themeId}.\n");
