"""Fast approvals for uniform dark products, including new interior-hole checks."""
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np
from PIL import Image
from scipy.ndimage import binary_closing, binary_erosion, binary_fill_holes, label
import white_jpeg_category_policy as policy

PARAMETERS = {'size': 192, 'foreground_delta': 35, 'dark_max': 160, 'pale_min': 210,
    'dominant_fraction': .90, 'dark_fraction': .80, 'pale_fraction': .005, 'luma_p90': 180,
    'erased_dark_fraction': .15, 'new_enclosed_erasure_fraction': .005,
    'native_edge_retention': .90, 'retained_pixel_agreement': .92}


def identity():
    return hashlib.sha256(json.dumps({'version': 1, 'parameters': PARAMETERS,
        'implementation': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}, sort_keys=True).encode()).hexdigest()


def gate(row, metrics, meta, glass_scoped=False):
    text = ' '.join(meta.get('classes', []) + [meta.get('name', '')]).lower()
    if glass_scoped or re.search(r'glass|mirror|transparent|acrylic|crystal', text):
        return False
    if policy.room_bundle(meta) or not meta.get('classes') or any(c in ('Bedding Sets', 'Unknown', 'Uncategorized') for c in meta['classes']):
        return False
    if not row.get('output_file') or row.get('warning') or metrics is None or metrics.get('candidate_error'):
        return False
    for key in ('backdrop_fit_p90', 'border_edge_fraction', 'white_border', 'native_edge_retention', 'retained_pixel_agreement'):
        if type(metrics.get(key)) not in (int, float) or not math.isfinite(metrics[key]):
            raise ValueError('Invalid native dark-product evidence')
    return (metrics['backdrop_fit_p90'] <= 16 and metrics['border_edge_fraction'] <= .04 and
            metrics['white_border'] >= .98 and metrics['native_edge_retention'] >= PARAMETERS['native_edge_retention'] and
            metrics['retained_pixel_agreement'] >= PARAMETERS['retained_pixel_agreement'])


def features(original, candidate, native_metrics):
    if original.size != candidate.size:
        raise ValueError('Dark-product image dimensions changed')
    size = PARAMETERS['size']
    a, b = [np.asarray(image.resize((size, size), Image.Resampling.LANCZOS), dtype=np.float32) for image in (original, candidate)]
    bg = np.asarray(native_metrics['border_median_rgb'])
    foreground = np.max(abs(a-bg), axis=2) > PARAMETERS['foreground_delta']
    components, n = label(binary_closing(foreground, structure=np.ones((3, 3))), np.ones((3, 3)))
    sizes = np.bincount(components.ravel());sizes[0] = 0
    if not n or sizes.max() < .01 * foreground.size:
        return {'measurable': False}
    envelope = binary_fill_holes(components == sizes.argmax())
    core = binary_erosion(envelope, iterations=2)
    if core.sum() < .005 * foreground.size:
        return {'measurable': False}
    dark = (np.max(a, axis=2) < PARAMETERS['dark_max']) & envelope
    white = np.min(b, axis=2) > 245
    white_labels, _ = label(white, np.ones((3, 3)))
    exterior = np.unique(np.concatenate([white_labels[0], white_labels[-1], white_labels[:, 0], white_labels[:, -1]]))
    enclosed = white & ~np.isin(white_labels, exterior)
    return {'measurable': True, 'dominant_fraction': float(sizes.max()/max(sizes.sum(), 1)),
        'dark_fraction': float(dark.sum()/envelope.sum()),
        'pale_fraction': float(np.mean(np.min(a, axis=2)[core] > PARAMETERS['pale_min'])),
        'luma_p90': float(np.quantile(np.mean(a, axis=2)[core], .90)),
        'erased_dark_fraction': float(np.sum(dark & (np.min(b, axis=2) > 225))/max(dark.sum(), 1)),
        'new_enclosed_erasure_fraction': float(np.sum(dark & enclosed)/max(dark.sum(), 1))}


def passes(values):
    if not values.get('measurable'):
        return False
    for key in ('dominant_fraction', 'dark_fraction', 'pale_fraction', 'luma_p90', 'erased_dark_fraction', 'new_enclosed_erasure_fraction'):
        if type(values.get(key)) not in (int, float) or not math.isfinite(values[key]):
            raise ValueError('Invalid dark-product measurement')
    return (values['dominant_fraction'] >= PARAMETERS['dominant_fraction'] and values['dark_fraction'] >= PARAMETERS['dark_fraction'] and
        values['pale_fraction'] <= PARAMETERS['pale_fraction'] and values['luma_p90'] <= PARAMETERS['luma_p90'] and
        values['erased_dark_fraction'] <= PARAMETERS['erased_dark_fraction'] and
        values['new_enclosed_erasure_fraction'] <= PARAMETERS['new_enclosed_erasure_fraction'])
