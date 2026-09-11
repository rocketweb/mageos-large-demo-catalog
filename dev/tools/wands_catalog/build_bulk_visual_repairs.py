#!/usr/bin/env python3
"""One bounded repair pass for recurring visual errors in the bulk contact sheet."""
import argparse
import hashlib
import json
from pathlib import Path
from catalog_repairs import read_jsonl


def repair_prompt(job):
    c = job['contract']
    name = c['product_name'].lower()
    options = ', '.join(str(v) for k,v in c['selected_options'].items() if k not in {'wands_piece_count','wands_size'})
    start = 'High quality photorealistic unbranded product photograph on white seamless background. '
    end = ' Soft studio lighting, complete objects visible, no text, no logos, no people, no extra props.'
    if c['root_sku'] == 'WANDS-022642':
        return start+'Exactly two empty kitchen appliances side by side: LEFT a round metal hamburger patty mold with a solid pressing lid and black handle; RIGHT a rectangular manual potato cutter with a metal square blade grid and hinged lever handle. Both are tools made of metal and plastic, completely empty. Absolutely no food, hamburgers, buns or potatoes.'+end
    if 'nursery' in name:
        aliases = {'Crib skirt':'flat rectangular bed dust ruffle unfolded as a cross, one large rectangular center with four rectangular fabric flaps, no waistband',
                   'Fitted crib sheet':'rectangular elastic-corner mattress fabric cover lying flat',
                   'Nursery quilt':'flat rectangular stitched patchwork blanket',
                   'Window valance':'long narrow rectangular fabric curtain topper lying flat'}
        parts = [str(p['quantity'])+' '+aliases.get(p['label'],p['label']) for p in c['components']]
        return start+'Overhead flat lay of home bedding textiles, '+options+'. Exactly these separated objects: '+ '; '.join(parts)+'. All fabric is unfolded and flat with rectangular edges. These are household linens, not clothing. No skirts worn by people, no pants, no shorts, no gathered waistbands, no garments, no crib, no bed.'+end
    if 'body pillowcase' in name:
        return start+'One very long narrow rectangular body pillow cover, '+options+', displayed horizontally, length nearly three times its height. A long slim rectangle with straight stitched seams, not a square cushion. No lettering.'+end
    if 'one-drawer' in name:
        return start+'A compact '+options+' bedside nightstand with exactly ONE drawer. One single drawer front with one centered handle. Below the single drawer is a large completely open empty shelf, clearly visible. Four legs. No second drawer, no third drawer, no cabinet door.'+end
    if 'three-level bunk' in name:
        return start+'One natural wood triple bunk bed frame with EXACTLY THREE vertically stacked sleeping platforms: bottom platform close to floor, middle platform halfway up, top platform at the top. Three distinct horizontal slatted platforms all clearly visible. '+str(c['selected_options'].get('wands_size',''))+'. Frame only, no mattresses, no bedding.'+end
    return None


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    rows=[]
    for job in read_jsonl(args.packet/'image-jobs.jsonl'):
        prompt=repair_prompt(job)
        if prompt:
            digest=hashlib.sha256(prompt.encode()).hexdigest()
            rows.append({'sku':job['sku'],'output_file':job['sku']+'-visual-repair-'+digest[:10]+'.jpg',
                         'prompt':prompt,'seed':int(digest[:8],16),'original_file':job['output_file']})
    with args.output.open('x') as stream:
        for row in rows:
            stream.write(json.dumps(row)+'\n')
