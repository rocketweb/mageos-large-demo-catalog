"""Separate outline checks for glass/transparent catalog derivatives.

Interior print/texture edges must not conceal a missing transparent outline.
This stage only vetoes existing approvals; it does not grant new approvals.
"""
from functools import lru_cache
import hashlib
import inspect
import json

PARAMETERS = {'source_edge': 12, 'candidate_edge': 6, 'match_window': 7,
              'outline_band': 8, 'min_outline_pixels': 64,
              'retention_min': .9, 'missing_component_max': 1024,
              'missing_span_fraction_max': .5}


def features(original, candidate):
    import numpy as np
    from scipy.ndimage import maximum_filter, label, find_objects
    from white_jpeg_audit import edge_strength
    if original.size != candidate.size:
        raise ValueError('Glass pair dimensions differ')
    source = edge_strength(np.asarray(original, dtype=np.float32))
    target = edge_strength(np.asarray(candidate, dtype=np.float32))
    edge = source >= PARAMETERS['source_edge']
    band = PARAMETERS['outline_band']
    edge[:band] = False; edge[-band:] = False
    edge[:, :band] = False; edge[:, -band:] = False
    outline = np.zeros_like(edge)
    for y in range(edge.shape[0]):
        xs = np.flatnonzero(edge[y])
        if len(xs):
            outline[y, xs[0]:xs[0]+band] = edge[y, xs[0]:xs[0]+band]
            outline[y, max(0, xs[-1]-band+1):xs[-1]+1] = edge[y, max(0, xs[-1]-band+1):xs[-1]+1]
    for x in range(edge.shape[1]):
        ys = np.flatnonzero(edge[:, x])
        if len(ys):
            outline[ys[0]:ys[0]+band, x] = edge[ys[0]:ys[0]+band, x]
            outline[max(0, ys[-1]-band+1):ys[-1]+1, x] = edge[max(0, ys[-1]-band+1):ys[-1]+1, x]
    missing = outline & (maximum_filter(target, size=PARAMETERS['match_window']) < PARAMETERS['candidate_edge'])
    cc, n = label(missing, np.ones((3, 3)))
    sizes = np.bincount(cc.ravel()); sizes[0] = 0
    regions = []
    for index, box in enumerate(find_objects(cc), 1):
        if box is None: continue
        y, x = box
        regions.append({'pixels': int(sizes[index]), 'box': [x.start+1, y.start+1, x.stop+1, y.stop+1],
                        'span_fraction': max((x.stop-x.start)/original.width, (y.stop-y.start)/original.height)})
    total = int(outline.sum())
    return {'dimensions': list(original.size), 'outline_pixels': total,
            'outline_retention': float(1-missing.sum()/total) if total else 0,
            'missing_pixels': int(missing.sum()), 'regions': sorted(regions, key=lambda r: -r['pixels'])}


def choose(measurements):
    if measurements['outline_pixels'] < PARAMETERS['min_outline_pixels']:
        return 'review', 'too_little_visible_outline_to_verify'
    if measurements['outline_retention'] < PARAMETERS['retention_min']:
        return 'review', 'missing_original_outline_pixels'
    for region in measurements['regions']:
        if (region['pixels'] > PARAMETERS['missing_component_max'] or
                region['span_fraction'] > PARAMETERS['missing_span_fraction_max']):
            return 'review', 'connected_or_extended_outline_loss'
    return 'preserved', 'native_outline_edges_preserved'


def protect(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS glass_outline_checks(
        file TEXT PRIMARY KEY,source_sha256 TEXT,output_sha256 TEXT,identity TEXT,
        measurements TEXT,verdict TEXT,reason TEXT,review TEXT,details TEXT,updated_at REAL);
        CREATE TABLE IF NOT EXISTS glass_prior_selection(file TEXT PRIMARY KEY,reason TEXT);
        CREATE TRIGGER IF NOT EXISTS preserve_glass_outline_hold
        AFTER UPDATE OF decision ON images
        WHEN NEW.decision='white' AND EXISTS(SELECT 1 FROM glass_outline_checks g
            WHERE g.file=NEW.file AND g.verdict!='preserved')
        BEGIN
            INSERT OR IGNORE INTO glass_prior_selection(file,reason) VALUES(NEW.file,NEW.reason);
            UPDATE images SET decision='original',reason='glass_outline_missing_or_uncertain_keep_original'
                WHERE file=NEW.file;
        END;''')


@lru_cache(maxsize=1)
def identity():
    return hashlib.sha256(json.dumps({'parameters': PARAMETERS,
        'implementation': inspect.getsource(features)+inspect.getsource(choose)}, sort_keys=True).encode()).hexdigest()
