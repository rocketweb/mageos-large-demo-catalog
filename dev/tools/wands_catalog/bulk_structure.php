<?php
declare(strict_types=1);

class BulkCatalogStructure
{
    private array $journal = [];

    public function __construct(private PDO $pdo)
    {
    }

    private function select(string $table, array $where): array
    {
        $clauses = [];
        foreach (array_keys($where) as $column) {
            if (!preg_match('/^[a-z_]+$/', $column)) {
                throw new RuntimeException('Invalid selector');
            }
            $clauses[] = '`'.$column.'`=?';
        }
        if (!$clauses || !preg_match('/^[a-z_]+$/', $table)) {
            throw new RuntimeException('Unbounded selection');
        }
        $statement = $this->pdo->prepare('SELECT * FROM `'.$table.'` WHERE '.implode(' AND ', $clauses));
        $statement->execute(array_values($where));
        return $statement->fetchAll(PDO::FETCH_ASSOC);
    }

    private function canonical(?array $row): ?array
    {
        if ($row === null) {
            return null;
        }
        ksort($row);
        return array_map(static fn($value) => $value === null ? null : (string)$value, $row);
    }

    private function change(string $table, array $selector, ?array $before, ?array $after): void
    {
        $actual = $this->select($table, $selector);
        if (count($actual) !== ($before === null ? 0 : 1) || $this->canonical($actual[0] ?? null) !== $this->canonical($before)) {
            throw new RuntimeException('Structure drift: '.$table);
        }
        $where = implode(' AND ', array_map(static fn($column) => '`'.$column.'`=?', array_keys($selector)));
        if ($after === null) {
            $sql = 'DELETE FROM `'.$table.'` WHERE '.$where;
            $values = array_values($selector);
        } elseif ($before === null) {
            $sql = 'INSERT INTO `'.$table.'` (`'.implode('`,`', array_keys($after)).'`) VALUES ('.implode(',', array_fill(0, count($after), '?')).')';
            $values = array_values($after);
        } else {
            $sql = 'UPDATE `'.$table.'` SET '.implode(',', array_map(static fn($column) => '`'.$column.'`=?', array_keys($after))).' WHERE '.$where;
            $values = [...array_values($after), ...array_values($selector)];
        }
        $this->pdo->prepare($sql)->execute($values);
        $this->journal[] = ['table' => $table, 'selector' => $selector, 'before' => $before, 'after' => $this->select($table, $selector)[0] ?? null];
    }

    public function inspect(array $structure): array
    {
        $entities = [];
        foreach ($structure['all_skus'] as $sku) {
            if (!preg_match('/^WANDS-[A-Z0-9-]+$/', $sku)) {
                throw new RuntimeException('Non-WANDS target');
            }
            $found = $this->select('catalog_product_entity', ['sku' => $sku]);
            if (count($found) !== 1) {
                throw new RuntimeException('Missing exact product: '.$sku);
            }
            $entities[$sku] = $found[0];
        }
        $attributes = [];
        $query = $this->pdo->query("SELECT a.* FROM eav_attribute a INNER JOIN eav_entity_type t ON a.entity_type_id=t.entity_type_id WHERE t.entity_type_code='catalog_product'");
        foreach ($query->fetchAll(PDO::FETCH_ASSOC) as $row) {
            $attributes[$row['attribute_code']] = $row;
        }
        $missing = [];
        foreach ($structure['attribute_options'] as $code => $values) {
            if (!isset($attributes[$code]) || $attributes[$code]['backend_type'] !== 'int') {
                throw new RuntimeException('Missing or incompatible variant attribute: '.$code);
            }
            foreach ($values as $value) {
                $query = $this->pdo->prepare('SELECT v.option_id FROM eav_attribute_option_value v INNER JOIN eav_attribute_option o ON o.option_id=v.option_id WHERE o.attribute_id=? AND v.store_id=0 AND v.value=?');
                $query->execute([$attributes[$code]['attribute_id'], $value]);
                if ($query->fetchColumn() === false) {
                    $missing[] = ['attribute_id' => $attributes[$code]['attribute_id'], 'attribute_code' => $code, 'value' => $value];
                }
            }
        }
        $remove = [];
        foreach ($structure['retired_skus'] as $sku) {
            $id = $entities[$sku]['entity_id'];
            if ($this->select('catalog_product_bundle_selection', ['product_id' => $id])) {
                throw new RuntimeException('Retired child is used by a live bundle: '.$sku);
            }
            foreach (['catalog_product_super_link' => 'product_id', 'catalog_product_relation' => 'child_id'] as $table => $column) {
                foreach ($this->select($table, [$column => $id]) as $row) {
                    if (!in_array((string)$row['parent_id'], array_map('strval', array_column($entities, 'entity_id')), true)) {
                        throw new RuntimeException('Retired child has an unrelated parent');
                    }
                    $remove[$table][] = $row;
                }
            }
        }
        $parents = $structure['parent_axes'];
        foreach ($structure['conversions'] as $sku) {
            if ($entities[$sku]['type_id'] !== 'configurable') {
                throw new RuntimeException('Unexpected conversion source type: '.$sku);
            }
            $parents[$sku] = [];
        }
        foreach ($parents as $sku => $codes) {
            $keep = array_map(static fn($code) => (string)$attributes[$code]['attribute_id'], $codes);
            foreach ($this->select('catalog_product_super_attribute', ['product_id' => $entities[$sku]['entity_id']]) as $row) {
                if (!in_array((string)$row['attribute_id'], $keep, true)) {
                    foreach ($this->select('catalog_product_super_attribute_label', ['product_super_attribute_id' => $row['product_super_attribute_id']]) as $label) {
                        $remove['catalog_product_super_attribute_label'][] = $label;
                    }
                    $remove['catalog_product_super_attribute'][] = $row;
                }
            }
        }
        return ['entities' => $entities, 'new_options' => $missing, 'remove' => $remove,
            'counts' => ['products' => count($entities), 'new_options' => count($missing), 'conversions' => count($structure['conversions']),
                         'removed_rows' => array_map('count', $remove)]];
    }

    public function apply(array $structure, array $expected): array
    {
        $current = $this->inspect($structure);
        if ($current !== $expected) {
            throw new RuntimeException('Structure changed after preflight');
        }
        foreach ($current['new_options'] as $option) {
            $this->pdo->prepare('INSERT INTO eav_attribute_option (attribute_id,sort_order) VALUES (?,0)')->execute([$option['attribute_id']]);
            $id = $this->pdo->lastInsertId();
            $this->journal[] = ['table' => 'eav_attribute_option', 'selector' => ['option_id' => $id], 'before' => null, 'after' => $this->select('eav_attribute_option', ['option_id' => $id])[0]];
            $this->change('eav_attribute_option_value', ['option_id' => $id, 'store_id' => 0], null, ['option_id' => $id, 'store_id' => 0, 'value' => $option['value']]);
        }
        foreach (['catalog_product_super_attribute_label', 'catalog_product_super_link', 'catalog_product_relation', 'catalog_product_super_attribute'] as $table) {
            foreach ($current['remove'][$table] ?? [] as $row) {
                $key = match ($table) {
                    'catalog_product_super_attribute_label' => ['value_id' => $row['value_id']],
                    'catalog_product_super_link' => ['link_id' => $row['link_id']],
                    'catalog_product_relation' => ['parent_id' => $row['parent_id'], 'child_id' => $row['child_id']],
                    default => ['product_super_attribute_id' => $row['product_super_attribute_id']]
                };
                $this->change($table, $key, $row, null);
            }
        }
        foreach ($structure['conversions'] as $sku) {
            $row = $current['entities'][$sku];
            $this->change('catalog_product_entity', ['entity_id' => $row['entity_id']], $row,
                array_replace($row, ['type_id' => 'simple', 'has_options' => 0, 'required_options' => 0]));
        }
        return $this->journal;
    }

    public function rollback(array $journal): void
    {
        foreach (array_reverse($journal) as $operation) {
            if ($operation['table'] === 'eav_attribute_option' && $operation['before'] === null) {
                $query = $this->pdo->prepare('SELECT COUNT(*) FROM catalog_product_entity_int WHERE attribute_id=? AND value=?');
                $query->execute([$operation['after']['attribute_id'], $operation['after']['option_id']]);
                if ((int)$query->fetchColumn() !== 0) {
                    throw new RuntimeException('Restore product values before removing used new options');
                }
            }
            $this->change($operation['table'], $operation['selector'], $operation['after'], $operation['before']);
        }
    }
}
