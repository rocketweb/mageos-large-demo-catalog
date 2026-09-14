"""Prepare reference-bound gallery views for a visually inspected synthetic subset."""
import argparse
import hashlib
import json
import logging
from pathlib import Path

from prepare_catalog import sha256

# These references were viewed directly on September 12, 2026. Two mislabeled
# papasan-chair images were excluded, not silently approved for propagation.
SUBJECTS = {
    'WANDS-000639': 'one white table lamp with a slim curved base and tapered shade',
    'WANDS-000710': 'one white table lamp with a flared round base and tapered shade',
    'WANDS-000711': 'one white table lamp with a conical base and cylindrical shade',
    'WANDS-000082': 'one round aqua and cream braided rug',
    'WANDS-000083': 'one octagonal beige braided rug',
    'WANDS-000084': 'one square black braided rug',
    'WANDS-000304': 'one brown upholstered armchair with a wood frame and wood armrests',
}
VIEWS = {
    'angle': 'A slightly higher three-quarter studio view, the complete product visible against a warm off-white background.',
    'detail': 'A close-up of the visible surface texture and an adjacent edge; do not invent hidden construction.',
    'room': 'A calm residential room context with the referenced product as the clear subject. Supporting furnishings are background styling, not included products.',
}
APPROVED_HASHES = {
    'WANDS-000639': 'c25f6fe00b918f9aa3056105b1a7cf71428c8cd205d5356ac3187a34dc4d7038',
    'WANDS-000710': 'c34e4e6cdd88f3fb53cdf55f57f2c7b78aa2eae795ed0669accc73e5a6d4088c',
    'WANDS-000711': 'df05fd362d85760ad81c8ccbb6e832e223213e003a3d0e5201c9d4b20180958e',
    'WANDS-000082': '1deac89708d595f20b105ded32a943d028f58c9e210abad2c60829c8c6e49ec5',
    'WANDS-000083': 'f3e0ad9538100ff32a0c613abb04913a442f0e2afe7bd9c82cecaefb19b7afb8',
    'WANDS-000084': '942ef202e2b439dce864f653fa57d4870807743c39b7e9346e90af9cc93c71ee',
    'WANDS-000304': 'bbc540c32d81030c844220940a98eaa8a1c366b802900c101e70762400c8c354',
}


def build(media, output):
    if output.exists():
        raise ValueError('Choose a new queue directory')
    jobs, audits = [], []
    for sku, subject in SUBJECTS.items():
        path = (media / (sku + '.jpg')).resolve()
        digest = sha256(path)
        if digest != APPROVED_HASHES[sku]:
            raise ValueError('Reference differs from the visually inspected image: '+sku)
        audits.append({'path': str(path), 'image_sha256': digest, 'approved': True,
                       'scope': 'synthetic gallery reference identity, not manufacturer accuracy',
                       'observation': subject, 'method': 'direct assistant visual inspection, 2026-09-12'})
        for view, instruction in VIEWS.items():
            prompt = ('Use case: product-mockup. Image 1 is the identity reference. Show ' + subject + '. '
                      + instruction + ' Preserve the exact silhouette, colors, visible materials and piece count from Image 1. '
                      'Photorealistic product illustration, soft natural lighting. No people, logos, text, dimensions or watermarks. '
                      'Do not redesign the product or imply verified scale or fit.')
            signature = hashlib.sha256((digest + prompt).encode()).hexdigest()
            jobs.append({'sku': sku, 'view': view, 'output_file': sku+'-gallery-'+view+'-'+signature[:10]+'.jpg',
                         'seed': int(signature[:8], 16), 'prompt': prompt,
                         'reference_images': [{'path': str(path), 'sha256': digest}],
                         'disclosure': 'Synthetic illustration; room styling is not included in the sale unit.'})
    output.mkdir(parents=True)
    for name, rows in [('jobs.jsonl', jobs), ('reference-audit.jsonl', audits)]:
        (output / name).write_text(''.join(json.dumps(row, sort_keys=True)+'\n' for row in rows))
    (output / 'manifest.json').write_text(json.dumps({'jobs': len(jobs), 'products': len(audits),
        'outputs': {name: sha256(output/name) for name in ['jobs.jsonl','reference-audit.jsonl']},
        'images_installed': 0}, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--media', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.output.with_suffix('.log'), level=logging.INFO)
    try:
        build(args.media, args.output)
        logging.info('Prepared 21 reference-bound gallery jobs')
    except Exception:
        logging.exception('Queue preparation failed')
        raise SystemExit(1)
