"""Native-photo correction of standalone riser identity/material false negatives.

Never overrides annotation, geometry, piece-count, paired-source or category failures.
The application layer must also refuse current human Keeps and manual image holds.
"""
import copy
from build_expanded_catalog import digest
from human_keep_acceptance import annotation_clear
VERSION='native-standalone-riser-v1'

def valid(review,job,expected_identity):
 from category_image_corrections import identity,BOOLS
 import component_review
 p=review.get('direct_riser_acceptance');d=job.get('design',{})
 if not isinstance(p,dict):return False
 original=p.get('original_review');category=p.get('category_review')
 if not isinstance(original,dict) or not isinstance(category,dict):return False
 vision=original.get('vision',{});result=category.get('result',{})
 if (p.get('version')!=VERSION or p.get('reviewer')!='direct_visual_inspection'
     or digest(p)!=review.get('direct_riser_acceptance_sha256')
     or job.get('reference') is not None or job.get('profile')!='monitor-riser' or d.get('profile')!='monitor-riser'
     or job.get('design_sha256')!=digest(d) or review.get('design_sha256')!=digest(d)
     or p.get('image_sha256')!=review.get('image_sha256') or p.get('design_sha256')!=digest(d)
     or p.get('review_identity')!=review.get('review_identity') or review.get('review_identity')!=expected_identity
     or any(original.get(k) for k in ('human_keep','direct_visual_failure','geometry_hold','direct_component_resolution'))
     or not annotation_clear(original) or vision.get('geometry_defects') is not False or vision.get('piece_count_matches') is not True
     or not component_review.accepted(original,d)
     or category.get('identity')!=identity(review.get('model'))
     or category.get('image_sha256')!=review.get('image_sha256') or category.get('design_sha256')!=digest(d)
     or result.get('acceptable') is not True or result.get('verdict')!='pass' or result.get('confidence',0)<.95
     or result.get('issues')!=[] or any(result.get(k) is not True for k in BOOLS)):return False
 unchanged={k:v for k,v in review.items() if k not in {'decision','direct_riser_acceptance','direct_riser_acceptance_sha256'}}
 if unchanged!={k:v for k,v in original.items() if k!='decision'}:return False
 note=p.get('observations');note=note.lower() if isinstance(note,str) else ''
 if not all(s in note for s in ('separate riser','horizontal load surface','no annotations')):return False
 if 'side cubby' in d.get('construction','') and not all(s in note for s in ('accessible side cubby','open center')):return False
 return review.get('decision')=='accepted'

def resolve(review,job,category,observations):
 p={'version':VERSION,'reviewer':'direct_visual_inspection','image_sha256':review['image_sha256'],
    'design_sha256':review['design_sha256'],'review_identity':review['review_identity'],
    'original_review':copy.deepcopy(review),'category_review':copy.deepcopy(category),'observations':observations}
 result={**review,'decision':'accepted','direct_riser_acceptance':p,'direct_riser_acceptance_sha256':digest(p)}
 if not valid(result,job,review['review_identity']):raise ValueError('Riser correction requires exact native geometry, clear annotations and accepted category QA; no paired-source or other defect overrides')
 return result
