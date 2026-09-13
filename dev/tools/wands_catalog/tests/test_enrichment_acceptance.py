import json
import os
from pathlib import Path
import subprocess
import unittest


@unittest.skipUnless(os.environ.get('WANDS_TEST_PHP'), 'Set WANDS_TEST_PHP to PHP 8.4')
class EnrichmentAcceptanceTest(unittest.TestCase):
    def test_comparison_detects_missing_wrong_and_unexpected_values(self):
        helper = Path(__file__).resolve().parents[1] / 'distribution/acceptance/enrichment_checks.php'
        script = r'''<?php
require $argv[1];
$rows = ['A' => ['description'=>'Details', 'url_key'=>'a', 'lab_spec_style'=>'Modern',
    'lab_spec_width_cm'=>'10.25', 'lab_spec_care'=>'', 'lab_spec_disclosure'=>'Synthetic lab data',
    'related_skus'=>'B,C', 'crosssell_skus'=>'D']];
$values = ['A' => ['description'=>'Details', 'url_key'=>'a', 'lab_spec_style'=>'Modern',
    'lab_spec_width_cm'=>'10.2500', 'lab_spec_disclosure'=>'Synthetic lab data']];
$metadata = ['lab_spec_style'=>['backend_type'=>'int', 'frontend_input'=>'select'],
    'lab_spec_width_cm'=>['backend_type'=>'decimal'], 'lab_spec_care'=>['backend_type'=>'text'],
    'lab_spec_disclosure'=>['backend_type'=>'text', 'is_visible_on_front'=>1, 'is_comparable'=>1]];
$links = ['A'=>['related_skus'=>['C','B'], 'crosssell_skus'=>['D']]];
$run = function ($actual, $meta, $actualLinks) use ($rows) {
    $failures=[]; $checks=0;
    wandsVerifyEnrichment($rows, $actual, $meta, $actualLinks,
        function ($ok, $message) use (&$failures, &$checks) { $checks++; if (!$ok) { $failures[]=$message; } });
    return ['checks'=>$checks, 'failures'=>$failures];
};
$results=['good'=>$run($values,$metadata,$links)];
foreach (['lab_spec_style'=>'Rustic','lab_spec_width_cm'=>'nonsense','lab_spec_care'=>'Unexpected',
    'lab_spec_disclosure'=>'','description'=>'Lost specs','url_key'=>'changed'] as $code=>$value) {
    $changed=$values; $changed['A'][$code]=$value; $results[$code]=$run($changed,$metadata,$links);
}
$changed=$metadata; unset($changed['lab_spec_style']); $results['missing_attribute']=$run($values,$changed,$links);
$changed=$metadata; $changed['lab_spec_disclosure']['is_visible_on_front']=0;
$results['hidden_notice']=$run($values,$changed,$links);
$changed=$links; $changed['A']['related_skus'][]='EXTRA'; $results['extra_link']=$run($values,$metadata,$changed);
$changed=$links; $changed['A']['related_skus']=['B']; $results['missing_link']=$run($values,$metadata,$changed);
$changed=$links; $changed['A']['related_skus']=['B','B','C']; $results['duplicate_link']=$run($values,$metadata,$changed);
echo json_encode($results);
'''
        result = subprocess.run([os.environ['WANDS_TEST_PHP'], '-r', script.removeprefix('<?php\n'), str(helper)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        results = json.loads(result.stdout)
        self.assertEqual(results['good']['failures'], [])
        self.assertGreater(results['good']['checks'], 8)
        for name, result in results.items():
            if name != 'good':
                self.assertTrue(result['failures'], name)


if __name__ == '__main__':
    unittest.main()
