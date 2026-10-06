"""Magento varchar normalization after every variant substitution."""
from build_expanded_catalog import digest

def normalize(rows):
    changes=[]
    for sku,row in sorted(rows.items()):
        for field in ('name','meta_title','meta_description'):
            value=row.get(field,'')
            if len(value)>255:
                row[field]=value[:255]
                changes.append({'sku':sku,'field':field,'before_sha256':digest(value),'after_sha256':digest(row[field]),'characters_removed':len(value)-255})
    return changes

def media_label(name):
    suffix=' (synthetic illustration; no displayed measurements)'
    return name[:255-len(suffix)]+suffix
