<?php
declare(strict_types=1);

/** Prepare and apply only the named WANDS catalog patches and variant options. */
final class ExpansionSetup
{
    public const PATCHES = [
        'RocketWeb\\LabCatalog\\Setup\\Patch\\Data\\AddProductAttributes',
        'RocketWeb\\LabCatalog\\Setup\\Patch\\Data\\AddMerchandisingAttributes',
        'RocketWeb\\LabCatalog\\Setup\\Patch\\Data\\AttachColorToDefaultAttributeSet',
        'RocketWeb\\LabCatalog\\Setup\\Patch\\Data\\AddRealismAttributes',
        'RocketWeb\\LabCatalog\\Setup\\Patch\\Data\\AddDepthAttributes',
        'RocketWeb\\LabCatalog\\Setup\\Patch\\Data\\AddSpecificationDisclosure',
    ];
    public const ATTRIBUTES = ['color', 'wands_size', 'wands_finish', 'wands_length', 'wands_material',
        'wands_seat_height', 'wands_light_count', 'wands_seating_capacity', 'wands_piece_count', 'wands_pack_size'];

    public static function missing(array $options, array $existing): array
    {
        $missing = [];
        foreach ($options as $code => $labels) {
            if (!in_array($code, self::ATTRIBUTES, true) || !is_array($labels) || !$labels) {
                throw new RuntimeException('Unexpected configurable attribute options');
            }
            $seen = array_map('strtolower', $existing[$code] ?? []); $requested = [];
            foreach ($labels as $label) {
                if (!is_string($label) || trim($label) !== $label || $label === '' || strlen($label) > 200
                    || in_array(strtolower($label), $requested, true)) { throw new RuntimeException('Invalid or duplicate variant label'); }
                $requested[] = strtolower($label);
                if (!in_array(strtolower($label), $seen, true)) { $missing[$code][] = $label; }
            }
        }
        return $missing;
    }
}

function expansionSetupMain(): void
{
    $a = getopt('', ['root:', 'options:', 'options-sha256:', 'action:', 'plan:', 'plan-sha256:', 'output:']);
    $root = realpath($a['root'] ?? ''); $input = realpath($a['options'] ?? '');
    $parent = realpath(dirname($a['output'] ?? '')); $action = $a['action'] ?? 'inspect';
    if (!in_array($root, ['/Users/matt/code/mageos-latest', '/var/www/html'], true)
        || !in_array($action, ['inspect', 'apply'], true) || !$input || !str_starts_with($input, $root . '/var/')
        || hash_file('sha256', $input) !== ($a['options-sha256'] ?? '') || !$parent
        || !str_starts_with($parent, $root . '/var/') || (fileperms($parent) & 0077) || file_exists($a['output'])) {
        throw new RuntimeException('Exact existing root, pinned options and fresh private receipt required');
    }
    require $root . '/app/bootstrap.php';
    $manager = Magento\Framework\App\Bootstrap::create(BP, $_SERVER)->getObjectManager();
    $resource = $manager->get(Magento\Framework\App\ResourceConnection::class); $db = $resource->getConnection();
    $options = json_decode(file_get_contents($input), true, 512, JSON_THROW_ON_ERROR);
    $history = $manager->get(Magento\Framework\Setup\Patch\PatchHistory::class); $pending = []; $existing = []; $attributes = [];
    foreach (ExpansionSetup::PATCHES as $class) { if (!$history->isApplied($class)) { $pending[] = $class; } }
    $setup = $manager->get(Magento\Eav\Setup\EavSetupFactory::class)->create();
    foreach ($options as $code => $labels) {
        if (!in_array($code, ExpansionSetup::ATTRIBUTES, true)) { throw new RuntimeException('Attribute outside WANDS scope'); }
        $attribute = $setup->getAttribute(Magento\Catalog\Model\Product::ENTITY, $code);
        if (!$attribute || empty($attribute['attribute_id'])) { $attributes[$code] = null; continue; }
        if ($attribute['frontend_input'] !== 'select' || (int)$attribute['is_global'] !== 1) {
            throw new RuntimeException('Incompatible configurable attribute: ' . $code);
        }
        $attributes[$code] = (int)$attribute['attribute_id'];
        $select = $db->select()->from(['o' => $resource->getTableName('eav_attribute_option')], [])
            ->join(['v' => $resource->getTableName('eav_attribute_option_value')], 'o.option_id=v.option_id', ['value'])
            ->where('o.attribute_id=?', $attributes[$code])->where('v.store_id=0')->order('o.option_id');
        $existing[$code] = $db->fetchCol($select);
    }
    $scope = ['root' => $root, 'tool_sha256' => hash_file('sha256', __FILE__),
        'env_sha256' => hash_file('sha256', $root . '/app/etc/env.php'),
        'options_sha256' => $a['options-sha256'], 'pending_patches' => $pending, 'attributes_before' => $attributes,
        'existing_options' => $existing, 'missing_options' => ExpansionSetup::missing($options, $existing)];
    if ($action === 'apply') {
        $plan = realpath($a['plan'] ?? '');
        if (!$plan || !str_starts_with($plan, $root . '/var/') || (fileperms($plan) & 0077)
            || hash_file('sha256', $plan) !== ($a['plan-sha256'] ?? '')) { throw new RuntimeException('Setup preview changed'); }
        $reviewed = json_decode(file_get_contents($plan), true, 512, JSON_THROW_ON_ERROR);
        $age = time() - strtotime($reviewed['created_at']);
        if (($reviewed['scope'] ?? null) !== $scope || $age < 0 || $age > 3600) {
            throw new RuntimeException('Setup state changed or preview is stale');
        }
        // The enclosing installation coordinator captures catalog-row and
        // module inverses before this operation. Never run setup:upgrade here.
        foreach ($pending as $class) { $manager->create($class)->apply(); $history->fixPatch($class); }
        foreach ($scope['missing_options'] as $code => $labels) {
            $id = $setup->getAttributeId(Magento\Catalog\Model\Product::ENTITY, $code);
            if (!$id) { throw new RuntimeException('Named catalog patches did not create ' . $code); }
            // Patches may already have inserted these exact labels.
            $actual = $db->fetchCol($db->select()->from(['o' => $resource->getTableName('eav_attribute_option')], [])
                ->join(['v' => $resource->getTableName('eav_attribute_option_value')], 'o.option_id=v.option_id', ['value'])
                ->where('o.attribute_id=?', $id)->where('v.store_id=0'));
            $missing = ExpansionSetup::missing([$code => $labels], [$code => $actual]);
            if (!empty($missing[$code])) { $setup->addAttributeOption(['attribute_id' => $id, 'values' => $missing[$code]]); }
        }
        foreach ($options as $code => $labels) {
            $id = $setup->getAttributeId(Magento\Catalog\Model\Product::ENTITY, $code);
            $actual = $db->fetchCol($db->select()->from(['o' => $resource->getTableName('eav_attribute_option')], [])
                ->join(['v' => $resource->getTableName('eav_attribute_option_value')], 'o.option_id=v.option_id', ['value'])
                ->where('o.attribute_id=?', $id)->where('v.store_id=0'));
            if (ExpansionSetup::missing([$code => $labels], [$code => $actual])) {
                throw new RuntimeException('Missing configured variant after setup: ' . $code);
            }
        }
    }
    $result = ['created_at' => gmdate('c'), 'action' => $action, 'scope' => $scope,
        'database_writes' => $action === 'apply', 'outside_patches_applied' => 0];
    $handle = fopen($a['output'], 'x'); chmod($a['output'], 0600);
    fwrite($handle, json_encode($result, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR) . "\n"); fclose($handle);
    echo json_encode(['action' => $action, 'pending_patches' => count($pending),
        'missing_options' => array_sum(array_map('count', $scope['missing_options']))]) . "\n";
}

if (realpath($_SERVER['SCRIPT_FILENAME'] ?? '') === __FILE__) { expansionSetupMain(); }
