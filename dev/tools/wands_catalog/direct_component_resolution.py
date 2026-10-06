"""Exact-photo direct correction of a false scalar component count only."""
import copy
from build_expanded_catalog import digest
from human_keep_acceptance import annotation_clear

VERSION='direct-component-resolution-v1'

def valid(review, design, expected):
    import component_review
    proof=review.get('direct_component_resolution') or {}
    if not isinstance(proof,dict):return False
    original=proof.get('original_review') or {}
    if not isinstance(original,dict):return False
    if (not expected or proof.get('version')!=VERSION
            or proof.get('reviewer')!='direct_visual_inspection'
            or digest(proof)!=review.get('direct_component_resolution_sha256')
            or proof.get('image_sha256')!=review.get('image_sha256')
            or proof.get('design_sha256')!=review.get('design_sha256') or digest(design)!=review.get('design_sha256')
            or proof.get('review_identity')!=review.get('review_identity')
            or not isinstance(proof.get('observations'),str) or not proof['observations'].strip()
            or not original.get('vision',{}).get('acceptable') or not annotation_clear(original)
            or any(original.get('vision',{}).get(k) is not False for k in ('geometry_defects','visible_text','visible_measurements'))
            or any(original.get('vision',{}).get(k) is not True for k in ('product_matches','piece_count_matches'))):return False
    if original.get('direct_visual_failure') or original.get('geometry_hold'):return False
    if proof.get('counting_scope')!=component_review.count_scope(design):return False
    unchanged={k:v for k,v in review.items() if k not in {'decision','direct_component_resolution','direct_component_resolution_sha256'}}
    if unchanged!={k:v for k,v in original.items() if k!='decision'}:return False
    observed=proof.get('observed')
    if not isinstance(observed,dict) or set(observed)!=set(expected):return False
    if any(type(observed[k]) is not int or observed[k]!=v for k,v in expected.items()):return False
    if 'drawer_fronts' in expected:
        rows=proof.get('drawer_fronts_by_row')
        if (not isinstance(rows,list) or not rows or any(type(n) is not int or not 1<=n<=100 for n in rows)
                or sum(rows)!=expected['drawer_fronts']):return False
    return True

def resolve(review, design, observed, observations, drawer_fronts_by_row=None):
    import component_review
    original=copy.deepcopy(review)
    if original.get('direct_component_resolution'):raise ValueError('Count already resolved')
    proof={'version':VERSION,'reviewer':'direct_visual_inspection','image_sha256':review['image_sha256'],
           'design_sha256':review['design_sha256'],'review_identity':review['review_identity'],
           'observed':observed,'counting_scope':component_review.count_scope(design),'drawer_fronts_by_row':drawer_fronts_by_row,
           'observations':observations,'original_review':original}
    result={**review,'decision':'accepted','direct_component_resolution':proof,'direct_component_resolution_sha256':digest(proof)}
    if not valid(result,design,component_review.required_counts(design)):raise ValueError('Direct count resolution must match the exact brief and clear general and annotation QA')
    return result
