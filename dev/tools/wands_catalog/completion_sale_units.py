"""Render-only geometry for diagnosed, repeatedly confused sale items.

Frozen catalog briefs and the independent product/count/text reviews are intact.
These instructions describe what to draw rather than repeating a wrong object
from the previous model's rejection paragraph.
"""
import re


WORDS=('zero','one','two','three','four','five','six','seven','eight','nine','ten','eleven','twelve')


def pieces(subject):
    match=re.search(r'\b(1[0-2]|[1-9])\s*[- ]?\s*(?:pieces?|pcs?)\b|\bpack\s+of\s+(1[0-2]|[1-9])\b',subject,re.I)
    return int(match[1] or match[2]) if match else None


def geometry(design):
    subject=design.get('subject','').lower()
    category=design.get('product_class',design.get('profile','')).lower()
    count=pieces(subject)
    if 'pillowcase' in subject or 'pillow cover' in subject:
        n=count or 1
        return ('Show exactly '+WORDS[n]+' separate fabric pillowcases, each with a visible open end and sewn edges. '
                'Arrange the complete textile sale items side by side, retaining the specified embroidery or printed motif. '
                'Only the pillowcases are present, with no bed, bed frame, duvet or furniture. ')
    if 'furniture cushions' in category:
        return ('Show the standalone padded fabric seat cushion as the sale item, with its coherent sewn cover, '
                'visible thickness, and any specified ties or back cushion. The cushion is separate from furniture; '
                'no chair frame, legs, bench or sofa is included. ')
    if 'life size cutout' in category:
        return ('One flat printed cardboard silhouette of the specified character or scene, held upright by a small rear folding support. '
                'A slightly angled view reveals the thin cardboard edge and flat printed surface. '
                'The character appears in the printed artwork, never as a sculpted statue or action figure. ')
    if 'strip' in subject and ('lighting' in category or 'led' in subject):
        text=('One long narrow flexible ribbon of connected LED segments on a thin circuit strip, partly coiled '
              'with a long straight end extending visibly. Small repeated emitting diodes are mounted along the ribbon. ')
        if 'remote' in subject:text+='Include the specified plain unmarked remote with blank buttons, separate from the ribbon. '
        return text+'All control boxes and circuit surfaces are entirely plain and unmarked. '
    if 'over-the-toilet' in subject or 'over the toilet' in subject:
        return ('One tall freestanding bathroom storage unit: two tall side supports with a large open lower gap '
                'and connected storage shelves or the specified cabinet above the gap. '
                'The lower opening is wide enough to straddle a toilet, but show only the complete storage furniture. ')
    if 'bread knife' in subject:
        return ('One complete bread knife with an elongated serrated stainless steel blade connected to its handle. '
                'The entire cutting edge has clearly visible repeating teeth. Show the complete utensil alone. ')
    if 'widespread' in subject and 'faucet' in subject:
        text=('One widespread bathroom faucet assembly with one central spout and two separate side handles, '
              'each handle on its own small mounting base. Arrange all three matching fittings together. ')
        if 'drain' in subject:text+='Include the specified separate drain assembly beside the faucet fittings. '
        return text+'Plain unmarked metal surfaces; no sink bowl or kitchen appliance. '
    if 'washer and dryer sets' in category:
        return ('Show exactly two complete separate appliance bodies side by side: one washing machine and one clothes dryer. '
                'Each has its own complete housing, door or lid and plain unmarked controls. '
                'Retain the specified loading style for each appliance. No extra appliance. ')
    if 'washing machines' in category or ('uncategorized' in category and 'washer' in subject):
        if 'top load' in subject or 'top-load' in subject:
            body='One complete top-loading washing machine with a hinged lid on the horizontal top and a deep enclosed tub beneath it. '
        elif 'front load' in subject or 'front-load' in subject:
            body='One complete front-loading washing machine with a large circular front door in a coherent rectangular housing. '
        else:body='One complete washing machine with the specified door or lid and coherent appliance housing. '
        return body+'Use plain unmarked controls and a blank dark display. Every surface is free of branding or lettering. '
    if count and 'wall art' in category:
        return ('Show exactly '+WORDS[count]+' separate canvas panels with clear gaps between every panel. '
                'The specified scene is printed across the panels as one continuous composition. '
                'All complete panel edges are visible; no single canvas replaces the separate pieces. ')
    if count and 'table set' in subject and ('living room' in category or 'uncategorized' in category):
        return ('Show exactly '+WORDS[count]+' complete separate tables with clear gaps between them. '
                'Every table has its own tabletop and complete supports. Keep the specified coffee/end/nesting table '
                'style and matching finish. Arrange all tables so their tops and bases are visible. No chairs or sofa. ')
    if count and 'bath accessories' in category:
        items=('soap dispenser','tumbler','toothbrush holder','soap dish','tray','lidded jar')
        specified=' '.join(' '.join(re.findall(r'[a-z]+',word)) for word in (design.get('construction','').lower(),subject))
        listed=[name for name in items if name in specified]
        # A generic collection name has no specified component identities. Use
        # exactly the requested number of ordinary accessories, not six options
        # that the renderer can misread as six required objects.
        types=', '.join(listed) if listed else ', '.join(items[:count]) if count<=len(items) else ''
        return ('Show exactly '+WORDS[count]+' separate complete matching bathroom accessory items. '
                +('The matching accessories are: '+types+'. ' if types else '')+
                'Each complete item counts once, '
                'with attached lids and pumps as parts of that same item. Plain unmarked surfaces. ')
    if 'wall plate' in category and 'toggle' in subject:
        match=re.search(r'\b([1-6])\s*[- ]\s*gang\b',subject)
        n=int(match[1]) if match else 1
        return ('One flat electrical cover plate with exactly '+WORDS[n]+' narrow rectangular toggle-switch openings '
                'side by side and small mounting screw holes. Keep the specified decorative motif on the plate surface. '
                'The openings are empty and distinct from the decorative printed artwork. ')
    return ''


def wrong_object_diagnostic(text):
    """Drop rejected-object descriptions only when a positive sale-unit recipe exists."""
    return bool(re.search(r'\b(?:image|illustration|candidate|product)\s+(?:shows?|depicts?|displays?|is\s+(?:an?|a))\b',text,re.I))
