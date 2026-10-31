import sys,json,tempfile,unittest,hashlib
from pathlib import Path
from dataclasses import replace
import cv2
import numpy as np
import imageio_ffmpeg as ffmpeg
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jitter_pass import residual_plan,second_pass_clip,processed_band
from video_effects import Effects,ProcessedClip,process_clip
from video_core import VideoClip
from shaft_tracking import shaft_pose


class JitterTests(unittest.TestCase):
    def test_residual_smoothing_removes_jitter_and_preserves_slow_drift(self):
        poses=[(np.array([100+i*.03+(-1)**i*.6,120]),(-1)**i*.15,1) for i in range(80)]
        s=Effects(second_max_shift=1,second_max_angle=.2)
        matrices,r=residual_plan(poses,(240,240),30,s)
        out=np.array([(m[:,:2]@p[0]+m[:,2])[0] for m,p in zip(matrices,poses)])
        self.assertLess(np.std(np.diff(out)),.03);self.assertGreater(out[-1]-out[0],1.8)
        self.assertLessEqual(r['max_applied_shift_px'],1);self.assertLessEqual(r['max_applied_angle_deg'],.2)
        self.assertEqual(r['safety_limited_frames'],0)
        for m in matrices:np.testing.assert_allclose(m[:,:2].T@m[:,:2],np.eye(2),atol=1e-6)

    def test_limits_zero_strength_and_tracking_failure(self):
        poses=[(np.array([100.+(-1)**i*3,100]),(-1)**i*2,1) for i in range(60)]
        s=Effects(second_max_shift=.2,second_max_angle=.1)
        _,r=residual_plan(poses,(240,240),30,s);self.assertEqual(r['safety_limited_frames'],60)
        matrices,r=residual_plan(poses,(240,240),30,replace(s,second_strength=0))
        for m in matrices:np.testing.assert_allclose(m,np.array([[1,0,0],[0,1,0]]),atol=1e-5)
        with self.assertRaises(ValueError):residual_plan([None]*60,(240,240),30,s)
        p=poses[0]
        with self.assertRaises(ValueError):residual_plan([p]*60+[None]*7+[p]*60,(240,240),30,s)

    def test_validation_and_crop_band_mapping(self):
        for s in (Effects(second_strength=float('nan')),Effects(second_smoothing=0),Effects(second_max_shift=25),Effects(second_max_angle=4),Effects(second_pass='yes')):
            with self.assertRaises(ValueError):s.validate()
        from types import SimpleNamespace
        clip=SimpleNamespace(size=(1000,500));s=Effects(axis_roi=(.4,.4,.2,.3),border_crop=10)
        np.testing.assert_allclose(processed_band(clip,s),(350/900,150/400,200/900,150/400))

    def make_clip(self,root,transparent=False):
        path=root/('first.mov' if transparent else 'first.mp4');s=Effects(axis_lock=True,axis_roi=(.3,.3,.4,.5),remove_background=transparent,background='transparent' if transparent else '#ffffff',edge=256,second_pass=False)
        writer=ffmpeg.write_frames(str(path),(256,256),fps=24,pix_fmt_in='rgba',pix_fmt_out='yuva444p10le' if transparent else 'yuv420p',codec='prores_ks' if transparent else 'libx264',macro_block_size=1,output_params=['-profile:v','4','-alpha_bits','16'] if transparent else ['-crf','12']);writer.send(None)
        for i in range(48):
            a=np.full((256,256,4),[185,185,185,255],np.uint8)
            if transparent:a[:]=0
            a[20:240,118:138]=[60,70,80,255]
            m=cv2.getRotationMatrix2D((128,140),(-1)**i*.15,1);m[0,2]+=(-1)**i*.65
            frame=cv2.warpAffine(a,m,(256,256),borderMode=cv2.BORDER_CONSTANT,borderValue=(0,0,0,0) if transparent else (185,185,185,255));writer.send(frame.tobytes())
        writer.close()
        report={'tracked_frames':48,'total_frames':48,'interpolated_frames':0,'settings':{}}
        # Deliberately nonexistent original source proves pass two reads first.path.
        return ProcessedClip(path,s,str(root/'original-is-not-readable.mp4'),report)

    def test_standalone_uses_first_pass_pixels_and_preserves_grid_and_ownership(self):
        with tempfile.TemporaryDirectory() as d:
            first=self.make_clip(Path(d));result=None
            try:
                expected=hashlib.sha256(Path(first.path).read_bytes()).hexdigest();result=second_pass_clip(first,replace(first.effects,second_pass=True))
                self.assertIs(result.first_pass,first);self.assertFalse(first.closed);self.assertEqual(result.count,48);self.assertEqual(result.size,(256,256));self.assertEqual(result.fps,first.fps)
                self.assertEqual(result.effect_report['second_pass']['input_sha256'],expected)
                def centers(path):
                    g=ffmpeg.read_frames(path);next(g);out=[]
                    for b in g:
                        p=shaft_pose(np.frombuffer(b,np.uint8).reshape(256,256,3),first.effects.axis_roi);self.assertIsNotNone(p);out.append(p[0][0])
                    g.close();return np.array(out)
                before,after=centers(first.path),centers(result.path)
                self.assertLess(np.std(np.diff(after)),np.std(np.diff(before))*.4)
                with self.assertRaises(ValueError):second_pass_clip(result,result.effects)
            finally:
                if result:result.close();self.assertTrue(first.closed)
                else:first.close()

    def test_transparent_second_pass_and_final_export_keep_alpha_and_count(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);first=self.make_clip(root,True);result=None
            try:
                result=second_pass_clip(first,replace(first.effects,second_pass=True))
                self.assertEqual(result.rgba_frame(0).getpixel((0,0))[3],0)
                from colour_video import export_colour_loop
                out=root/'final.mov';export_colour_loop(result,0,24,out,{},edge=256)
                self.assertEqual(ffmpeg.count_frames_and_secs(str(out))[0],24)
                g=ffmpeg.read_frames(out,pix_fmt='rgba',bits_per_pixel=32);next(g);a=np.frombuffer(next(g),np.uint8).reshape(256,256,4);g.close()
                self.assertLess(a[0,0,3],5);self.assertGreater(a[128,128,3],240)
                report=json.loads(out.with_suffix('.loop.json').read_text());self.assertIn('second_pass',report['effects'])
            finally:
                if result:result.close()
                else:first.close()

    def test_automatic_pipeline_finishes_first_then_reads_it(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);first=self.make_clip(root);original=VideoClip(first.path);result=None
            try:
                result=process_clip(original,replace(first.effects,second_pass=True));self.assertTrue(hasattr(result,'first_pass'))
                self.assertEqual(result.count,original.count)
                expected=hashlib.sha256(Path(result.first_pass.path).read_bytes()).hexdigest()
                self.assertEqual(result.effect_report['second_pass']['input_sha256'],expected)
                self.assertEqual(result.effect_report['second_pass']['tracked_frames'],48)
            finally:
                if result:result.close()
                original.close();first.close()

if __name__=='__main__':unittest.main()
