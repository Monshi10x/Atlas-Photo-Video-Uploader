import json,math,sys,tempfile,unittest
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crop_geometry import fit_ratio,move_box,resize_corner
from core import Settings,crop_for,render
from video_core import VideoClip,export_loop
import imageio_ffmpeg as ffmpeg

class CropTests(unittest.TestCase):
    def test_square_source_pixels_on_portrait(self):
        b=fit_ratio([0,0,900,660],(900,1200),1);self.assertAlmostEqual(b[2]-b[0],b[3]-b[1])
    def test_corner_lock_every_corner(self):
        for corner in ('nw','ne','se','sw'):
            b=resize_corner([100,100,400,300],corner,(50,40) if 'w' in corner else (900,700),(1000,800),16/9)
            self.assertAlmostEqual((b[2]-b[0])/(b[3]-b[1]),16/9);self.assertTrue(0<=b[0]<b[2]<=1000);self.assertTrue(0<=b[1]<b[3]<=800)
    def test_move_preserves_size_at_boundaries(self):
        b=move_box([100,200,400,500],-1000,1000,(900,1200));self.assertEqual(b,[0,900,300,1200])
    def test_freehand_changes_aspect(self):
        b=resize_corner([10,10,110,110],'se',(210,60),(300,300),None);self.assertEqual(b,[10,10,210,60])
    def test_locked_export_raster_stays_square_with_fractional_edges(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fractional.png';Image.new('RGB',(901,1203),'white').save(p)
            s=Settings(crop_boxes=json.dumps({str(p):[.123,.023,.743,.723]}))
            im=render(str(p),s,main=True);self.assertEqual(im.width,im.height)
    def test_default_square_and_persisted_aspects(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'photo.png';Image.new('RGB',(900,1200),'white').save(p);s=Settings()
            b=crop_for(str(p),s);self.assertAlmostEqual((b[2]-b[0])*900,(b[3]-b[1])*1200)
            s.crop_aspect='16:9';b=crop_for(str(p),s);self.assertAlmostEqual((b[2]-b[0])*900/((b[3]-b[1])*1200),16/9)
            s.crop_aspect='Freehand';b=crop_for(str(p),s);self.assertEqual(b,(0,0,1,.55))

class VideoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name);cls.source=cls.root/'rotation.mp4'
        writer=ffmpeg.write_frames(str(cls.source),(128,128),fps=12,codec='libx264',quality=9,macro_block_size=1);writer.send(None)
        for i in range(96):
            im=Image.new('RGB',(128,128),'white');draw=ImageDraw.Draw(im);angle=i%24/24*2*math.pi
            def point(x,y):return (64+x*math.cos(angle)-y*math.sin(angle),64+x*math.sin(angle)+y*math.cos(angle))
            draw.polygon([point(-12,-40),point(20,-25),point(12,42),point(-10,32)],fill='#204080');draw.ellipse([point(20,10)[0]-4,point(20,10)[1]-4,point(20,10)[0]+4,point(20,10)[1]+4],fill='red')
            writer.send(np.asarray(im).tobytes())
        writer.close();cls.clip=VideoClip(cls.source)
    @classmethod
    def tearDownClass(cls):cls.clip.close();cls.tmp.cleanup()
    def test_native_frame_grid_and_matching_rotation(self):
        self.assertEqual(self.clip.count,96);self.assertAlmostEqual(self.clip.fps,12)
        c=self.clip.find_loops(target=2,tolerance=.2)[0];self.assertEqual(c.end-c.start,24);self.assertLess(c.error,.01)
    def test_fixed_start_and_excluded_duplicate_frame(self):
        c=self.clip.find_loops(2,.2,5)[0];self.assertEqual((c.start,c.end),(5,29))
        output=self.root/'loop.mp4';info=export_loop(self.clip,c.start,c.end,output,edge=128)
        n,duration=ffmpeg.count_frames_and_secs(str(output));self.assertEqual(n,24);self.assertAlmostEqual(duration,2,places=2)
        self.assertEqual(info['matching_return_frame_excluded'],29)
    def test_crop_logo_and_output_size(self):
        logo=self.root/'logo.png';Image.new('RGBA',(20,10),'red').save(logo)
        output=self.root/'logo-loop.mp4';info=export_loop(self.clip,0,24,output,crop=(16,16,96,96),edge=128,logo_path=str(logo),logo_x=2,logo_y=4,logo_width=25)
        self.assertEqual(info['output_size'],[96,96])
        gen=ffmpeg.read_frames(str(output));meta=next(gen);a=np.frombuffer(next(gen),dtype=np.uint8).reshape((96,96,3));gen.close()
        patch=a[5:12,4:20].mean(axis=(0,1));self.assertGreater(patch[0],patch[1]+100)
    def test_source_and_existing_outputs_protected(self):
        with self.assertRaises(ValueError):export_loop(self.clip,0,24,self.source)
        out=self.root/'exists.mp4';out.write_bytes(b'keep')
        with self.assertRaises(ValueError):export_loop(self.clip,0,24,out)
        self.assertEqual(out.read_bytes(),b'keep')
    def test_bounds_and_static_detection(self):
        with self.assertRaises(ValueError):self.clip.validate_bounds(0,96)
        motion=self.clip.motion
        try:
            self.clip.motion=0
            with self.assertRaises(ValueError):self.clip.find_loops(2,.2)
        finally:self.clip.motion=motion
if __name__=='__main__':unittest.main()
