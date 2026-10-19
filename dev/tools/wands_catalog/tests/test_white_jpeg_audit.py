import sys
from pathlib import Path
import unittest
import tempfile
import hashlib

from PIL import Image,ImageDraw,ImageFilter

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from white_jpeg_audit import metrics,decision
from white_jpeg_audit_run import clone_copy


class WhiteJpegAuditTest(unittest.TestCase):
    def test_selected_copy_cannot_mutate_an_original_through_a_hard_link(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'original.jpg';source.write_bytes(b'original bytes')
            target=root/(hashlib.sha256(source.read_bytes()).hexdigest()+'.jpg')
            clone_copy(source,target)
            self.assertEqual(source.read_bytes(),target.read_bytes())
            self.assertNotEqual(source.stat().st_ino,target.stat().st_ino)
            target.write_bytes(b'changed selection')
            self.assertEqual(source.read_bytes(),b'original bytes')
    def product(self,background):
        image=Image.new('RGB',(256,256),background)
        draw=ImageDraw.Draw(image)
        draw.rectangle((65,50,190,200),fill=(40,80,140))
        draw.rectangle((80,80,175,100),fill=(140,80,40))
        return image

    def test_good_plain_product_reuses_white_jpeg(self):
        original=self.product((244,237,222));output=self.product('white')
        self.assertEqual(decision({'output_file':'out.jpg'},metrics(original,output),[7,9,1,1,0,1,1])[0],'white')

    def test_removing_the_old_soft_shadow_does_not_count_as_product_loss(self):
        background=(244,237,222)
        source=Image.new('RGB',(256,256),background)
        shadow=Image.new('RGB',source.size,background)
        ImageDraw.Draw(shadow).ellipse((32,180,224,230),fill=(165,160,150))
        source=shadow.filter(ImageFilter.GaussianBlur(10))
        product=self.product(background)
        source.paste(product.crop((65,50,191,201)),(65,50))
        self.assertEqual(decision({'output_file':'out.jpg'},metrics(source,self.product('white')),[7,9,1,1,0,1,1])[0],'white')

    def test_neutral_shadow_on_warm_backdrop_is_not_product_loss(self):
        source=Image.new('RGB',(256,256),(244,237,222))
        ImageDraw.Draw(source).ellipse((32,180,224,230),fill=(160,160,160))
        source=source.filter(ImageFilter.GaussianBlur(10))
        product=self.product((244,237,222));source.paste(product.crop((65,50,191,201)),(65,50))
        self.assertEqual(decision({'output_file':'out.jpg'},metrics(source,self.product('white')),[7,9,1,1,0,1,1])[0],'white')

    def test_room_background_keeps_original_despite_confident_model(self):
        source=self.product((242,230,210))
        ImageDraw.Draw(source).rectangle((0,205,255,255),fill=(140,110,80))
        self.assertEqual(decision({'output_file':'out.jpg'},metrics(source,self.product('white')),[7,9,1,1,0,1,1]),('original','non_solid_or_scene_background'))

    def test_erased_product_keeps_original(self):
        source=self.product((244,237,222));output=Image.new('RGB',source.size,'white')
        self.assertEqual(decision({'output_file':'out.jpg'},metrics(source,output),[7,9,1,1,0,1,1])[0],'original')

    def test_non_finite_model_scores_are_uncertain(self):
        m=metrics(self.product((244,237,222)),self.product('white'))
        self.assertEqual(decision({'output_file':'out.jpg'},m,[float('nan'),9,1,1,0,1,1])[0],'original')

    def test_uncertain_scene_semantics_keeps_original(self):
        m=metrics(self.product((244,237,222)),self.product('white'))
        self.assertEqual(decision({'output_file':'out.jpg'},m,[3,4,3,4,1,2,3]),('original','scene_or_uncertain_semantics'))

    def test_remaining_verified_product_is_eligible_not_yet_selected(self):
        self.assertEqual(decision({},metrics(self.product((244,237,222))),[7,9,1,1,0,1,1])[0],'eligible')

    def test_flagged_cutouts_never_reused(self):
        m=metrics(self.product((244,237,222)),self.product('white'))
        self.assertEqual(decision({'output_file':'out.jpg','warning':'tiny foreground'},m,[7,9,1,1,0,1,1]),('original','flagged_cutout'))

    def test_actual_failed_mirrors_are_rejected(self):
        root=Path(__file__).resolve().parents[4]/'var/catalog-expansion-20260918'
        originals=root/'accepted-export-completion-20261003/media/wands-expanded'
        media=root/'white-jpeg-bulk-20261012/media/wands-expanded'
        pairs=[('98f3096dc16fd278b1e293e6d729cef2bec95f96e5a960621146f66bb8601a47.jpg','75ebdb235d762584cca9790122b74d35f3dc9e3e0f2df93b706fa903474164c3.jpg'),('f235273c6bcb056413c6f9d16e38fc81fdad28cc3a6337c0c0943885ed542093.jpg','1dceb0d7e85ae6b4f20a4155829fe9497534e77e0ccaa6129a86fa9f925c26b7.jpg')]
        for source,output in pairs:
            with Image.open(originals/source) as a,Image.open(media/output) as b:
                m=metrics(a.convert('RGB'),b.convert('RGB'))
            self.assertEqual(decision({'output_file':output},m,[7,9,1,1,0,1,1])[0],'original')


if __name__=='__main__':unittest.main()
