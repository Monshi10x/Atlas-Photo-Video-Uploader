"""Subpixel shank centre-line tracking, independent of rotating cutting flutes.

The tracking band must contain a straight, contrasting shaft with background on
both sides. Rigid transforms preserve the tool's shape and deliberate spin.
"""
import math
import cv2
import numpy as np


def shaft_pose(rgb, roi, contrast=18):
    h,w=rgb.shape[:2];x,y,rw,rh=roi
    left,top,right,bottom=round(x*w),round(y*h),round((x+rw)*w),round((y+rh)*h)
    p=np.asarray(rgb[top:bottom,left:right],np.float32)
    if p.shape[0]<12 or p.shape[1]<10:return None
    side=max(2,p.shape[1]//8)
    bg=np.median(np.concatenate((p[:,:side],p[:,-side:]),axis=1),axis=1)
    distance=np.linalg.norm(p-bg[:,None,:],axis=2);points=[]
    for row,v in enumerate(distance):
        on=np.flatnonzero(v>contrast)
        if len(on)<3:continue
        l,r=int(on[0]),int(on[-1])
        # Reject touching edges, wide background changes and fragmented rows.
        if l<1 or r>=len(v)-1 or r-l>len(v)*.7:continue
        if np.count_nonzero(v[l:r+1]>contrast)<(r-l+1)*.45:continue
        lo=l-1+(contrast-v[l-1])/max(float(v[l]-v[l-1]),.001)
        hi=r+(v[r]-contrast)/max(float(v[r]-v[r+1]),.001)
        points.append([left+(lo+hi)/2,top+row])
    if len(points)<max(12,.6*(bottom-top)):return None
    points=np.asarray(points,np.float32)
    vx,vy,cx,cy=cv2.fitLine(points,cv2.DIST_HUBER,0,.001,.001).ravel()
    if abs(vy)<.5:return None
    slope=float(vx/vy);anchor_y=top+(bottom-top-1)/2
    anchor_x=float(cx+(anchor_y-cy)*slope)
    residual=np.abs(points[:,0]-(anchor_x+(points[:,1]-anchor_y)*slope))
    if np.quantile(residual,.8)>max(1.5,w*.002):return None
    return np.array([anchor_x,anchor_y]),math.degrees(math.atan(slope)),float(len(points)/(bottom-top))


def shaft_plan(poses,size,fps,settings):
    valid=np.array([p is not None for p in poses]);n=len(poses)
    if not n or valid.mean()<.9:
        raise ValueError('Precision shaft tracking needs at least 90% reliable frames. Select a longer straight shank band, with background on both sides; adjust contrast.')
    missing=np.flatnonzero(~valid)
    gaps=np.split(missing,np.where(np.diff(missing)>1)[0]+1)
    if any(len(g)>max(2,round(fps*.15)) for g in gaps):
        raise ValueError('Shaft tracking was lost for over 0.15 seconds. Adjust the tracking band; no video was kept.')
    raw=np.array([[*(p[0] if p else [np.nan,np.nan]),p[1] if p else np.nan] for p in poses])
    for j in range(3):raw[:,j]=np.interp(np.arange(n),np.flatnonzero(valid),raw[valid,j])
    ref=getattr(settings,'axis_reference',0)
    if not 0<=ref<n:raise ValueError('Reference frame is outside this clip.')
    initial=raw[ref,:2]
    target=np.array([initial[0] if settings.target_x<0 else settings.target_x*size[0],initial[1] if settings.target_y<0 else settings.target_y*size[1]])
    limit=max(size)*settings.max_shift/100;strength=settings.strength/100
    matrices=[];limited=0
    for row in raw:
        center=row[:2];angle=np.clip(row[2],-settings.max_angle,settings.max_angle)*strength
        shift=np.clip((target-center)*strength,-limit,limit)
        limited+=int(abs(row[2])>settings.max_angle or np.any(np.abs((target-center)*strength)>limit))
        theta=math.radians(angle);r=np.array([[math.cos(theta),-math.sin(theta)],[math.sin(theta),math.cos(theta)]])
        matrices.append(np.column_stack((r,center+shift-r@center)).astype(np.float32))
    report={'method':'straight-shaft subpixel edges + robust row centre line',
            'band':list(settings.axis_roi),'tracking_size':list(size),
            'input_angle_range_deg':[float(raw[:,2].min()),float(raw[:,2].max())],
            'input_axis_drift_px':float(np.ptp(raw[:,0])),
            'safety_limited_frames':limited,'interpolated_frames':int((~valid).sum()),
            'vertical_position':'fixed band anchor; no scale, depth or tip-height correction'}
    return matrices,valid.tolist(),report


def refine_shaft_matrix(rgb,matrix,measured_center,settings):
    """Reduce subpixel edge-resampling residuals in the actual rendered pixels.

    Only full-strength locks are refined; partial correction and safety bounds
    retain their requested meaning. Background removal follows this geometry.
    """
    if settings.strength!=100:return matrix,0
    h,w=rgb.shape[:2];center=np.asarray(measured_center);target=matrix[:,:2]@center+matrix[:,2]
    limit=max(w,h)*settings.max_shift/100;refined=matrix.copy();iterations=0
    for _ in range(2):
        warped=cv2.warpAffine(rgb,refined,(w,h),borderMode=cv2.BORDER_REFLECT_101)
        p=shaft_pose(warped,settings.axis_roi,settings.axis_contrast)
        if p is None:break
        angle=float(math.degrees(math.atan2(refined[1,0],refined[0,0])))+p[1]
        if abs(angle)>settings.max_angle:break
        theta=math.radians(p[1]);r=np.array([[math.cos(theta),-math.sin(theta)],[math.sin(theta),math.cos(theta)]])
        correction=np.vstack((np.column_stack((r,target-r@p[0])),[0,0,1]))
        candidate=(correction@np.vstack((refined,[0,0,1])))[:2].astype(np.float32)
        if np.any(np.abs(candidate[:,:2]@center+candidate[:,2]-center)>limit+.001):break
        refined=candidate;iterations+=1
    return refined,iterations
