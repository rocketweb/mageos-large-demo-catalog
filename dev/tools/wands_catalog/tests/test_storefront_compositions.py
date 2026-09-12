from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_storefront_compositions import pack, validate_acceptance


class CompositionTest(unittest.TestCase):
    def test_pack_preserves_count_ratio_and_common_scale(self):
        source=[{'instance_id':str(i),'width':20+i*3,'height':40+i*7,'uniform_scale':1} for i in range(7)]
        result=pack(source,[3,4])
        self.assertEqual([r['instance_id'] for r in result],[str(i) for i in range(7)])
        scales=[]
        for old,new in zip(source,result):
            scales.append(new['width']/old['width'])
            self.assertAlmostEqual(new['width']/new['height'],old['width']/old['height'])
            self.assertGreaterEqual(new['x'],80-1e-7)
            self.assertLessEqual(new['x']+new['width'],920+1e-7)
        self.assertLess(max(scales)-min(scales),1e-7)

    def test_incomplete_duplicate_or_invalid_geometry_rejected(self):
        r={'instance_id':'a','width':20,'height':40,'uniform_scale':1}
        for rows,groups in (([r],[2]),([r,r],[2]),([{**r,'width':float('nan')}],[1])):
            with self.assertRaises(ValueError): pack(rows,groups)

    def test_acceptance_must_match_hash_and_pass_every_check(self):
        r={'verdict':'initial_visual_pass','checks':{'count':'pass'}}
        validate_acceptance(r,'abc','abc')
        for row,a,b in ((r,'abc','xyz'),({**r,'checks':{'count':'uncertain'}},'abc','abc'),({**r,'verdict':'pending'},'abc','abc')):
            with self.assertRaises(ValueError): validate_acceptance(row,a,b)


if __name__=='__main__': unittest.main()
