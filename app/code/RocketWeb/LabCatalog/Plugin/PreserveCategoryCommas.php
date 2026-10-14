<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Plugin;

use Magento\CatalogImportExport\Model\Import\Product\CategoryProcessor;
use RocketWeb\LabCatalog\Model\Catalog\NavigationTaxonomy;

class PreserveCategoryCommas
{
    private const PATH_SEPARATOR = "\x1F";

    public function beforeUpsertCategories(
        CategoryProcessor $subject,
        ?string $categoriesString,
        string $categoriesSeparator,
    ): array {
        if ($categoriesString !== null
            && str_starts_with($categoriesString, 'WANDS Catalog/')
        ) {
            if (str_contains($categoriesString, self::PATH_SEPARATOR)) {
                throw new \InvalidArgumentException('WANDS category paths contain a reserved separator.');
            }
            // Exported assignments repeat the root; commas within a path are category-name data.
            $paths = $categoriesSeparator === ','
                ? preg_split('/,\s*(?=WANDS Catalog\/)/', $categoriesString)
                : explode($categoriesSeparator, $categoriesString);
            $paths = array_map([NavigationTaxonomy::class, 'normalizePath'], $paths);
            $separator = $categoriesSeparator === ',' ? self::PATH_SEPARATOR : $categoriesSeparator;
            return [implode($separator, $paths), $separator];
        }

        return [$categoriesString, $categoriesSeparator];
    }
}
