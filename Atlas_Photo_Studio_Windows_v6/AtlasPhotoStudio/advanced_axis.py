"""Confidence-gated geometry and drift-free reference-mask registration.

Only the selected stable shank is modelled. Rotating flutes are deliberately
excluded: forcing their changing silhouette onto one template changes the spin.
"""
import math
import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d


STRATEGIES={'legacy':'Legacy shaft edges','robust':'Robust multi-band edges',
            'reference':'Reference geometry mask','hybrid':'Hybrid edges + reference mask'}


def geometry(rgb,roi,contrast):
    h,w=rgb.shape[:2];x,y,rw,rh=roi
    left,top,right,bottom=round(x*w),round(y*h),round((x+rw)*w),round((y+rh)*h)
    patch=np.asarray(rgb[top:bottom,left:right],np.float32)
    if patch.shape[0]<24 or patch.shape[1]<12:return None
    side=max(2,patch.shape[1]//8)
    background=np.median(np.concatenate((patch[:,:side],patch[:,-side:]),axis=1),axis=1)
    distance=gaussian_filter1d(np.linalg.norm(patch-background[:,None,:],axis=2),.55,axis=1)
    rows=[]
    for iy,v in enumerate(distance):
        centres=[];widths=[]
        for level in (contrast*.85,contrast,contrast*1.15):
            on=np.flatnonzero(v>level)
            if len(on)<3:continue
            l,r=int(on[0]),int(on[-1])
            if l<2 or r>=len(v)-2 or r-l>len(v)*.7:continue
            if np.count_nonzero(v[l:r+1]>level)<(r-l+1)*.45:continue
            lo=l-1+(level-v[l-1])/max(float(v[l]-v[l-1]),.001)
            hi=r+(v[r]-level)/max(float(v[r]-v[r+1]),.001)
            centres.append((lo+hi)/2);widths.append(hi-lo)
        if centres:rows.append((iy,float(np.median(centres)),float(np.median(widths))))
    if len(rows)<max(20,.7*patch.shape[0]):return None
    rows=np.asarray(rows);width=rows[:,2];med=np.median(width);mad=max(.5,np.median(abs(width-med))*1.4826)
    rows=rows[abs(width-med)<=max(3,4*mad)]
    if len(rows)<max(20,.65*patch.shape[0]):return None
    anchor_y=(patch.shape[0]-1)/2;Y=rows[:,0]-anchor_y;X=rows[:,1]
    A=np.column_stack((Y,np.ones(len(Y))));coef=np.linalg.lstsq(A,X,rcond=None)[0]
    for _ in range(6):
        residual=X-A@coef;scale=max(.08,np.median(abs(residual-np.median(residual)))*1.4826)
        weight=np.minimum(1,2*scale/np.maximum(abs(residual),1e-8));root=np.sqrt(weight)
        coef=np.linalg.lstsq(A*root[:,None],X*root,rcond=None)[0]
    error=float(np.quantile(abs(X-A@coef),.8))
    if error>max(1.5,w*.002):return None
    # Independently fit thirds; an isolated blob/transition cannot silently
    # dominate a very long lever arm. Low consensus reduces hybrid confidence.
    estimates=[]
    for start,end in ((0,1/3),(1/3,2/3),(2/3,1)):
        selected=(rows[:,0]>=start*patch.shape[0])&(rows[:,0]<end*patch.shape[0])
        if selected.sum()>=8:
            q=np.linalg.lstsq(A[selected],X[selected],rcond=None)[0];estimates.append(q)
    spread=float(np.std([q[0] for q in estimates])) if estimates else 1
    confidence=float(np.clip((len(rows)/patch.shape[0])/(1+error+spread*30),0,1))
    # Fill the geometric silhouette rather than correlating rotating reflections.
    yy=np.arange(patch.shape[0]);centers=np.interp(yy,rows[:,0],rows[:,1]);widths=np.interp(yy,rows[:,0],rows[:,2]);xx=np.arange(patch.shape[1])[None,:]
    mask=np.minimum(np.clip(xx-(centers-widths/2)[:,None]+.5,0,1),np.clip((centers+widths/2)[:,None]-xx+.5,0,1)).astype(np.float32)
    mask=cv2.GaussianBlur(mask,(0,0),.8)
    pose=(np.array([coef[1]+left,anchor_y+top]),math.degrees(math.atan(coef[0])),confidence)
    return pose,mask,(left,top),rows,error


class AxisTracker:
    def __init__(self,reference,settings):
        self.s=settings;self.counts={'edge_frames':0,'mask_frames':0,'fallback_frames':0,'rejected_frames':0}
        self.reference=geometry(reference,settings.axis_roi,settings.axis_contrast)
        if self.reference is None:raise ValueError('Reference frame has no reliable straight shank. Select a longer band or a different reference frame.')
        p,mask,origin,_,_=self.reference;self.origin=np.array(origin);self.anchor=p[0]-self.origin
        theta=math.radians(p[1]);r=np.array([[math.cos(theta),-math.sin(theta)],[math.sin(theta),math.cos(theta)]],np.float32)
        transform=np.column_stack((r,self.anchor-r@self.anchor)).astype(np.float32)
        # Ideal mask is the captured source mask rigidly made vertical.
        self.template=cv2.warpAffine(mask,transform,(mask.shape[1],mask.shape[0]),flags=cv2.INTER_CUBIC,borderMode=cv2.BORDER_REPLICATE)
        self.validity=np.zeros(mask.shape,np.uint8);margin=max(5,round(mask.shape[0]*.12));self.validity[margin:-margin,2:-2]=255
        self.last_quality=0;self.last_pose=None
    def measure(self,rgb):
        g=geometry(rgb,self.s.axis_roi,self.s.axis_contrast)
        if g is None:self.counts['rejected_frames']+=1;return None
        edge,mask,origin,_,error=g;self.counts['edge_frames']+=1
        if self.s.axis_strategy=='robust':self.last_pose=edge;return edge
        center,angle,confidence=edge;theta=math.radians(-angle)
        r=np.array([[math.cos(theta),-math.sin(theta)],[math.sin(theta),math.cos(theta)]],np.float32)
        initial=np.column_stack((r,center-np.array(origin)-r@self.anchor)).astype(np.float32)
        matched=None
        try:
            quality,warp=cv2.findTransformECC(self.template,mask,initial,cv2.MOTION_EUCLIDEAN,(cv2.TERM_CRITERIA_COUNT|cv2.TERM_CRITERIA_EPS,60,1e-7),self.validity,3)
            point=warp[:,:2]@self.anchor+warp[:,2]+origin
            tilt=-math.degrees(math.atan2(warp[1,0],warp[0,0]));self.last_quality=float(quality)
            point[0]+=math.tan(math.radians(tilt))*(center[1]-point[1])
            # Axial translation is unobservable for a straight shank. Ignore
            # ECC's Y estimate, and constrain geometry to the measured band.
            if quality>=self.s.axis_mask_min_score and abs(point[0]-center[0])<=max(1.5,mask.shape[1]*.025) and abs(tilt-angle)<=.75:
                matched=(np.array([point[0],center[1]]),tilt,float(quality))
        except cv2.error:self.last_quality=0
        if matched is None:
            if self.s.axis_strategy=='reference':self.counts['rejected_frames']+=1;return None
            self.counts['fallback_frames']+=1;self.last_pose=edge;return edge
        self.counts['mask_frames']+=1
        if self.s.axis_strategy=='reference':self.last_pose=matched;return matched
        # Combine two independently fitted geometric estimates. Confidence
        # shifts weight towards the mask when multi-band edges disagree.
        weight=.5+.25*(1-confidence)
        pose=(center*(1-weight)+matched[0]*weight,angle*(1-weight)+matched[1]*weight,max(confidence,matched[2]))
        self.last_pose=pose;return pose
    def report(self):
        return {'strategy':self.s.axis_strategy,'reference_frame':self.s.axis_reference,
                'reference_type':'captured shank geometry rigidly made vertical; fixed reference for every frame',
                'registration':'ECC Euclidean; no scale/shear and no cumulative frame-to-frame drift',
                'minimum_mask_score':self.s.axis_mask_min_score,**self.counts}


