import sys,math,json,tempfile,unittest
from pathlib import Path
from dataclasses import replace,asdict
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2,numpy as np,imageio_ffmpeg as ff
from advanced_axis import geometry,AxisTracker
from subpixel import precision_warp
from video_effects import Effects,process_clip
from video_core import VideoClip
from jitter_pass import residual_plan


class AdvancedAxisTests(unittest.TestCase):
    def base(self):
        a=np.full((360,300,3),190,np.uint8);a[20:340,140:160]=50;return a

    def test_known_subpixel_motion_and_nonvertical_reference(self):
        base=self.base();roi=(.3,.3,.4,.5);anchor=(149.5,197.5);frames=[];truth=[]
        for i in range(16):
            angle=2+1.5*math.sin(i*.4);shift=3*math.cos(i*.5)
            m=cv2.getRotationMatrix2D(anchor,angle,1);m[0,2]+=shift
            frames.append(precision_warp(base,m));truth.append((angle,anchor[0]+shift))
        for strategy in ('robust','reference','hybrid'):
            tracker=AxisTracker(frames[0],Effects(axis_strategy=strategy,axis_roi=roi));errors=[]
            for frame,t in zip(frames,truth):
                p=tracker.measure(frame);self.assertIsNotNone(p);errors.append([p[1]-t[0],p[0][0]-t[1]])
            rms=np.sqrt(np.mean(np.array(errors)**2,axis=0));self.assertLess(rms[0],.07,(strategy,rms));self.assertLess(rms[1],.15,(strategy,rms))

    def test_reference_alignment_does_not_accumulate_drift(self):
        base=self.base();s=Effects(axis_strategy='reference',axis_roi=(.3,.3,.4,.5));tracker=AxisTracker(base,s);initial=tracker.measure(base)
        for i in range(20):
            m=cv2.getRotationMatrix2D((149.5,197.5),math.sin(i)*2,1);m[0,2]+=math.cos(i)*4;self.assertIsNotNone(tracker.measure(precision_warp(base,m)))
        final=tracker.measure(base);np.testing.assert_allclose(final[0],initial[0],atol=1e-5);self.assertAlmostEqual(final[1],initial[1],places=5)

    def test_hybrid_fallback_and_strict_reference_rejection(self):
        base=self.base();s=Effects(axis_strategy='hybrid',axis_roi=(.3,.3,.4,.5));hybrid=AxisTracker(base,s);reference=AxisTracker(base,replace(s,axis_strategy='reference'))
        with patch('advanced_axis.cv2.findTransformECC',side_effect=cv2.error('no convergence')):
            self.assertIsNotNone(hybrid.measure(base));self.assertIsNone(reference.measure(base))
        self.assertEqual(hybrid.report()['fallback_frames'],1);self.assertEqual(reference.report()['rejected_frames'],1)

    def test_rotating_flutes_highlights_and_local_outlier_do_not_take_over(self):
        base=self.base();roi=(.3,.3,.4,.5);initial=geometry(base,roi,18)[0]
        for shift in (-20,0,20):
            a=base.copy();a[20:90,125+shift:175+shift]=20;a[150:210,147:153]=240
            a[180:187,168:174]=10
            p=geometry(a,roi,18);self.assertIsNotNone(p);self.assertLess(abs(p[0][1]),.03);self.assertLess(abs(p[0][0][0]-initial[0][0]),.05)

    def test_cubic_identity_subpixel_change_and_premultiplied_alpha(self):
        a=self.base();identity=np.array([[1.,0,0],[0,1,0]],np.float32)
        for quality in ('subpixel','cubic'):
            np.testing.assert_array_equal(precision_warp(a,identity,quality=quality),a)
            first=precision_warp(a,np.array([[1,0,.004],[0,1,0]],np.float32),quality=quality);second=precision_warp(a,np.array([[1,0,.014],[0,1,0]],np.float32),quality=quality)
            self.assertFalse(np.array_equal(first,second))
            rgba=np.zeros((64,64,4),np.uint8);rgba[:,:,:3]=[255,0,0];rgba[15:50,20:42]=[50,100,150,255]
            out=precision_warp(rgba,np.array([[1,0,.4],[0,1,.2]],np.float32),True,quality)
            self.assertEqual(out[0,0,3],0);self.assertGreater(out[30,30,3],250)
            visible=out[:,:,3]>80;self.assertLess(np.max(abs(out[:,:,:3][visible].astype(int)-[50,100,150])),5)

    def test_fixed_second_pass_pins_axis_instead_of_preserving_drift(self):
        poses=[(np.array([100+i*.02+(-1)**i*.2,120]),.12*math.sin(i),1) for i in range(50)]
        s=Effects(second_mode='lock',second_max_shift=3,second_max_angle=.5);matrices,r=residual_plan(poses,(256,256),30,s)
        points=[]
        for m,p in zip(matrices,poses):
            points.append(m[:,:2]@p[0]+m[:,2]);v=m[:,:2]@np.array([math.sin(math.radians(p[1])),math.cos(math.radians(p[1]))]);self.assertAlmostEqual(v[0],0,places=5)
        self.assertLess(np.ptp(np.array(points)[:,0]),.0001);self.assertEqual(r['mode'],'lock')

    def test_new_recipe_fields_roundtrip_and_reject_invalid_values(self):
        s=Effects(axis_strategy='hybrid',axis_reference=12,axis_mask_min_score=.99,render_quality='cubic',second_mode='lock');s.validate();restored=Effects(**json.loads(json.dumps(asdict(s))));self.assertEqual(json.dumps(asdict(restored),sort_keys=True),json.dumps(asdict(s),sort_keys=True))
        for q in (replace(s,axis_strategy='unknown'),replace(s,axis_reference=-1),replace(s,axis_mask_min_score=float('nan')),replace(s,second_mode='x'),replace(s,render_quality='x')):
            with self.assertRaises(ValueError):q.validate()

    def test_encoded_advanced_modes_alpha_and_frame_grid(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source.mp4';writer=ff.write_frames(str(source),(256,256),fps=12,codec='libx264',macro_block_size=1);writer.send(None)
            for i in range(12):
                a=np.full((256,256,3),255,np.uint8);a[20:240,118:138]=[40,60,80];m=cv2.getRotationMatrix2D((127.5,140),math.sin(i)*1.2,1);m[0,2]+=math.cos(i)*2;writer.send(precision_warp(a,m).tobytes())
            writer.close();clip=VideoClip(source)
            try:
                for strategy in ('robust','reference','hybrid'):
                    s=Effects(axis_lock=True,axis_strategy=strategy,axis_roi=(.3,.3,.4,.5),axis_reference=3,render_quality='cubic' if strategy=='reference' else 'subpixel',second_mode='lock',edge=256,remove_background=strategy=='hybrid',background='transparent' if strategy=='hybrid' else '#ffffff')
                    result=process_clip(clip,s)
                    try:
                        self.assertEqual(result.count,clip.count);self.assertEqual(result.effect_report['second_pass']['mode'],'lock');self.assertIn('advanced_tracking',result.effect_report['shaft_lock'])
                        self.assertEqual(result.effect_report['shaft_lock']['advanced_tracking']['strategy'],strategy)
                        if strategy=='hybrid':
                            self.assertEqual(result.rgba_frame(0).getpixel((0,0))[3],0)
                            from colour_video import export_colour_loop
                            out=root/'final.mov';info=export_colour_loop(result,0,10,out,{},edge=256);self.assertEqual(info['output_frames'],10)
                            gen=ff.read_frames(out,pix_fmt='rgba',bits_per_pixel=32);next(gen);a=np.frombuffer(next(gen),np.uint8).reshape(256,256,4);gen.close();self.assertLess(a[0,0,3],5);self.assertGreater(a[128,128,3],240)
                    finally:result.close()
            finally:clip.close()

if __name__=='__main__':unittest.main()
