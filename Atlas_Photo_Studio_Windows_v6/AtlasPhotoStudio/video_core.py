"""Local video analysis and deterministic, frame-exclusive loop exports."""
from __future__ import annotations
import json, math, os, shutil, subprocess, tempfile
from pathlib import Path
from dataclasses import dataclass
import numpy as np
from PIL import Image
import imageio_ffmpeg as ffmpeg

@dataclass
class LoopCandidate:
    start:int
    end:int  # Matching return frame; NOT included in the export.
    seconds:float
    error:float

class VideoClip:
    def __init__(self,path,progress=lambda text:None):
        self.path=str(Path(path).resolve());stat=Path(self.path).stat();self.source_stamp=(stat.st_size,stat.st_mtime_ns);self.cache=tempfile.TemporaryDirectory(prefix='atlas-video-');self.closed=False
        self.features=[];self.count=0
        try:
            g=ffmpeg.read_frames(self.path);meta=next(g);g.close()
            self.source_fps=float(meta['fps']);self.duration=float(meta['duration']);self.size=tuple(meta['size'])
            if not .5<=self.duration<=90:raise ValueError('Use a product clip between 0.5 and 90 seconds.')
            if not 1<=self.source_fps<=120:raise ValueError('Unsupported frame rate. Convert to a normal 24/25/30/60 fps clip first.')
            # All preview/analysis/export indices use this SAME constant-frame-rate grid.
            self.fps=min(self.source_fps,60.0)
            if self.size[0]<2 or self.size[1]<2:raise ValueError('Invalid video dimensions.')
            ratio=min(1,256/max(self.size));self.proxy_size=(max(2,round(self.size[0]*ratio)),max(2,round(self.size[1]*ratio)))
            self.frame_bytes=self.proxy_size[0]*self.proxy_size[1]*3
            self.raw=Path(self.cache.name)/'frames.rgb'
            gen=ffmpeg.read_frames(self.path,pix_fmt='rgb24',output_params=['-vf',f'fps={self.fps:.8f},scale={self.proxy_size[0]}:{self.proxy_size[1]}','-an'])
            next(gen)
            try:
                with self.raw.open('wb') as out:
                    for data in gen:
                        if self.count>=math.ceil(91*self.fps):raise ValueError('Decoded clip exceeded the 90-second limit.')
                        out.write(data)
                        im=Image.frombytes('RGB',self.proxy_size,data).resize((40,40),Image.Resampling.BILINEAR).convert('L')
                        a=np.asarray(im,dtype=np.float32)/255
                        gy,gx=np.gradient(a)
                        # Gradients emphasize tool detail rather than large white backgrounds.
                        feature=np.concatenate(((a-a.mean()).ravel()*.35,gx.ravel()*2,gy.ravel()*2))
                        self.features.append(feature);self.count+=1
                        if self.count%max(1,round(self.fps))==0:progress(f'Preparing video: {self.count/self.fps:.0f} / {self.duration:.0f} seconds')
            finally:gen.close()
            if self.count<4:raise ValueError('Not enough decodable frames.')
            self.features=np.asarray(self.features,dtype=np.float32)
            stat=Path(self.path).stat()
            if (stat.st_size,stat.st_mtime_ns)!=self.source_stamp:raise ValueError('Source video changed during analysis. Open it again.')
            self.duration=self.count/self.fps
            self.motion=float(np.sqrt(np.mean(np.diff(self.features,axis=0)**2)))
        except Exception:
            self.cache.cleanup();raise
    def frame(self,index):
        if not 0<=int(index)<self.count:raise ValueError('Frame is outside this video.')
        with self.raw.open('rb') as f:f.seek(int(index)*self.frame_bytes);data=f.read(self.frame_bytes)
        return Image.frombytes('RGB',self.proxy_size,data)
    def compare(self,start,end):
        self.validate_bounds(start,end)
        a=self.features[start];b=self.features[end]
        return float(np.sqrt(np.mean((a-b)**2)))
    def validate_bounds(self,start,end):
        if not 0<=int(start)<int(end)<self.count:raise ValueError(f'Use start < matching return frame, within 0–{self.count-1}.')
        if end-start<2:raise ValueError('Select at least two output frames.')
    def find_loops(self,target=7,tolerance=1.5,start_hint=None):
        if not .1<float(target)<=self.duration:raise ValueError('Target duration must fit inside the clip.')
        if not 0<=float(tolerance)<=min(15,self.duration):raise ValueError('Search tolerance must be 0–15 seconds.')
        if self.motion<.00001:raise ValueError('The clip appears static. No reliable rotating loop can be detected.')
        low=max(2,round((target-tolerance)*self.fps));high=min(self.count-1,round((target+tolerance)*self.fps));raw=[]
        velocity=np.diff(self.features,axis=0)
        energy=np.concatenate(([0.0],np.cumsum(np.mean(velocity*velocity,axis=1))))
        for lag in range(low,high+1):
            delta=self.features[lag:]-self.features[:-lag]
            err=np.mean(delta*delta,axis=1)
            # A five-frame neighborhood rejects coincidental single-frame matches.
            n=len(err);kernel=np.ones(min(5,n),dtype=np.float32)
            smoothed=np.convolve(err,kernel,mode='same')/np.convolve(np.ones(n),kernel,mode='same')
            # Penalize an abrupt change of angular velocity at the join.
            if n>1:
                vm=np.mean((velocity[lag:]-velocity[:-lag])**2,axis=1)
                smoothed[:-1]+=vm*.3
            segment_motion=(energy[lag:]-energy[:-lag])/lag
            smoothed[segment_motion<max(self.motion*self.motion*.15,1e-10)]=np.inf
            if start_hint is not None:
                starts=[max(0,min(n-1,int(start_hint)))]
            else:starts=np.argsort(smoothed)[:3]
            for a in starts:
                score=float(smoothed[a])
                if not np.isfinite(score):continue
                raw.append((score,int(a),int(a+lag)))
        result=[]
        for score,a,b in sorted(raw,key=lambda c:(c[0],abs((c[2]-c[1])/self.fps-target),c[1])):
            if any(abs(a-c.start)<self.fps*.5 and abs(b-c.end)<self.fps*.5 for c in result):continue
            result.append(LoopCandidate(a,b,(b-a)/self.fps,math.sqrt(score)))
            if len(result)>=8:break
        if not result:raise ValueError('No candidate found. Widen the duration search or use a longer clip.')
        return result
    def close(self):
        if not self.closed:self.cache.cleanup();self.closed=True

def export_loop(clip,start,end,destination,crop=None,edge=1080,logo_path='',logo_width=18,logo_x=0,logo_y=0,opacity=100,crf=18):
    clip.validate_bounds(start,end);destination=Path(destination)
    transparent=bool(getattr(clip,'effects',None) and clip.effects.remove_background and clip.effects.background=='transparent')
    if transparent and destination.suffix.lower()!='.mov':raise ValueError('Transparent video must be saved as .mov (ProRes 4444).')
    stat=Path(clip.path).stat()
    if (stat.st_size,stat.st_mtime_ns)!=clip.source_stamp:raise ValueError('Source video changed after analysis. Open it again before exporting.')
    if destination.resolve()==Path(clip.path).resolve():raise ValueError('Choose a new file; the source video cannot be overwritten.')
    if destination.exists():raise ValueError('That output file already exists. Choose another filename.')
    w,h=clip.size
    if crop is None:crop=(0,0,w,h)
    x,y,cw,ch=map(int,crop)
    if x<0 or y<0 or cw<2 or ch<2 or x+cw>w or y+ch>h:raise ValueError('Spatial crop must fit inside the original video.')
    if not 128<=int(edge)<=3840:raise ValueError('Output edge must be 128–3840 px.')
    scale=min(1,int(edge)/max(cw,ch));ow=max(2,int(cw*scale)//2*2);oh=max(2,int(ch*scale)//2*2)
    if not 0<=float(opacity)<=100 or not 1<=float(logo_width)<=95:raise ValueError('Invalid logo size or opacity.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
    with tempfile.TemporaryDirectory(prefix='atlas-loop-export-') as tmp:
        partial=Path(tmp)/'encoded.mp4'
        cmd=[ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-i',clip.path]
        vf=f'fps={clip.fps:.8f},trim=start_frame={int(start)}:end_frame={int(end)},setpts=PTS-STARTPTS,crop={cw}:{ch}:{x}:{y}:exact=1,scale={ow}:{oh},setsar=1'
        if logo_path:
            from core import load_image
            logo=load_image(logo_path);box=logo.getbbox()
            if not box:raise ValueError('Logo is completely transparent.')
            logo=logo.crop(box);lw=max(1,round(ow*float(logo_width)/100));lh=max(1,round(logo.height*lw/logo.width))
            if lh>oh:lw=max(1,round(lw*oh/lh));lh=oh
            logo=logo.resize((lw,lh),Image.Resampling.LANCZOS);logo.putalpha(logo.getchannel('A').point(lambda a:round(a*float(opacity)/100)))
            overlay=Path(tmp)/'logo.png';logo.save(overlay)
            lx=max(0,min(ow-lw,int(logo_x)));ly=max(0,min(oh-lh,int(logo_y)))
            cmd+=['-loop','1','-i',str(overlay),'-filter_complex',f'[0:v]{vf}[base];[base][1:v]overlay={lx}:{ly}:shortest=1:format=auto[out]','-map','[out]']
        else:cmd+=['-vf',vf]
        count=int(end)-int(start)
        if transparent:
            partial=Path(tmp)/'encoded.mov'
            encoding=['-c:v','prores_ks','-profile:v','4','-alpha_bits','16','-pix_fmt','yuva444p10le']
        else:encoding=['-c:v','libx264','-crf',str(int(crf)),'-preset','medium','-pix_fmt','yuv420p','-movflags','+faststart']
        cmd+=['-frames:v',str(count),'-r',f'{clip.fps:.8f}','-an']+encoding+['-y',str(partial)]
        try:r=subprocess.run(cmd,capture_output=True,timeout=600,**flags)
        except subprocess.TimeoutExpired:raise RuntimeError('Video export exceeded ten minutes; try a shorter clip or smaller output.') from None
        if r.returncode:raise RuntimeError('FFmpeg export failed: '+r.stderr.decode(errors='replace')[-1500:])
        actual,duration=ffmpeg.count_frames_and_secs(str(partial))
        if actual!=count:raise RuntimeError(f'Frame verification failed: expected {count}, got {actual}. No output was published.')
        # Exclusive create prevents races from overwriting an existing file.
        try:
            with destination.open('xb') as out,partial.open('rb') as source:shutil.copyfileobj(source,out)
        except FileExistsError:raise ValueError('Output file was created by another process. Choose a new name.') from None
    info={'source':getattr(clip,'original_source',clip.path),'start_frame':int(start),'matching_return_frame_excluded':int(end),'output_frames':count,'fps':clip.fps,'duration_seconds':count/clip.fps,'crop_source_pixels':list(crop),'output_size':[ow,oh],'bytes':destination.stat().st_size,'join_error':clip.compare(start,end),'audio':'removed','transparent':transparent,'effects':getattr(clip,'effect_report',None)}
    report=destination.with_suffix('.loop.json')
    try:
        with report.open('x',encoding='utf-8') as out:json.dump(info,out,indent=2)
    except FileExistsError:pass
    return info
