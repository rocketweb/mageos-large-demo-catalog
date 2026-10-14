<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Model\Catalog;

class NavigationTaxonomy
{
    public const DEPARTMENTS = [
        'DIY', 'Furniture', 'Decor', 'Bed & Bath', 'Kitchen', 'Outdoor', 'Storage', 'Kids', 'Pets',
    ];

    public const RENAMES = [
        'Kitchen & Tabletop' => 'Kitchen',
        'Décor & Pillows' => 'Decor',
        'Storage & Organization' => 'Storage',
        'Baby & Kids' => 'Kids',
        'Pet' => 'Pets',
        'Home Improvement' => 'DIY',
    ];

    public const CHILD_DEPARTMENTS = ['Lighting' => 'Decor', 'Rugs' => 'Decor'];

    public const URL_KEYS = ['DIY' => 'diy'];

    public static function normalizePath(string $path): string
    {
        $parts = explode('/', $path, 3);
        if (count($parts) < 2 || strcasecmp($parts[0], 'WANDS Catalog') !== 0) {
            return $path;
        }
        foreach (self::RENAMES as $old => $new) {
            if (mb_strtolower($parts[1]) === mb_strtolower($old)) {
                $parts[1] = $new;
                break;
            }
        }
        foreach (self::CHILD_DEPARTMENTS as $child => $parent) {
            if (mb_strtolower($parts[1]) === mb_strtolower($child)) {
                $parts[1] = $parent . '/' . $child;
                break;
            }
        }
        return implode('/', $parts);
    }
}
