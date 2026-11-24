import sys,tempfile,unittest
from pathlib import Path
from dataclasses import replace
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from video_effects import Effects,mask_frame,pose,plan_transforms,apply_transform,process_clip
from video_core import VideoClip,export_loop
import imageio_ffmpeg as ffmpeg

class EffectsTests(unittest.TestCase):
    def test_target_mask_keeps_interior_highlight(self):
        a=np.full((128,128,3),255,np.uint8);a[20:110,50:78]=60;a[40:50,60:67]=255
        alpha=mask_frame(a,Effects(feather=0));self.assertEqual(alpha[0,0],0);self.assertEqual(alpha[45,63],1);self.assertEqual(alpha[70,55],1)
    def test_rigid_aim_is_vertical_and_centred(self):
        p=(np.array([60.,70.]),12.,10.);s=Effects(smart_aim=True,max_shift=40,target_x=.5,target_y=.5,smoothing=0)
        m,_=plan_transforms([p],(128,128),30,s);axis=np.array([np.sin(np.radians(12)),np.cos(np.radians(12))]);v=m[0][:,:2]@axis
        self.assertAlmostEqual(v[0],0,places=5);np.testing.assert_allclose(m[0][:,:2]@p[0]+m[0][:,2],[64,64],atol=.001)
    def test_standard_smoothing_reduces_jitter_without_rotating(self):
        ps=[(np.array([64.+(-1)**i*5,64]),10,10) for i in range(30)]
        ms,_=plan_transforms(ps,(128,128),30,Effects(smoothing=.2));xs=[(m[:,:2]@p[0]+m[:,2])[0] for m,p in zip(ms,ps)]
        self.assertLess(np.std(xs),2);np.testing.assert_allclose(ms[0][:,:2],np.eye(2))
    def test_missing_tracking_and_safety_limits(self):
        with self.assertRaises(ValueError):plan_transforms([None]*10,(128,128),30,Effects())
        ps=[(np.array([20.+i*3,64]),35,10) for i in range(10)];ms,_=plan_transforms(ps,(128,128),30,Effects(smart_aim=True,max_shift=1,max_angle=5))
        for m,p in zip(ms,ps):self.assertLessEqual(np.max(abs((m[:,:2]@p[0]+m[:,2])-p[0])),1.281)
    def test_alpha_and_replacement_colour(self):
        rgb=np.full((32,32,3),100,np.uint8);alpha=np.zeros((32,32),np.float32);alpha[8:24,8:24]=1;m=np.array([[1,0,0],[0,1,0]],np.float32)
        out=apply_transform(rgb,alpha,m,'transparent','#ffffff');self.assertEqual(out[0,0,3],0);self.assertEqual(out[12,12,3],255)
        out=apply_transform(rgb,alpha,m,'#f5a900','#ffffff');np.testing.assert_array_equal(out[0,0,:3],[245,169,0])
    def test_real_encoding_alpha_loop_and_stabilized_jitter(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);src=root/'jitter.mp4';wr=ffmpeg.write_frames(str(src),(128,128),fps=12,codec='libx264',macro_block_size=1);wr.send(None)
            for i in range(30):
                a=np.full((128,128,3),255,np.uint8);x=50+(-1)**i*4;a[15:113,x:x+25]=[50,70,90];wr.send(a.tobytes())
            wr.close();original=VideoClip(src);processed=None
            try:
                processed=process_clip(original,Effects(smart_aim=True,background='transparent',edge=128,feather=.5))
                self.assertEqual(processed.count,original.count);out=root/'alpha.mov';info=export_loop(processed,0,24,out,edge=128)
                self.assertTrue(info['transparent']);self.assertEqual(ffmpeg.count_frames_and_secs(str(out))[0],24)
                gen=ffmpeg.read_frames(str(out),pix_fmt='rgba',bits_per_pixel=32);next(gen);frame=np.frombuffer(next(gen),np.uint8).reshape(128,128,4);gen.close()
                self.assertLess(frame[0,0,3],5);self.assertGreater(frame[60,64,3],240)
                logo=root/'logo.png';Image.new('RGBA',(20,10),'red').save(logo);out2=root/'alpha-logo.mov';export_loop(processed,0,24,out2,edge=128,logo_path=str(logo),logo_x=2,logo_y=2)
                gen=ffmpeg.read_frames(str(out2),pix_fmt='rgba',bits_per_pixel=32);next(gen);f=np.frombuffer(next(gen),np.uint8).reshape(128,128,4);gen.close();self.assertLess(f[127,127,3],5);self.assertGreater(f[4,4,3],240)
                from colour_video import export_colour_loop
                out3=root/'graded-alpha.mov';export_colour_loop(processed,0,24,out3,{'temperature':20,'contrast':10},edge=128,logo_path=str(logo),logo_x=2,logo_y=2)
                gen=ffmpeg.read_frames(str(out3),pix_fmt='rgba',bits_per_pixel=32);next(gen);f=np.frombuffer(next(gen),np.uint8).reshape(128,128,4);gen.close();self.assertLess(f[127,127,3],5);self.assertGreater(f[4,4,3],240)
            finally:
                if processed:processed.close()
                original.close()
if __name__=='__main__':unittest.main()
