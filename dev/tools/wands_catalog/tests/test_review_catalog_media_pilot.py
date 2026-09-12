import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from plan_catalog_media_repairs import CHECKS
from prepare_catalog import sha256
from review_catalog_media_pilot import classify, bind_observations, render, build


def observation():
    return {'root_sku': 'WANDS-000001', 'image_sha256': 'a' * 64, 'definition_sha256': 'b' * 64,
            'runtime_prompt_sha256': 'c' * 64, 'checks': {key: 'pass' for key in CHECKS},
            'review_method': 'direct_image_inspection', 'review_date': '2026-09-10',
            'finding': 'One coherent object.', 'next_direction': 'Keep local; no publication approval.'}


def case():
    return {'root_sku': 'WANDS-000001', 'candidate_filename': 'candidate.webp',
            'definition_sha256': 'b' * 64, 'runtime_prompt_sha256': 'c' * 64,
            'original_reference_evidence': {'path': '/tmp/original.jpg', 'sha256': 'd' * 64},
            'pilot_case': {'challenge': 'Identity'}, 'token_count': 144,
            'runtime_prompt': '<script>unsafe & quoted</script>',
            'acceptance_contract': {'product_name': '<img src=x onerror=evil()>',
                'selected_options': {'color': 'Black'}, 'sale_unit': '1 object',
                'components': [], 'required_disclosure': 'Synthetic lab design.'}}


class MediaPilotReviewTest(unittest.TestCase):
    def test_verdict_is_derived_with_fail_then_uncertainty_precedence(self):
        row = observation(); row['verdict'] = 'fail'
        self.assertEqual(classify(row), 'pass')
        row['checks'][CHECKS[0]] = 'uncertain'
        self.assertEqual(classify(row), 'uncertain')
        row['checks'][CHECKS[1]] = 'fail'; row['verdict'] = 'pass'
        self.assertEqual(classify(row), 'fail')

    def test_pending_missing_unknown_checks_or_empty_evidence_cannot_pass(self):
        rows = []
        pending = observation(); pending['checks'][CHECKS[0]] = 'pending'; rows.append(pending)
        missing = observation(); del missing['checks'][CHECKS[0]]; rows.append(missing)
        extra = observation(); extra['checks']['invented'] = 'pass'; rows.append(extra)
        empty = observation(); empty['finding'] = ' '; rows.append(empty)
        for row in rows:
            with self.assertRaises(ValueError): classify(row)

    def test_every_binding_must_match_the_exact_candidate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); path = root / 'candidate.webp'; path.write_bytes(b'candidate')
            good = observation(); good['image_sha256'] = sha256(path)
            self.assertEqual(bind_observations([case()], [good], root)[0]['verdict'], 'pass')
            for key in ('image_sha256', 'definition_sha256', 'runtime_prompt_sha256'):
                bad = copy.deepcopy(good); bad[key] = 'e' * 64
                with self.assertRaisesRegex(ValueError, 'Stale'):
                    bind_observations([case()], [bad], root)

    def test_scope_must_be_complete_and_unique(self):
        for rows in ([], [observation(), observation()], [{**observation(), 'root_sku': 'unknown'}]):
            with self.assertRaises(ValueError):
                bind_observations([case()], rows, Path('/tmp'))

    def test_observation_cannot_grant_approval_or_override_a_failed_screen(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); path = root / 'candidate.webp'; path.write_bytes(b'candidate')
            row = observation(); row.update(image_sha256=sha256(path), publication_approved=True,
                                           reference_use_approved=True, bulk_generation_approved=True, verdict='pass')
            row['checks'][CHECKS[0]] = 'fail'
            bound = bind_observations([case()], [row], root)[0]
            self.assertEqual(bound['verdict'], 'fail')
            for key in ('publication_approved', 'reference_use_approved', 'bulk_generation_approved'):
                self.assertIs(bound[key], False)

    def test_html_escapes_catalog_text_and_renders_two_images_and_bounded_claims(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); path = root / 'candidate.webp'; path.write_bytes(b'candidate')
            row = observation(); row['image_sha256'] = sha256(path)
            rows = bind_observations([case()], [row], root)
            html = render(rows, {'reviewed': 1, 'pass': 1, 'fail': 0, 'uncertain': 0})
            self.assertEqual(html.count('<img '), 2)
            self.assertIn('&lt;script&gt;', html)
            self.assertNotIn('<script>', html)
            self.assertNotIn('<img src=x', html)
            self.assertIn('not a catalog-wide quality estimate', html)
            self.assertIn('144 to 144 tokens', html)

    def test_build_pins_observations_and_never_overwrites_a_review(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); run_dir = root / 'run'; run_dir.mkdir()
            image = run_dir / 'candidate.webp'; image.write_bytes(b'candidate')
            row = observation(); row['image_sha256'] = sha256(image)
            notes = root / 'notes.json'; notes.write_text(json.dumps([row]))
            output = root / 'review'
            with patch('review_catalog_media_pilot.verify_run', return_value=([case()], {str(image): sha256(image)})):
                self.assertEqual(build(root / 'plan', run_dir, notes, output)['pass'], 1)
                before = (output / 'manifest.json').read_bytes()
                with self.assertRaisesRegex(ValueError, 'fresh'):
                    build(root / 'plan', run_dir, notes, output)
                self.assertEqual((output / 'manifest.json').read_bytes(), before)
            manifest = json.loads(before)
            self.assertEqual(manifest['inputs'][str(notes.resolve())], sha256(notes))
            self.assertFalse(manifest['deployment_ready'])
            self.assertEqual(set(manifest['outputs']), {'review.html', 'reviews.jsonl'})

    def test_cli_error_is_quiet_and_produces_no_review(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); output = root / 'review'
            command = [sys.executable, str(Path(__file__).resolve().parents[1] / 'review_catalog_media_pilot.py'),
                       '--plan', str(root / 'absent'), '--run-dir', str(root / 'absent-run'),
                       '--observations', str(root / 'absent.json'), '--output-dir', str(output)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout + result.stderr, '')
            self.assertFalse(output.exists())
            self.assertIn('no images or approvals changed', output.with_suffix('.log').read_text())


if __name__ == '__main__':
    unittest.main()
