import sys,json,tempfile,unittest
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from colour import *
from core import Settings,export_batch
from colour_video import export_colour_loop
from video_core import VideoClip
import imageio_ffmpeg as ffmpeg

class ColourTests(unittest.TestCase):
 def test_identity_is_bit_exact_and_alpha_preserved(self):
  a=np.random.default_rng(9).integers(0,256,(32,40,4),dtype=np.uint8);im=Image.fromarray(a)
  np.testing.assert_array_equal(np.asarray(apply_colour(im,{})),a)
  np.testing.assert_array_equal(np.asarray(apply_colour(im,{'exposure':1,'clarity':30}))[:,:,3],a[:,:,3])
 def test_exposure_wb_vibrance_blacks_and_hsl(self):
  im=Image.new('RGB',(16,16),(90,65,40));base=np.asarray(im,dtype=float).mean()
  self.assertGreater(np.asarray(apply_colour(im,{'exposure':1}))[:,:,:3].mean(),base)
  warm=np.asarray(apply_colour(im,{'temperature':50}))[0,0];self.assertGreater(warm[0],90);self.assertLess(warm[2],40)
  self.assertGreater(apply_colour(im,{'blacks':60}).getpixel((0,0))[2],40)
  hsl=apply_colour(Image.new('RGB',(16,16),'red'),{'red_hue':100});self.assertGreater(hsl.getpixel((0,0))[1],30)
 def test_all_controls_finite_and_full_preset_roundtrip(self):
  im=Image.fromarray(np.random.default_rng(1).integers(0,256,(20,20,3),dtype=np.uint8))
  for key,(_,_,lo,hi,_) in SPECS.items():
   result=np.asarray(apply_colour(im,{key:hi}));self.assertEqual(result.shape,(20,20,4))
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'preset.json';s=validate({'contrast':25,'blue_lum':-10,'curve_master':[[0,0],[.5,.65],[1,1]]});write_preset(p,s);self.assertEqual(read_preset(p),s)
 def test_invalid_import_and_curve_are_rejected(self):
  with self.assertRaises(ValueError):validate({'exposure':1000})
  with self.assertRaises(ValueError):validate({'contrast':float('nan')})
  with self.assertRaises(ValueError):validate({'curve_master':[[0,0],[0,.5],[1,1]]})
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'other.json';p.write_text('{}')
   with self.assertRaises(ValueError):read_preset(p)
 def test_image_export_bakes_recipe_and_writes_importable_sidecar(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'tool.png';Image.new('RGB',(300,400),(60,70,80)).save(p)
   s=Settings(output_dir=d,colour_json=json.dumps({'exposure':1}))
   item=export_batch([(str(p),'Top')],'Atlas',s)[0]
   self.assertEqual(read_preset(item['colour_preset'])['exposure'],1)
   with Image.open(item['file']) as out:self.assertGreater(out.getpixel((100,100))[0],60)
 def test_video_export_grade_sidecar_count_and_logo_order(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);src=root/'source.mp4';wr=ffmpeg.write_frames(str(src),(128,128),fps=12,codec='libx264',macro_block_size=1);wr.send(None)
   for i in range(30):wr.send(np.full((128,128,3),[80,90,100],np.uint8).tobytes())
   wr.close();clip=VideoClip(src)
   try:
    logo=root/'logo.png';Image.new('RGBA',(20,10),'red').save(logo)
    out=root/'graded.mp4';info=export_colour_loop(clip,0,24,out,{'exposure':1,'monochrome':100},edge=128,logo_path=str(logo),logo_x=2,logo_y=2)
    self.assertEqual(info['output_frames'],24);self.assertEqual(ffmpeg.count_frames_and_secs(str(out))[0],24)
    self.assertEqual(read_preset(out.with_suffix('.mp4.colour.json'))['monochrome'],100)
    reader=ffmpeg.read_frames(str(out));next(reader);a=np.frombuffer(next(reader),np.uint8).reshape(128,128,3);reader.close()
    self.assertGreater(a[4:10,4:15,0].mean(),a[4:10,4:15,1].mean()+100)
    self.assertLess(np.max(a[70,70])-np.min(a[70,70]),6)
    with self.assertRaises(ValueError):export_colour_loop(clip,0,24,out,{})
   finally:clip.close()
if __name__=='__main__':unittest.main()
