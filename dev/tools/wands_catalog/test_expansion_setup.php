<?php
declare(strict_types=1);
require __DIR__ . '/expansion_setup.php';
function expect(bool $test): void { if (!$test) { throw new RuntimeException('Failed setup check'); } }
expect(ExpansionSetup::missing(['color' => ['Black', 'Terracotta']], ['color' => ['black']]) === ['color' => ['Terracotta']]);
expect(ExpansionSetup::missing(['wands_light_count' => ['1', '4']], ['wands_light_count' => ['1', '4']]) === []);
foreach ([['unrelated_attribute' => ['x']], ['color' => ['Black', 'black']], ['color' => [' Black']], ['color' => [4]]] as $bad) {
    $rejected = false;
    try { ExpansionSetup::missing($bad, []); } catch (RuntimeException) { $rejected = true; }
    expect($rejected);
}
echo "PASS: case-insensitive reuse, exact missing variants, duplicate and out-of-scope rejection\n";
