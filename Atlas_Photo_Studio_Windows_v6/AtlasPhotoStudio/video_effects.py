"""Local silhouette tracking, rigid stabilization and temporally coherent matting."""
from dataclasses import dataclass,asdict,replace
from pathlib import Path
import json,math,tempfile,shutil
import numpy as np
import cv2
from scipy.ndimage import gaussian_filter1d
from PIL import Image
import imageio_ffmpeg as ffmpeg
from video_core import VideoClip
from shaft_tracking import shaft_pose,shaft_plan,refine_shaft_matrix

@dataclass
class Effects:
    stabilize:bool=True
    smart_aim:bool=False
    remove_background:bool=True
    key_color:str='#ffffff'
    background:str='#ffffff'  # 'transparent' or #RRGGBB
    tolerance:float=35
    feather:float=1.0
    strength:float=100
    smoothing:float=.25
    max_shift:float=12  # percent of image edge
    max_angle:float=20
    roi:tuple=(0,0,1,1)
    target_x:float=-1  # normalized; -1 captures the initial measured position
    target_y:float=-1
    border_crop:float=0
    edge:int=1080
    axis_lock:bool=False
    axis_roi:tuple=(.4,.4,.2,.45)
    axis_contrast:float=18
    tracking_edge:int=1080
    second_pass:bool=True  # automatic after precision shaft lock only
    second_strength:float=100
    second_smoothing:float=.12
    second_max_shift:float=3  # output pixels, not percent
    second_max_angle:float=.5
    axis_strategy:str='legacy'
    axis_reference:int=0
    axis_mask_min_score:float=.98
    render_quality:str='fast'
    second_mode:str='smooth'
    def validate(self):
        colour(self.key_color)
        if self.background!='transparent':colour(self.background)
        if not 1<=self.tolerance<=180 or not 0<=self.feather<=8:raise ValueError('Mask tolerance must be 1–180; feather 0–8 pixels.')
        if not 0<=self.strength<=100 or not 0<=self.smoothing<=2:raise ValueError('Invalid strength or smoothing.')
        if not 0<=self.max_shift<=40 or not 0<=self.max_angle<=60:raise ValueError('Maximum shift must be 0–40%; angle 0–60 degrees.')
        x,y,w,h=self.roi
        if x<0 or y<0 or w<=0 or h<=0 or x+w>1.00001 or y+h>1.00001:raise ValueError('Tracking rectangle must fit inside the video.')
        if not 0<=self.border_crop<=20:raise ValueError('Safety crop must be 0–20%.')
        if not 128<=self.edge<=2160:raise ValueError('Processing edge must be 128–2160 px.')
        if any(v!=-1 and not 0<=v<=1 for v in (self.target_x,self.target_y)):raise ValueError('Target must fit inside the frame.')
        x,y,w,h=self.axis_roi
        if not all(math.isfinite(float(v)) for v in (x,y,w,h,self.axis_contrast,self.tracking_edge)):raise ValueError('Shaft settings must be finite numbers.')
        if x<0 or y<0 or w<=0 or h<=0 or x+w>1.00001 or y+h>1.00001:raise ValueError('Shaft band must fit inside the video.')
        if not 3<=self.axis_contrast<=150 or not 512<=self.tracking_edge<=2160:raise ValueError('Shaft contrast must be 3–150; tracking edge 512–2160 px.')
        if not 0<=self.second_strength<=100 or not .02<=self.second_smoothing<=1:raise ValueError('Second-pass strength must be 0–100%; smoothing 0.02–1 second.')
        if not 0<=self.second_max_shift<=20 or not 0<=self.second_max_angle<=3:raise ValueError('Second-pass limits must be 0–20 output pixels and 0–3 degrees.')
        if not isinstance(self.second_pass,bool):raise ValueError('Second-pass toggle must be true or false.')
        if self.axis_strategy not in ('legacy','robust','reference','hybrid'):raise ValueError('Unknown axis tracking strategy.')
        if not isinstance(self.axis_reference,int) or not 0<=self.axis_reference<=5400:raise ValueError('Reference frame must be a whole number from 0–5400.')
        if not .8<=self.axis_mask_min_score<=.9999:raise ValueError('Mask correlation threshold must be 0.8–0.9999.')
        if self.render_quality not in ('fast','subpixel','cubic'):raise ValueError('Choose fast, subpixel or cubic resampling.')
        if self.second_mode not in ('smooth','lock'):raise ValueError('Choose residual smoothing or fixed vertical lock for the second pass.')

def colour(value):
    s=value.lstrip('#')
    if len(s)!=6:raise ValueError('Use a colour like #ffffff or #101010.')
    try:return tuple(int(s[i:i+2],16) for i in (0,2,4))
    except ValueError:raise ValueError('Invalid colour.') from None

def mask_frame(rgb,settings,previous=None):
    """Colour seeds + GrabCut + target-connected silhouette; holes preserve metal highlights."""
    a=np.asarray(rgb,dtype=np.uint8);h,w=a.shape[:2];key=np.array(colour(settings.key_color),np.float32)
    distance=np.linalg.norm(a.astype(np.float32)-key,axis=2)
    roi=np.zeros((h,w),np.uint8);x,y,rw,rh=settings.roi;x0,y0=int(x*w),int(y*h);x1,y1=min(w,int((x+rw)*w)),min(h,int((y+rh)*h));roi[y0:y1,x0:x1]=1
    seed=np.full((h,w),cv2.GC_BGD,np.uint8)
    seed[roi>0]=cv2.GC_PR_BGD
    seed[(distance>settings.tolerance)&(roi>0)]=cv2.GC_PR_FGD
    seed[(distance>settings.tolerance*1.8)&(roi>0)]=cv2.GC_FGD
    if previous is not None:seed[(previous>.8)&(distance>settings.tolerance*.5)&(roi>0)]=cv2.GC_PR_FGD
    seed[0,:]=seed[-1,:]=cv2.GC_BGD;seed[:,0]=seed[:,-1]=cv2.GC_BGD
    if not np.any(seed==cv2.GC_FGD):
        hard=((distance>settings.tolerance)&(roi>0)).astype(np.uint8)
    else:
        try:
            cv2.grabCut(cv2.cvtColor(a,cv2.COLOR_RGB2BGR),seed,None,np.zeros((1,65)),np.zeros((1,65)),1,cv2.GC_INIT_WITH_MASK)
            hard=np.isin(seed,[cv2.GC_FGD,cv2.GC_PR_FGD]).astype(np.uint8)
        except cv2.error:hard=((distance>settings.tolerance)&(roi>0)).astype(np.uint8)
    contours,_=cv2.findContours(hard,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    if not contours:return np.zeros((h,w),np.float32)
    # Keep the largest component in the user-selected target rectangle, fill interior reflections.
    contour=max(contours,key=cv2.contourArea);hard[:]=0;cv2.drawContours(hard,[contour],-1,1,cv2.FILLED)
    if cv2.contourArea(contour)<max(8,h*w*.0003):return np.zeros((h,w),np.float32)
    alpha=hard.astype(np.float32)
    if settings.feather:alpha=cv2.GaussianBlur(alpha,(0,0),max(.1,settings.feather))
    return alpha

def pose(alpha):
    ys,xs=np.where(alpha>.5)
    if len(xs)<12:return None
    points=np.column_stack((xs,ys)).astype(float);center=points.mean(axis=0)
    eig,vec=np.linalg.eigh(np.cov(points.T));v=vec[:,-1]
    if v[1]<0:v=-v
    angle=math.degrees(math.atan2(v[0],v[1]))
    elongation=float(eig[-1]/max(eig[0],1))
    return center,angle,elongation

def plan_transforms(poses,size,fps,s):
    valid=np.array([p is not None for p in poses]);n=len(poses)
    if not valid.any():raise ValueError('No tool found. Adjust the key colour, tolerance or tracking rectangle.')
    if (s.stabilize or s.smart_aim) and valid.mean()<.6:raise ValueError('Tool tracking was lost too often. Tighten the tracking rectangle or improve the mask.')
    indices=np.arange(n);raw=np.array([[*(p[0] if p else [np.nan,np.nan]),p[1] if p else np.nan] for p in poses])
    for j in range(3):raw[:,j]=np.interp(indices,indices[valid],raw[valid,j])
    # Axis estimates for round/short silhouettes are unreliable: do not rotate those frames.
    reliable=np.array([p is not None and p[2]>=2.0 for p in poses])
    raw[:,2]=np.clip(raw[:,2],-s.max_angle,s.max_angle)
    sigma=max(.01,s.smoothing*fps);smooth=gaussian_filter1d(raw,sigma,axis=0,mode='nearest')
    initial=raw[np.flatnonzero(valid)[0]];target=np.array([initial[0] if s.target_x<0 else s.target_x*size[0],initial[1] if s.target_y<0 else s.target_y*size[1]])
    matrices=[];limit=max(size)*s.max_shift/100;strength=s.strength/100
    for i in range(n):
        center=raw[i,:2];desired=center.copy();angle=0
        if s.smart_aim:
            desired=center+(target-center)*strength
            # Correct the current angle, not a smoothed angle which leaves the
            # fast component of physical wobble visible in the result.
            if reliable[i]:angle=raw[i,2]*strength
        elif s.stabilize:desired=center+(smooth[i,:2]-center)*strength
        theta=math.radians(angle);r=np.array([[math.cos(theta),-math.sin(theta)],[math.sin(theta),math.cos(theta)]])
        shift=np.clip(desired-center,-limit,limit);translation=center+shift-r@center
        matrices.append(np.column_stack((r,translation)).astype(np.float32))
    return matrices,valid.tolist()

def apply_transform(rgb,alpha,matrix,background,key_color):
    h,w=alpha.shape
    # Premultiplied resampling prevents bright/dark halos along the moving matte edge.
    premul=rgb.astype(np.float32)*(alpha[:,:,None])
    warped=cv2.warpAffine(premul,matrix,(w,h),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
    mask=cv2.warpAffine(alpha,matrix,(w,h),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
    straight=np.divide(warped,mask[:,:,None],out=np.zeros_like(warped),where=mask[:,:,None]>.001)
    if background=='transparent':return np.dstack((np.clip(straight,0,255).astype(np.uint8),np.clip(mask*255,0,255).astype(np.uint8)))
    bg=np.array(colour(background),np.float32);out=warped+bg*(1-mask[:,:,None]);return np.dstack((np.clip(out,0,255).astype(np.uint8),np.full((h,w),255,np.uint8)))

class ProcessedClip(VideoClip):
    def __init__(self,path,effects,source,report):
        super().__init__(path);self.effects=effects;self.original_source=source;self.effect_report=report
    def rgba_frame(self,index):
        if not hasattr(self,'alpha_proxy'):return super().frame(index).convert('RGBA')
        w,h=self.alpha_proxy_size
        with open(self.alpha_proxy,'rb') as f:f.seek(int(index)*w*h*4);data=f.read(w*h*4)
        return Image.frombytes('RGBA',(w,h),data)
    def frame(self,index):
        if not hasattr(self,'alpha_proxy'):return super().frame(index)
        w,h=self.alpha_proxy_size
        with open(self.alpha_proxy,'rb') as f:f.seek(int(index)*w*h*4);data=f.read(w*h*4)
        rgba=Image.frombytes('RGBA',(w,h),data);yy,xx=np.indices((h,w));grey=np.where((xx//12+yy//12)%2,70,45).astype(np.uint8)
        bg=Image.fromarray(np.dstack((grey,grey,grey))).convert('RGBA');bg.alpha_composite(rgba);return bg.convert('RGB')
    def close(self):
        super().close()
        if hasattr(self,'processing_cache'):self.processing_cache.cleanup()
        if hasattr(self,'first_pass'):self.first_pass.close()

def process_clip(clip,s,progress=lambda text:None):
    first=process_primary(clip,s,progress)
    if not (s.axis_lock and s.second_pass):return first
    from jitter_pass import second_pass_clip
    try:
        return second_pass_clip(first,s,progress)
    except Exception:
        first.close();raise

def process_primary(clip,s,progress=lambda text:None):
    s.validate();w,h=clip.size;scale=min(1,s.edge/max(w,h));ow=max(2,int(w*scale)//2*2);oh=max(2,int(h*scale)//2*2)
    poses=[];previous=None;axis_report=None;tracking_size=clip.proxy_size;tracker=None
    if s.axis_lock:
        ratio=min(1,s.tracking_edge/max(clip.size));tracking_size=(max(2,round(clip.size[0]*ratio)),max(2,round(clip.size[1]*ratio)))
        if s.axis_reference>=clip.count:raise ValueError('Reference frame is outside this clip.')
        if s.axis_strategy!='legacy':
            from advanced_axis import AxisTracker
            refgen=ffmpeg.read_frames(clip.path,pix_fmt='rgb24',output_params=['-vf',f'fps={clip.fps:.8f},select=eq(n\\,{s.axis_reference}),scale={tracking_size[0]}:{tracking_size[1]}','-vsync','0','-frames:v','1','-an']);next(refgen)
            try:reference=np.frombuffer(next(refgen),np.uint8).reshape(tracking_size[1],tracking_size[0],3)
            finally:refgen.close()
            tracker=AxisTracker(reference,s)
        reader=ffmpeg.read_frames(clip.path,pix_fmt='rgb24',output_params=['-vf',f'fps={clip.fps:.8f},scale={tracking_size[0]}:{tracking_size[1]}','-an']);next(reader)
        try:
            for i,data in enumerate(reader):
                if i>=clip.count:break
                rgb=np.frombuffer(data,np.uint8).reshape(tracking_size[1],tracking_size[0],3)
                poses.append(tracker.measure(rgb) if tracker else shaft_pose(rgb,s.axis_roi,s.axis_contrast))
                if i%max(1,round(clip.fps))==0:progress(f'Precision shaft tracking: {i+1}/{clip.count} frames')
        finally:reader.close()
        if len(poses)!=clip.count:raise ValueError('Frame count changed during shaft tracking.')
        matrices,valid,axis_report=shaft_plan(poses,tracking_size,clip.fps,s)
        if tracker:axis_report['advanced_tracking']=tracker.report()
    else:
        # The legacy silhouette method remains available for non-shaft products.
        for i in range(clip.count):
            rgb=np.asarray(clip.frame(i).convert('RGB'));alpha=mask_frame(rgb,s,previous);previous=alpha;poses.append(pose(alpha))
            if i%max(1,round(clip.fps))==0:progress(f'Tracking tool: {i+1}/{clip.count} frames')
        matrices,valid=plan_transforms(poses,clip.proxy_size,clip.fps,s)
    cache=tempfile.TemporaryDirectory(prefix='atlas-processed-');transparent=s.remove_background and s.background=='transparent';path=Path(cache.name)/('processed.mov' if transparent else 'processed.mp4')
    codec='prores_ks' if transparent else 'libx264';pix='yuva444p10le' if transparent else 'yuv444p' if s.render_quality!='fast' else 'yuv420p'
    params=['-profile:v','4','-alpha_bits','16'] if transparent else ['-crf','10' if s.render_quality!='fast' else '16','-movflags','+faststart']
    gen=ffmpeg.read_frames(clip.path,pix_fmt='rgb24',output_params=['-vf',f'fps={clip.fps:.8f},scale={ow}:{oh}','-an']);next(gen)
    writer=ffmpeg.write_frames(str(path),(ow,oh),pix_fmt_in='rgba',pix_fmt_out=pix,fps=clip.fps,codec=codec,macro_block_size=1,output_params=params);writer.send(None)
    previous=None;count=0;refined_frames=0
    proxy_scale=min(1,256/max(ow,oh));proxy_size=(max(2,round(ow*proxy_scale)),max(2,round(oh*proxy_scale)))
    alpha_proxy=Path(cache.name)/'alpha.rgba';proxy_file=alpha_proxy.open('wb') if transparent else None
    try:
        for i,data in enumerate(gen):
            if i>=clip.count:break
            rgb=np.frombuffer(data,np.uint8).reshape(oh,ow,3)
            if s.remove_background:
                small=cv2.resize(rgb,clip.proxy_size);alpha=mask_frame(small,s,previous)
                if pose(alpha) is None:raise ValueError(f'Tool mask lost at frame {i}. Adjust tracking rectangle, key colour or tolerance; no processed video was kept.')
                previous=alpha;alpha=cv2.resize(alpha,(ow,oh),interpolation=cv2.INTER_LINEAR)
            m=matrices[i].copy();sx,sy=ow/tracking_size[0],oh/tracking_size[1]
            m[0,1]*=sx/sy;m[1,0]*=sy/sx;m[0,2]*=sx;m[1,2]*=sy
            if s.axis_lock and poses[i] is not None and s.axis_strategy=='legacy':
                m,iterations=refine_shaft_matrix(rgb,m,poses[i][0]*[sx,sy],s)
                refined_frames+=int(iterations>0)
            if s.remove_background:
                if s.render_quality!='fast':
                    from subpixel import precision_warp
                    source_rgba=np.dstack((rgb,np.rint(alpha*255).astype(np.uint8)))
                    rgba=precision_warp(source_rgba,m,True,s.render_quality)
                    if s.background!='transparent':
                        a=rgba[:,:,3:4].astype(float)/255;rgba[:,:,:3]=np.rint(rgba[:,:,:3]*a+np.array(colour(s.background))*(1-a)).astype(np.uint8);rgba[:,:,3]=255
                else:rgba=apply_transform(rgb,alpha,m,s.background,s.key_color)
            else:
                # Reflection fills exposed edges when retaining the original background.
                if s.render_quality!='fast':
                    from subpixel import precision_warp
                    rgb=precision_warp(rgb,m,quality=s.render_quality)
                else:rgb=cv2.warpAffine(rgb,m,(ow,oh),borderMode=cv2.BORDER_REFLECT_101)
                rgba=np.dstack((rgb,np.full((oh,ow),255,np.uint8)))
            border=round(min(ow,oh)*s.border_crop/100)
            if border:rgba=cv2.resize(rgba[border:oh-border,border:ow-border],(ow,oh),interpolation=cv2.INTER_LINEAR)
            if proxy_file:proxy_file.write(cv2.resize(rgba,proxy_size).tobytes())
            writer.send(rgba.tobytes());count+=1
            if i%max(1,round(clip.fps))==0:progress(f'Processing video: {i+1}/{clip.count} frames')
        writer.close();gen.close()
        if proxy_file:proxy_file.close()
        if count!=clip.count:raise ValueError('Frame count changed during processing. Reopen the original video.')
        actual,_=ffmpeg.count_frames_and_secs(str(path))
        if actual!=count:raise ValueError('Processed frame verification failed.')
        report={'settings':asdict(s),'tracked_frames':sum(valid),'total_frames':count,'interpolated_frames':len(valid)-sum(valid),'size':[ow,oh]}
        if axis_report:
            axis_report['render_refined_frames']=refined_frames;report['shaft_lock']=axis_report
        processed=ProcessedClip(path,s,clip.path,report);processed.processing_cache=cache
        if transparent:processed.alpha_proxy=str(alpha_proxy);processed.alpha_proxy_size=proxy_size
        if processed.count!=clip.count:processed.close();raise ValueError('Working frame grid changed during processing.')
        return processed
    except Exception:
        gen.close();writer.close()
        if proxy_file:proxy_file.close()
        cache.cleanup();raise
