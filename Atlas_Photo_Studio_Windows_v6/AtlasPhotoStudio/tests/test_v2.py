import json,sys,tempfile,unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core
from core import Settings,render,load_proxy,remove_white,build_name,export_batch,MAIN_SUFFIX
class StudioV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.photo=self.root/'tool.png';self.logo=self.root/'logo.png'
        im=Image.new('RGB',(900,1200),'white');d=ImageDraw.Draw(im);d.rectangle((300,60,600,1100),fill='#505050');d.rectangle((350,120,550,300),fill='white');im.save(self.photo)
        Image.new('RGBA',(150,40),(255,170,0,255)).save(self.logo)
        self.s=Settings(logo_path=str(self.logo),output_dir=str(self.root/'out'),logo_x=0,logo_y=0,crop_aspect='Freehand')
    def tearDown(self):self.temp.cleanup()
    def test_white_removal_preserves_enclosed_metal_highlight(self):
        im=remove_white(core.load_image(self.photo));self.assertEqual(im.getpixel((0,0))[3],0);self.assertEqual(im.getpixel((400,180))[3],255);self.assertEqual(im.getpixel((400,500))[:3],(80,80,80))
    def test_coloured_background_is_not_keyed(self):
        im=Image.new('RGBA',(60,60),(230,245,255,255));self.assertEqual(remove_white(im).getpixel((0,0))[3],255)
    def test_mainshot_png_suffix_crop_and_transparency(self):
        self.s.square=True
        images=export_batch([(str(self.photo),'Top'),(str(self.photo),'Reverse')],'Atlas 8x22',self.s)
        m=images[0];self.assertTrue(m['file'].endswith(MAIN_SUFFIX+'.png'));self.assertTrue(m['alt'].endswith(MAIN_SUFFIX));self.assertEqual((m['width'],m['height']),(900,660))
        with Image.open(m['file']) as im:self.assertEqual(im.getpixel((0,0))[3],0)
        self.assertTrue(images[1]['file'].endswith('.jpg'));self.assertEqual(images[1]['width'],images[1]['height'])
    def test_custom_crop_source_coordinates(self):
        self.s.crop_boxes=json.dumps({str(self.photo):[1/3,0,2/3,.5]})
        im=render(self.photo,self.s,main=True);self.assertEqual(im.size,(300,600))
    def test_bad_crop_is_rejected(self):
        self.s.crop_boxes=json.dumps({str(self.photo):[.5,.5,.2,.2]})
        with self.assertRaises(ValueError):render(self.photo,self.s,main=True)
    def test_pixel_origin_and_preview_scaling(self):
        self.s.longest_edge=600;self.s.logo_x=75;self.s.logo_y=120
        full=render(self.photo,self.s);self.assertEqual(full.getpixel((75,120))[:3],(255,170,0))
        self.s.preview_edge=360;proxy=render(self.photo,self.s,preview=True)
        self.assertEqual(proxy.size,(270,360));self.assertEqual(proxy.getpixel((45,72))[:3],(255,170,0))
    def test_fast_proxy_avoids_full_quality_loader(self):
        load_proxy(self.photo,720)
        with patch.object(core,'load_image',side_effect=AssertionError('Full loader must not run')):
            for x in range(4):
                self.s.logo_x=x*10;render(self.photo,self.s,preview=True)
    def test_proxy_cache_invalidates_on_file_change(self):
        first=load_proxy(self.photo,360);Image.new('RGB',(900,1200),'black').save(self.photo);second=load_proxy(self.photo,360)
        self.assertNotEqual(first.getpixel((0,0)),second.getpixel((0,0)))
    def test_independent_prefix_postfix_enabled_blocks(self):
        raw=json.dumps([{'kind':'text','value':'Atlas Tools'},{'kind':'name'},{'kind':'text','value':'ZrN'},{'kind':'text','value':'HIDDEN','enabled':False}])
        out=build_name(raw,'TCT 8x22','Top',1,' ',True,True)
        self.assertEqual(out,'Atlas Tools TCT 8x22 ZrN - MAINSHOT CLOSEUP')
    def test_main_suffix_survives_long_names(self):
        raw=json.dumps([{'kind':'name'},{'kind':'text','value':'POSTFIX'}])
        for filename in (True,False):self.assertTrue(build_name(raw,'A'*600,'Top',1,' - ',True,filename).endswith(MAIN_SUFFIX))
    def test_duplicate_blocks_do_not_overwrite(self):
        raw=json.dumps([{'kind':'name'}]);self.s.filename_blocks=raw
        images=export_batch([(str(self.photo),'a'),(str(self.photo),'b'),(str(self.photo),'c')],'Same',self.s)
        self.assertEqual(len({m['file'] for m in images}),3)
    def test_save_settings_without_logo(self):
        self.s.logo_path='';self.s.shop='atlas.myshopify.com';self.s.validate(require_logo=False)
        self.assertEqual(json.loads(json.dumps(asdict(self.s)))['shop'],'atlas.myshopify.com')
if __name__=='__main__':unittest.main()
