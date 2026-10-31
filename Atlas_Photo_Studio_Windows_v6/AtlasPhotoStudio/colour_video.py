"""Colour-managed final video pass; logo is composited after grading."""
import json,tempfile,shutil
from pathlib import Path
import numpy as np
from PIL import Image
import imageio_ffmpeg as ffmpeg
from colour import validate,apply_colour,write_preset,payload

def export_colour_loop(clip,start,end,destination,recipe,crop=None,edge=1080,logo_path='',logo_width=18,logo_x=0,logo_y=0,opacity=100,progress=lambda text:None):
 from core import load_image
 recipe=validate(recipe);clip.validate_bounds(start,end);dest=Path(destination)
 transparent=bool(getattr(clip,'effects',None) and clip.effects.remove_background and clip.effects.background=='transparent')
 ext='.mov' if transparent else '.mp4'
 if dest.suffix.lower()!=ext:raise ValueError(f'This export requires {ext}.')
 if dest.exists() or dest.resolve()==Path(clip.path).resolve():raise ValueError('Choose a new output filename. Existing videos are never overwritten.')
 stat=Path(clip.path).stat()
 if (stat.st_size,stat.st_mtime_ns)!=clip.source_stamp:raise ValueError('Source changed; reopen and reprocess it.')
 w,h=clip.size;x,y,cw,ch=map(int,crop or (0,0,w,h))
 if x<0 or y<0 or cw<2 or ch<2 or x+cw>w or y+ch>h:raise ValueError('Crop must fit inside the video.')
 if not 128<=int(edge)<=3840:raise ValueError('Output edge must be 128–3840.')
 scale=min(1,edge/max(cw,ch));ow=max(2,int(cw*scale)//2*2);oh=max(2,int(ch*scale)//2*2)
 logo=None
 if logo_path:
  if not 1<=logo_width<=95 or not 0<=opacity<=100:raise ValueError('Invalid logo settings.')
  logo=load_image(logo_path);box=logo.getbbox()
  if not box:raise ValueError('Logo is empty.')
  logo=logo.crop(box);lw=max(1,round(ow*logo_width/100));lh=max(1,round(logo.height*lw/logo.width))
  if lh>oh:lw=max(1,round(lw*oh/lh));lh=oh
  logo=logo.resize((lw,lh),Image.Resampling.LANCZOS);logo.putalpha(logo.getchannel('A').point(lambda a:round(a*opacity/100)))
  lx=max(0,min(ow-lw,int(logo_x)));ly=max(0,min(oh-lh,int(logo_y)))
 count=end-start;dest.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='atlas-colour-export-') as tmp:
  path=Path(tmp)/('render'+ext)
  vf=f'fps={clip.fps:.8f},trim=start_frame={start}:end_frame={end},setpts=PTS-STARTPTS,crop={cw}:{ch}:{x}:{y}:exact=1,scale={ow}:{oh}'
  reader=ffmpeg.read_frames(clip.path,pix_fmt='rgba',bits_per_pixel=32,output_params=['-vf',vf,'-vsync','0','-an']);next(reader)
  writer=ffmpeg.write_frames(str(path),(ow,oh),pix_fmt_in='rgba',pix_fmt_out='yuva444p10le' if transparent else 'yuv420p',fps=clip.fps,codec='prores_ks' if transparent else 'libx264',macro_block_size=1,output_params=['-profile:v','4','-alpha_bits','16'] if transparent else ['-crf','18','-movflags','+faststart']);writer.send(None)
  actual=0
  try:
   for data in reader:
    im=apply_colour(Image.frombytes('RGBA',(ow,oh),data),recipe)
    if logo:im.alpha_composite(logo,(lx,ly))
    writer.send(im.tobytes());actual+=1
    if actual%max(1,round(clip.fps))==0:progress(f'Grading and exporting: {actual}/{count} frames')
  finally:reader.close();writer.close()
  verified,_=ffmpeg.count_frames_and_secs(str(path))
  if actual!=count or verified!=count:raise ValueError(f'Frame count verification failed: expected {count}, decoded {actual}, encoded {verified}; no output was published.')
  # Sidecar collisions must not silently overwrite another edit's recipe.
  preset=dest.with_suffix(dest.suffix+'.colour.json');report=dest.with_suffix('.loop.json')
  if preset.exists() or report.exists():raise ValueError('A settings sidecar already exists for this name; choose another filename.')
  with dest.open('xb') as out,path.open('rb') as source:shutil.copyfileobj(source,out)
 write_preset(preset,recipe)
 info={'source':getattr(clip,'original_source',clip.path),'start_frame':start,'matching_return_frame_excluded':end,'output_frames':count,'fps':clip.fps,'duration_seconds':count/clip.fps,'output_size':[ow,oh],'crop_source_pixels':[x,y,cw,ch],'bytes':dest.stat().st_size,'transparent':transparent,'audio':'removed','colour':payload(recipe),'effects':getattr(clip,'effect_report',None)}
 with report.open('x',encoding='utf-8') as out:json.dump(info,out,indent=2)
 return info
