<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Model\Import;

use RocketWeb\LabCatalog\Model\Catalog\NavigationTaxonomy;

class CategoryProcessor extends \Magento\CatalogImportExport\Model\Import\Product\CategoryProcessor
{
    protected function initCategories()
    {
        parent::initCategories();
        // Reuse existing IDs while an older tree awaits post-import curation.
        foreach ($this->categories as $path => $id) {
            $canonicalPath = mb_strtolower(NavigationTaxonomy::normalizePath($path));
            if ($canonicalPath === $path) {
                continue;
            }
            if (isset($this->categories[$canonicalPath]) && $this->categories[$canonicalPath] !== $id) {
                throw new \RuntimeException('Conflicting WANDS category paths: ' . $path . ' and ' . $canonicalPath);
            }
            $this->categories[$canonicalPath] = $id;
        }
        return $this;
    }
}
