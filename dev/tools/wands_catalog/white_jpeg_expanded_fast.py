"""Additional fast approvals under the user's major-damage-only tolerance.

The first fast protocol remains intact. This second protocol can clear its
small changed-region flags, but never its background, category, diffuse-loss,
or invalid-candidate flags. Evidence names both protocols independently.
"""
import hashlib
import inspect
import json
import math
from functools import lru_cache

import white_jpeg_category_policy as base

VERSION = 'expanded-fast-major-damage-v1'
POLICY = {
    'enclosed_component_image_fraction': .01,
    'enclosed_component_visible_fraction': .05,
    'enclosed_total_image_fraction': .02,
    'enclosed_total_visible_fraction': .08,
    'dark_component_image_fraction': .012,
    'dark_component_visible_fraction': .05,
    'dark_total_image_fraction': .02,
    'dark_total_visible_fraction': .08,
    'new_edge_component_image_fraction': .003,
    'missing_edge_component_image_fraction': .01,
    'source_chroma_loss_fraction_max': .05,
    'envelope_foreground_loss_fraction_max': .15,
}
MEASURE = {'size': 256, 'foreground_delta': 35, 'chroma_delta': 25,
           'candidate_white': 247, 'candidate_foreground': 240, 'denominator_floor_fraction': .02}
REGION_FLAGS = {
    'changed_region_risk_enclosed_whitened_area',
    'changed_region_risk_erased_dark_area',
    'changed_region_risk_new_cutout_edge',
    'changed_region_risk_missing_source_edge',
    'multiple_enclosed_product_change_risks',
}


def route(row, metrics, meta, supplemental=None):
    decision, reason = base.route(row, metrics, meta)
    if decision != 'review' or reason not in REGION_FLAGS:
        return decision, reason
    area = math.prod(metrics['dimensions'])
    visible = metrics['visible_fraction'] * area
    sizes = {}
    for region in metrics['risk_regions']:
        value = region['pixels']
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError('Invalid changed-region measurement')
        sizes.setdefault(region['kind'], []).append(value)
    if set(sizes) - {'enclosed_whitened_area', 'erased_dark_area', 'new_cutout_edge', 'missing_source_edge'}:
        return 'review', 'unrecognized_changed_region'
    for kind, prefix in [('enclosed_whitened_area', 'enclosed'), ('erased_dark_area', 'dark')]:
        values = sizes.get(kind, [0])
        component = min(POLICY[prefix + '_component_image_fraction'] * area,
                        POLICY[prefix + '_component_visible_fraction'] * visible)
        total = min(POLICY[prefix + '_total_image_fraction'] * area,
                    POLICY[prefix + '_total_visible_fraction'] * visible)
        if max(values) > component or sum(values) > total:
            return 'review', 'likely_major_surface_loss_' + kind
    for kind, key in [('new_cutout_edge', 'new_edge_component_image_fraction'),
                      ('missing_source_edge', 'missing_edge_component_image_fraction')]:
        if max(sizes.get(kind, [0])) > POLICY[key] * area:
            return 'review', 'likely_major_structure_loss_' + kind
    if supplemental is None:
        return 'measure', 'awaiting_expanded_source_material_checks'
    for key in ['source_chroma_loss_fraction', 'envelope_foreground_loss_fraction']:
        value = supplemental.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('Invalid source-material measurement: ' + key)
        if value > POLICY[key + '_max']:
            return 'review', 'likely_major_material_loss_' + key
    return 'white', 'expanded_fast_checks_passed_minor_region_changes_accepted'


def features(original, candidate):
    import numpy as np
    from PIL import Image
    if original.size != candidate.size:
        raise ValueError('Image dimensions changed')
    size = MEASURE['size']
    a = np.asarray(original.resize((size, size), Image.Resampling.BICUBIC), dtype=np.float32)
    c = np.asarray(candidate.resize((size, size), Image.Resampling.BICUBIC), dtype=np.float32)
    y, x = np.mgrid[-1:1:complex(size), -1:1:complex(size)]
    ring = (abs(x) > .94) | (abs(y) > .94)
    design = np.stack([np.ones_like(x), x, y, x*y, x*x, y*y], axis=2)
    X, Y = design[ring], a[ring]
    keep = np.ones(len(X), dtype=bool)
    for _ in range(4):
        coef = np.linalg.lstsq(X[keep], Y[keep], rcond=None)[0]
        residual = np.max(abs(Y-X@coef), axis=1)
        keep = residual <= max(8, float(np.quantile(residual, .8)))
    backdrop = design@coef
    foreground = np.max(abs(a-backdrop), axis=2) > MEASURE['foreground_delta']
    white = np.min(c, axis=2) >= MEASURE['candidate_white']
    source_chroma = a-a.mean(axis=2, keepdims=True)
    backdrop_chroma = backdrop-backdrop.mean(axis=2, keepdims=True)
    colored = np.max(abs(source_chroma-backdrop_chroma), axis=2) > MEASURE['chroma_delta']
    minimum = MEASURE['denominator_floor_fraction']*size*size
    color_loss = float(np.sum(colored & white)/max(colored.sum(), minimum))
    mask = np.min(c, axis=2) < MEASURE['candidate_foreground']
    envelope = np.zeros_like(mask)
    for y in range(size):
        xs = np.flatnonzero(mask[y])
        if len(xs):
            envelope[y, xs[0]:xs[-1]+1] = True
    inner_loss = float(np.sum(foreground & white & envelope)/max(np.sum(foreground & envelope), minimum))
    return {'source_chroma_loss_fraction': color_loss, 'envelope_foreground_loss_fraction': inner_loss}


@lru_cache(maxsize=1)
def measurement_identity():
    return hashlib.sha256(json.dumps({'parameters': MEASURE, 'implementation': inspect.getsource(features)},
                                    sort_keys=True).encode()).hexdigest()


@lru_cache(maxsize=1)
def identity():
    value = {'version': VERSION, 'base_policy': base.identity(), 'policy': POLICY,
             'measurement_identity': measurement_identity(),
             'region_flags': sorted(REGION_FLAGS), 'implementation': inspect.getsource(route)}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
