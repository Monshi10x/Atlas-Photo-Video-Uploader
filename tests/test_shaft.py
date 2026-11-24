import sys,unittest
from pathlib import Path
from dataclasses import replace
import cv2
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from shaft_tracking import shaft_pose,shaft_plan,refine_shaft_matrix
from video_effects import Effects,plan_transforms


class ShaftTests(unittest.TestCase):
    def test_rotating_flutes_do_not_change_axis(self):
        a=np.full((300,240,3),190,np.uint8);a[80:280,112:128]=60
        roi=(.35,.35,.3,.5);initial=shaft_pose(a,roi)
        self.assertIsNotNone(initial)
        for offset in (-12,0,12):
            b=a.copy();b[10:80,100+offset:138+offset]=20
            p=shaft_pose(b,roi)
            np.testing.assert_allclose(p[0],initial[0]);self.assertAlmostEqual(p[1],0,places=4)

    def test_pixel_output_is_steady_under_tilt_and_drift(self):
        a=np.full((360,300,3),185,np.uint8);a[25:340,140:160]=45
        roi=(.32,.3,.36,.5);frames=[];poses=[]
        for i in range(25):
            m=cv2.getRotationMatrix2D((150,220),np.sin(i/4)*2,1);m[0,2]+=np.cos(i/5)*5
            frame=cv2.warpAffine(a,m,(300,360),borderValue=(185,185,185));frames.append(frame);poses.append(shaft_pose(frame,roi))
        self.assertTrue(all(p is not None for p in poses))
        s=Effects(axis_lock=True,axis_roi=roi,max_angle=5,max_shift=10)
        matrices,valid,report=shaft_plan(poses,(300,360),30,s)
        output=[shaft_pose(cv2.warpAffine(f,m,(300,360),borderValue=(185,185,185)),roi) for f,m in zip(frames,matrices)]
        self.assertTrue(all(p is not None for p in output));self.assertEqual(sum(valid),25);self.assertEqual(report['safety_limited_frames'],0)
        self.assertLess(np.ptp([p[0][0] for p in output]),.25)
        self.assertLess(max(abs(p[1]) for p in output),.05)
        for m in matrices:np.testing.assert_allclose(m[:,:2].T@m[:,:2],np.eye(2),atol=1e-6)

    def test_rejects_missing_axis_and_long_gap(self):
        self.assertIsNone(shaft_pose(np.full((200,200,3),190,np.uint8),(.2,.2,.6,.6)))
        p=(np.array([100,100]),1.,1.)
        with self.assertRaises(ValueError):shaft_plan([None]*30,(200,200),30,Effects())
        with self.assertRaises(ValueError):shaft_plan([p]*50+[None]*6+[p]*50,(200,200),30,Effects())
        ms,valid,r=shaft_plan([p]*20+[None]+[p]*20,(200,200),30,Effects())
        self.assertEqual(len(ms),41);self.assertEqual(r['interpolated_frames'],1)

    def test_reports_safety_limits_and_rejects_invalid_band(self):
        ps=[(np.array([50.+i,100]),8.,1.) for i in range(20)]
        _,_,r=shaft_plan(ps,(200,200),30,Effects(max_angle=2,max_shift=1))
        self.assertEqual(r['safety_limited_frames'],20)
        for s in (Effects(axis_roi=(0,0,2,1)),Effects(axis_contrast=float('nan')),Effects(tracking_edge=256)):
            with self.assertRaises(ValueError):s.validate()

    def test_smart_aim_corrects_current_angle_instead_of_smoothed_angle(self):
        ps=[(np.array([60.,70.]),(-1)**i*8.,10.) for i in range(20)]
        matrices,_=plan_transforms(ps,(128,128),30,Effects(smart_aim=True,smoothing=.4))
        for m,p in zip(matrices,ps):
            axis=np.array([np.sin(np.radians(p[1])),np.cos(np.radians(p[1]))])
            self.assertAlmostEqual(float((m[:,:2]@axis)[0]),0,places=5)

    def test_render_refinement_keeps_safety_bounds_and_partial_strength(self):
        a=np.full((360,300,3),185,np.uint8);a[25:340,140:160]=45;roi=(.32,.3,.36,.5)
        source=cv2.warpAffine(a,cv2.getRotationMatrix2D((150,220),1.4,1),(300,360),borderValue=(185,185,185))
        p=shaft_pose(source,roi);s=Effects(axis_lock=True,axis_roi=roi,max_angle=5,max_shift=10)
        matrices,_,_=shaft_plan([p],(300,360),30,s)
        m,n=refine_shaft_matrix(source,matrices[0],p[0],s)
        self.assertGreater(n,0);self.assertLessEqual(abs(np.degrees(np.arctan2(m[1,0],m[0,0]))),5)
        out=shaft_pose(cv2.warpAffine(source,m,(300,360),borderValue=(185,185,185)),roi)
        self.assertLess(abs(out[1]),.05)
        same,n=refine_shaft_matrix(source,matrices[0],p[0],replace(s,strength=50))
        np.testing.assert_array_equal(same,matrices[0]);self.assertEqual(n,0)

if __name__=='__main__':unittest.main()
