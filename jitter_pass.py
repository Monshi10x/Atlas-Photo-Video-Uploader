"""A separate residual-jitter pass on a completed, encoded first-pass file."""
from pathlib import Path
from dataclasses import asdict,replace
import copy,hashlib,math,tempfile
import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d
import imageio_ffmpeg as ffmpeg
from shaft_tracking import shaft_pose


def residual_plan(poses,size,fps,s):
    valid=np.array([p is not None for p in poses]);n=len(poses)
    if n<4 or valid.mean()<.9:raise ValueError('Second pass lost the straight shaft. Adjust the shaft band or disable the second pass to keep the first-pass result.')
    missing=np.flatnonzero(~valid);gaps=np.split(missing,np.where(np.diff(missing)>1)[0]+1)
    if any(len(g)>max(2,round(fps*.15)) for g in gaps):raise ValueError('Second-pass tracking gap is too long. Adjust the shaft band or disable the second pass.')
    raw=np.array([[*(p[0] if p else [np.nan,np.nan]),p[1] if p else np.nan] for p in poses],float)
    for j in range(3):raw[:,j]=np.interp(np.arange(n),np.flatnonzero(valid),raw[valid,j])
    smooth=gaussian_filter1d(raw,max(.01,s.second_smoothing*fps),axis=0,mode='reflect')
    factor=s.second_strength/100
    if s.second_mode=='lock':
        target=np.median(raw[:,:2],axis=0);desired=np.column_stack((np.tile(target,(n,1)),np.zeros(n)))
        delta=(desired-raw)*factor
    else:delta=(smooth-raw)*factor
    shifts=np.clip(delta[:,:2],-s.second_max_shift,s.second_max_shift)
    # Pose angle is measured clockwise from the downward vertical. Positive
    # matrix rotation removes a positive lean, hence raw minus desired angle.
    turns=np.clip(-delta[:,2],-s.second_max_angle,s.second_max_angle)
    matrices=[]
    for row,shift,angle in zip(raw,shifts,turns):
        theta=math.radians(angle);r=np.array([[math.cos(theta),-math.sin(theta)],[math.sin(theta),math.cos(theta)]])
        matrices.append(np.column_stack((r,row[:2]+shift-r@row[:2])).astype(np.float32))
    limited=np.any(np.abs(delta[:,:2])>s.second_max_shift,axis=1)|(np.abs(delta[:,2])>s.second_max_angle)
    report={'input':'completed first-pass rendered file','method':'subpixel shaft residuals against a Gaussian-smoothed trajectory',
            'strength_percent':s.second_strength,'smoothing_seconds':s.second_smoothing,
            'max_shift_output_pixels':s.second_max_shift,'max_angle_degrees':s.second_max_angle,
            'tracked_frames':int(valid.sum()),'interpolated_frames':int((~valid).sum()),'safety_limited_frames':int(limited.sum()),
            'measured_input_axis_drift_px':float(np.ptp(raw[:,0])),
            'measured_input_angle_range_deg':[float(raw[:,2].min()),float(raw[:,2].max())],
            'max_applied_shift_px':float(np.max(np.abs(shifts))),
            'max_applied_angle_deg':float(np.max(np.abs(turns))),
            'tracking_size':list(size),'corrections':'sideways shaft-axis jitter and tilt; axial height is unobservable in this band',
            'boundary':'reflect; find loop points after both passes','mode':s.second_mode,'axis_strategy':s.axis_strategy}
    return matrices,report


def processed_band(clip,s):
    # First-pass safety crop changes the measurement coordinates. It must not
    # be applied again to the second-pass image.
    w,h=clip.size;b=round(min(w,h)*s.border_crop/100);x,y,rw,rh=s.axis_roi
    band=((x*w-b)/(w-2*b),(y*h-b)/(h-2*b),rw*w/(w-2*b),rh*h/(h-2*b))
    if min(band)<0 or band[0]+band[2]>1 or band[1]+band[3]>1:raise ValueError('The safety crop cuts into the shaft band. Reduce safety crop or adjust the band before the second pass.')
    return band


def second_pass_clip(first,s,progress=lambda text:None):
    """Read first.path, never original_source. Result owns first until closed."""
    from video_effects import ProcessedClip,apply_transform
    s.validate()
    if first.effect_report.get('second_pass'):raise ValueError('Second pass is already applied. Reapply shaft lock to start a fresh two-pass process.')
    if not first.effects.axis_lock:raise ValueError('Second-pass jitter removal needs a precision shaft-lock result and a straight-shank band.')
    source=Path(first.path);stat=source.stat()
    if (stat.st_size,stat.st_mtime_ns)!=first.source_stamp:raise ValueError('First-pass video changed; reprocess it before the second pass.')
    size=first.size;w,h=size;band=processed_band(first,s);transparent=first.effects.remove_background and first.effects.background=='transparent'
    poses=[];digest=hashlib.sha256()
    with source.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):digest.update(block)
    # Decode the completed first-pass file at its rendered resolution. No
    # original transforms, background masks, crops or grade are rerun.
    def reader():
        gen=ffmpeg.read_frames(str(source),pix_fmt='rgba',bits_per_pixel=32,output_params=['-vsync','0','-an']);next(gen);return gen
    tracker=None
    if s.axis_strategy!='legacy':
        from advanced_axis import AxisTracker
        refgen=reader()
        try:
            for j,data in enumerate(refgen):
                if j==s.axis_reference:
                    rgba=np.frombuffer(data,np.uint8).reshape(h,w,4);reference=np.repeat(rgba[:,:,3:4],3,axis=2) if transparent else rgba[:,:,:3]
                    tracker=AxisTracker(reference,replace(s,axis_roi=band,axis_contrast=128*math.sqrt(3) if transparent else s.axis_contrast));break
        finally:refgen.close()
        if tracker is None:raise ValueError('Second-pass reference frame is outside the rendered clip.')
    gen=reader()
    try:
        for i,data in enumerate(gen):
            rgba=np.frombuffer(data,np.uint8).reshape(h,w,4)
            if transparent:
                # Measuring the alpha silhouette avoids hidden RGB colours and
                # checkerboards in transparent output.
                rgb=np.repeat(rgba[:,:,3:4],3,axis=2)
                poses.append(tracker.measure(rgb) if tracker else shaft_pose(rgb,band,128*math.sqrt(3)))
            else:poses.append(tracker.measure(rgba[:,:,:3]) if tracker else shaft_pose(rgba[:,:,:3],band,s.axis_contrast))
            if i%max(1,round(first.fps))==0:progress(f'Second pass — measuring rendered footage: {i+1}/{first.count}')
    finally:gen.close()
    if len(poses)!=first.count:raise ValueError('First-pass frame count changed before jitter removal.')
    matrices,report=residual_plan(poses,size,first.fps,s);report['tracking_band']=list(band);report['input_sha256']=digest.hexdigest()
    if tracker:report['advanced_tracking']=tracker.report()
    cache=tempfile.TemporaryDirectory(prefix='atlas-jitter-');path=Path(cache.name)/('second-pass.mov' if transparent else 'second-pass.mp4')
    alpha_file=None;gen=None;writer=None
    try:
        gen=reader();writer=ffmpeg.write_frames(str(path),size,pix_fmt_in='rgba',pix_fmt_out='yuva444p10le' if transparent else 'yuv444p' if s.render_quality!='fast' else 'yuv420p',fps=first.fps,codec='prores_ks' if transparent else 'libx264',macro_block_size=1,output_params=['-profile:v','4','-alpha_bits','16'] if transparent else ['-crf','10' if s.render_quality!='fast' else '14','-movflags','+faststart']);writer.send(None)
        ps=min(1,256/max(size));proxy_size=tuple(max(2,round(v*ps)) for v in size);alpha_path=Path(cache.name)/'alpha.rgba'
        if transparent:alpha_file=alpha_path.open('wb')
        count=0
        for i,data in enumerate(gen):
            if i>=first.count:raise ValueError('Unexpected extra frame in the second pass.')
            rgba=np.frombuffer(data,np.uint8).reshape(h,w,4)
            if s.render_quality!='fast':
                from subpixel import precision_warp
                out=precision_warp(rgba,matrices[i],transparent,s.render_quality)
            elif transparent:out=apply_transform(rgba[:,:,:3],rgba[:,:,3].astype(np.float32)/255,matrices[i],'transparent',s.key_color)
            else:out=cv2.warpAffine(rgba,matrices[i],size,borderMode=cv2.BORDER_REFLECT_101)
            if alpha_file:alpha_file.write(cv2.resize(out,proxy_size).tobytes())
            writer.send(np.ascontiguousarray(out).tobytes());count+=1
            if i%max(1,round(first.fps))==0:progress(f'Second pass — removing residual jitter: {i+1}/{first.count}')
        writer.close();gen.close()
        if alpha_file:alpha_file.close()
        actual,_=ffmpeg.count_frames_and_secs(str(path))
        if count!=first.count or actual!=first.count:raise ValueError('Second-pass frame verification failed; no result was kept.')
        stat=source.stat()
        if (stat.st_size,stat.st_mtime_ns)!=first.source_stamp:raise ValueError('First-pass video changed during jitter removal.')
        full_report=copy.deepcopy(first.effect_report);full_report['second_pass']=report;full_report['settings']=asdict(s)
        result=ProcessedClip(path,s,first.original_source,full_report);result.processing_cache=cache
        if result.count!=first.count or result.size!=size:
            result.close();raise ValueError('Second-pass working frame grid changed.')
        if transparent:result.alpha_proxy=str(alpha_path);result.alpha_proxy_size=proxy_size
        result.first_pass=first
        return result
    except Exception:
        if gen:gen.close()
        if writer:writer.close()
        if alpha_file:alpha_file.close()
        cache.cleanup();raise
