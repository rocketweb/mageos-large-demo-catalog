from pathlib import Path
import sys
import sqlite3
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import white_jpeg_glass_outline as glass


class OutlineTest(unittest.TestCase):
    def test_printed_interior_cannot_hide_an_erased_glass_frame(self):
        from PIL import Image, ImageDraw
        original=Image.new('RGB',(768,768),(250,242,224))
        white=Image.new('RGB',(768,768),'white')
        for im in [original,white]:
            d=ImageDraw.Draw(im)
            for x in range(220,550,6):d.line((x,230,x,550),fill=(30,30,30),width=2)
        ImageDraw.Draw(original).rectangle((150,120,630,640),outline=(110,110,105),width=3)
        self.assertEqual(glass.choose(glass.features(original,white))[0],'review')

    def test_whitened_backdrop_keeps_a_visible_glass_frame(self):
        from PIL import Image,ImageDraw
        a=Image.new('RGB',(768,768),(250,242,224));b=Image.new('RGB',(768,768),'white')
        for im in [a,b]:ImageDraw.Draw(im).rectangle((150,120,630,640),outline=(110,110,105),width=3)
        self.assertEqual(glass.choose(glass.features(a,b))[0],'preserved')

    def test_generic_worker_cannot_reapprove_a_glass_hold(self):
        db=sqlite3.connect(':memory:');db.execute('CREATE TABLE images(file TEXT PRIMARY KEY,decision TEXT,reason TEXT)')
        glass.protect(db)
        db.execute("INSERT INTO images VALUES('glass.jpg',NULL,NULL)")
        db.execute("INSERT INTO glass_outline_checks(file,verdict,reason) VALUES('glass.jpg','pending_review','outline missing')")
        db.execute("UPDATE images SET decision='white',reason='generic approval' WHERE file='glass.jpg'")
        self.assertEqual(db.execute('SELECT decision FROM images').fetchone()[0],'original')

    def test_outline_clearance_does_not_promote_an_original(self):
        db=sqlite3.connect(':memory:');db.execute('CREATE TABLE images(file TEXT PRIMARY KEY,decision TEXT,reason TEXT)');glass.protect(db)
        db.execute("INSERT INTO images VALUES('glass.jpg','original','scene')")
        db.execute("INSERT INTO glass_outline_checks(file,verdict) VALUES('glass.jpg','preserved')")
        self.assertEqual(db.execute('SELECT decision FROM images').fetchone()[0],'original')


if __name__=='__main__':unittest.main()
