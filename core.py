"""Atlas Photo Studio: deterministic image preparation and selection."""
from __future__ import annotations
import base64, hashlib, io, json, re, time
from pathlib import Path
from dataclasses import dataclass, asdict, replace
from functools import lru_cache
from scipy import ndimage
import numpy as np
from PIL import Image, ImageOps, ImageCms, ImageFile

SUPPORTED = {'.jpg', '.jpeg', '.png', '.webp', '.tif', '.tiff', '.bmp'}
@dataclass
class Settings:
    logo_path: str = ''
    logo_width: float = 18
    logo_opacity: float = 100
    logo_x: float = 32
    logo_y: float = 32
    longest_edge: int = 2048
    max_mb: float = 2
    quality: int = 92
    format: str = 'JPEG'
    square: bool = False
    output_dir: str = ''
    shop: str = ''
    model: str = 'gpt-4.1-mini'
    watch_dir: str = ''
    preview_edge: int = 720
    white_threshold: int = 235
    white_feather: int = 15
    filename_blocks: str = '[{"kind":"name","value":"","enabled":true},{"kind":"sequence","value":"","enabled":true},{"kind":"view","value":"","enabled":true}]'
    alt_blocks: str = '[{"kind":"name","value":"","enabled":true},{"kind":"sequence","value":"","enabled":true},{"kind":"view","value":"","enabled":true}]'
    crop_boxes: str = '{}'
    main_logo: str = 'No'
    crop_aspect: str = '1:1'
    colour_json: str = '{}'
    separator: str = ' - ' 
    def validate(self, require_logo=True):
        for name in ('logo_width', 'logo_opacity', 'logo_x', 'logo_y'):
            n = float(getattr(self, name))
            lo, hi = (1, 95) if name == 'logo_width' else (0, 4096) if name in ('logo_x','logo_y') else (0, 100)
            if not lo <= n <= hi: raise ValueError(f'{name} must be between {lo} and {hi}.')
        if not 256 <= int(self.longest_edge) <= 4096: raise ValueError('Longest edge must be 256–4096 px.')
        if not 0.1 <= float(self.max_mb) <= 19: raise ValueError('File target must be 0.1–19 MB.')
        if not 60 <= int(self.quality) <= 100: raise ValueError('JPEG quality must be 60–100.')
        if self.format not in ('JPEG', 'PNG'): raise ValueError('Choose JPEG or PNG.')
        if not 240 <= int(self.preview_edge) <= 1080: raise ValueError('Preview edge must be 240–1080 px.')
        if not 180 <= int(self.white_threshold) <= 254: raise ValueError('White threshold must be 180–254.')
        if not 1 <= int(self.white_feather) <= 50: raise ValueError('White feather must be 1–50.')
        from colour import validate as validate_colour
        validate_colour(self.colour_json)
        for blocks in (self.filename_blocks,self.alt_blocks): parse_blocks(blocks)
        if require_logo and not Path(self.logo_path).is_file(): raise ValueError('Choose an existing PNG, JPEG or WebP logo file.')

def load_image(path):
    with Image.open(path) as source:
        im = ImageOps.exif_transpose(source)
        profile = source.info.get('icc_profile')
        alpha = im.convert('RGBA').getchannel('A')
        if profile:
            try:
                rgb = ImageCms.profileToProfile(im.convert('RGB'), ImageCms.ImageCmsProfile(io.BytesIO(profile)), ImageCms.createProfile('sRGB'), outputMode='RGB')
                im = rgb.convert('RGBA'); im.putalpha(alpha)
            except (OSError, ValueError, ImageCms.PyCMSError):
                raise ValueError(f'Cannot convert embedded colour profile in {Path(path).name}; export it as sRGB first.')
        return im.convert('RGBA').copy()

def _stamp(path):
    p=Path(path); st=p.stat(); return str(p.resolve()),st.st_mtime_ns,st.st_size

@lru_cache(maxsize=24)
def _proxy_cached(stamp, edge):
    # JPEG draft reduces decoding work; other formats are decoded once per cached proxy.
    with Image.open(stamp[0]) as src:
        src.draft('RGB',(edge,edge))
        im=ImageOps.exif_transpose(src).convert('RGBA')
        im.thumbnail((edge,edge),Image.Resampling.BILINEAR)
        return im.copy()

def load_proxy(path, edge=720):
    return _proxy_cached(_stamp(path),int(edge)).copy()

@lru_cache(maxsize=64)
def _source_size(stamp):
    with Image.open(stamp[0]) as im:
        w,h=im.size
        return (h,w) if im.getexif().get(274) in (5,6,7,8) else (w,h)

def source_size(path): return _source_size(_stamp(path))

def crop_for(path, settings):
    boxes=json.loads(settings.crop_boxes)
    box=boxes.get(str(path))
    if box is None:
        from crop_geometry import RATIOS, fit_ratio
        w,h=source_size(path);px=fit_ratio([0,0,w,h*.55],(w,h),RATIOS.get(settings.crop_aspect,1))
        box=[px[0]/w,px[1]/h,px[2]/w,px[3]/h]
    if len(box)!=4 or not all(np.isfinite(float(v)) for v in box): raise ValueError('Invalid mainshot crop.')
    x0,y0,x1,y1=map(float,box)
    if not (0<=x0<x1<=1 and 0<=y0<y1<=1): raise ValueError('Crop must fit inside the photo.')
    from crop_geometry import RATIOS,fit_ratio
    ratio=RATIOS.get(settings.crop_aspect)
    if ratio:
        w,h=source_size(path);b=fit_ratio([x0*w,y0*h,x1*w,y1*h],(w,h),ratio)
        return b[0]/w,b[1]/h,b[2]/w,b[3]/h
    return x0,y0,x1,y1

def remove_white(im, threshold=235, feather=15):
    """Remove only neutral near-white areas connected to an image edge."""
    arr=np.asarray(im.convert('RGBA')).copy(); rgb=arr[:,:,:3].astype(float)
    low=rgb.min(axis=2); neutral=rgb.max(axis=2)-low<=30
    candidate=((low>=threshold)&neutral)|(arr[:,:,3]==0)
    seed=np.zeros(candidate.shape,dtype=bool)
    seed[0,:]=candidate[0,:];seed[-1,:]=candidate[-1,:]
    seed[:,0]=candidate[:,0];seed[:,-1]=candidate[:,-1]
    mask=ndimage.binary_propagation(seed,mask=candidate)
    a=np.ones(low.shape);a[mask]=np.clip((threshold+feather-low[mask])/feather,0,1)
    # Remove white matte from partially transparent boundary pixels.
    soft=mask & (a>0) & (a<1)
    rgb[soft]=np.clip((rgb[soft]-255*(1-a[soft,None]))/a[soft,None],0,255)
    arr[:,:,:3]=rgb.astype(np.uint8);arr[:,:,3]=(arr[:,:,3]*a).astype(np.uint8)
    return Image.fromarray(arr)

def crop_pixels(size,box,aspect):
    from crop_geometry import RATIOS
    from fractions import Fraction
    w,h=size;x0,y0,x1,y1=box
    cw=max(1,round((x1-x0)*w));ch=max(1,round((y1-y0)*h))
    ratio=RATIOS.get(aspect)
    if ratio:
        f=Fraction(ratio).limit_denominator(100);unit=int(min(cw/f.numerator,ch/f.denominator))
        if unit>=1:cw=unit*f.numerator;ch=unit*f.denominator
    left=max(0,min(w-cw,round(x0*w)));top=max(0,min(h-ch,round(y0*h)))
    return left,top,left+cw,top+ch

def canvas_size(path, settings, main=False):
    w,h=source_size(path)
    if main:
        a,b,c,d=crop_pixels((w,h),crop_for(path,settings),settings.crop_aspect);w=c-a;h=d-b
    scale=min(1,int(settings.longest_edge)/max(w,h));w=max(1,round(w*scale));h=max(1,round(h*scale))
    if settings.square and not main:w=h=max(w,h)
    return w,h

def logo_geometry(size, logo, settings):
    w,h=size; box=logo.getbbox()
    if not box:raise ValueError('Logo is completely transparent.')
    lw=max(1,min(w,round(w*float(settings.logo_width)/100)));lh=max(1,round(logo.crop(box).height*lw/logo.crop(box).width))
    if lh>h:lw=max(1,round(lw*h/lh));lh=h
    x=max(0,min(round(float(settings.logo_x)),w-lw));y=max(0,min(round(float(settings.logo_y)),h-lh))
    return x,y,lw,lh

@lru_cache(maxsize=16)
def _base_preview(stamp, edge, crop, main, threshold, feather, square, final_size, aspect):
    im=load_proxy(stamp[0],edge)
    if main:
        im=remove_white(im,threshold,feather)
        im=im.crop(crop_pixels(im.size,crop,aspect))
    if square and not main:
        side=max(im.size);bg=Image.new('RGBA',(side,side),'white');bg.alpha_composite(im,((side-im.width)//2,(side-im.height)//2));im=bg
    # Crop may magnify a low-res proxy; preview dimensions stay bounded.
    ratio=min(1,edge/max(final_size));target=(max(1,round(final_size[0]*ratio)),max(1,round(final_size[1]*ratio)))
    return im.resize(target,Image.Resampling.BILINEAR)

def render(path, settings, main=False, preview=False):
    settings.validate(require_logo=not main or settings.main_logo=='Yes')
    final=canvas_size(path,settings,main)
    crop=crop_for(path,settings) if main else None
    if preview:
        im=_base_preview(_stamp(path),int(settings.preview_edge),crop,main,int(settings.white_threshold),int(settings.white_feather),settings.square,final,settings.crop_aspect).copy()
    else:
        im=load_image(path)
        if main:
            # Keep source detail for the crop but avoid processing unnecessarily large canvases.
            x0,y0,x1,y1=crop
            ratio=min(1,int(settings.longest_edge)/max(im.width*(x1-x0),im.height*(y1-y0)))
            if ratio<1:im=im.resize((max(1,round(im.width*ratio)),max(1,round(im.height*ratio))),Image.Resampling.LANCZOS)
            im=remove_white(im,int(settings.white_threshold),int(settings.white_feather))
            im=im.crop(crop_pixels(im.size,crop,settings.crop_aspect))
        im.thumbnail((int(settings.longest_edge),int(settings.longest_edge)),Image.Resampling.LANCZOS)
        if settings.square and not main:
            side=max(im.size);bg=Image.new('RGBA',(side,side),'white');bg.alpha_composite(im,((side-im.width)//2,(side-im.height)//2));im=bg
    from colour import apply_colour
    im=apply_colour(im,settings.colour_json)
    if main and settings.main_logo!='Yes': return im
    logo=load_proxy(settings.logo_path,1024) if preview else load_image(settings.logo_path)
    x,y,lw,lh=logo_geometry(final,logo,settings)
    sx,sy=im.width/final[0],im.height/final[1]
    logo=logo.crop(logo.getbbox()).resize((max(1,round(lw*sx)),max(1,round(lh*sy))),Image.Resampling.BILINEAR if preview else Image.Resampling.LANCZOS)
    logo.putalpha(logo.getchannel('A').point(lambda a:round(a*float(settings.logo_opacity)/100)))
    im.alpha_composite(logo,(round(x*sx),round(y*sy)))
    return im

KINDS=('text','name','sequence','view')
MAIN_SUFFIX='MAINSHOT CLOSEUP'
def parse_blocks(raw):
    blocks=json.loads(raw)
    if not isinstance(blocks,list) or len(blocks)>30:raise ValueError('Names need a list of up to 30 blocks.')
    for b in blocks:
        if not isinstance(b,dict) or b.get('kind') not in KINDS:raise ValueError('Invalid naming block.')
    return blocks

def build_name(raw,product,view,index,separator,main=False,filename=False):
    values={'name':product,'view':view,'sequence':f'{index:02d}'}
    parts=[str(b.get('value','')) if b['kind']=='text' else values[b['kind']] for b in parse_blocks(raw) if b.get('enabled',True)]
    result=separator.join(p.strip() for p in parts if p.strip())
    if not result.strip():raise ValueError('Enable at least one non-empty naming block.')
    # Keep the mandatory mainshot suffix at the END even with custom postfix blocks.
    result=re.sub(r'\s+',' ',result).strip()
    if main:
        result=result.replace(MAIN_SUFFIX,'').strip(' -_')
        result=result[:(150 if filename else 512)-len(MAIN_SUFFIX)-3].rstrip(' -_')+' - '+MAIN_SUFFIX
    if filename:return clean_name(result)
    if len(result)>512:raise ValueError('Alt text exceeds 512 characters; shorten the blocks.')
    return result

def encode(im, settings):
    limit = int(float(settings.max_mb)*1_000_000)
    ImageFile.MAXBLOCK = max(ImageFile.MAXBLOCK, im.width*im.height*4)
    for _ in range(20):
        if settings.format == 'JPEG':
            flat = Image.new('RGB', im.size, 'white'); flat.paste(im, mask=im.getchannel('A'))
            for q in range(int(settings.quality), 59, -4):
                out = io.BytesIO(); flat.save(out, 'JPEG', quality=q, optimize=True, subsampling=0)
                if len(out.getvalue()) < limit: return out.getvalue(), flat.size
        else:
            out = io.BytesIO(); im.save(out, 'PNG', optimize=True)
            if len(out.getvalue()) < limit: return out.getvalue(), im.size
        size = (round(im.width*.85), round(im.height*.85))
        if min(size) < 128: break
        im = im.resize(size, Image.Resampling.LANCZOS)
    raise ValueError('Cannot reach the file-size target without excessive resizing. Increase the target.')

def clean_name(value):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', value).strip(' .')
    name = re.sub(r'\s+', ' ', name)[:150].rstrip(' .')
    if not name: raise ValueError('Enter a product name.')
    if name.upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}: name = 'Atlas '+name
    return name

def fingerprint(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def analyse(path):
    im = load_image(path).convert('RGB'); im.thumbnail((512,512))
    a = np.asarray(im.convert('L'), dtype=float)
    lap = -4*a[1:-1,1:-1]+a[:-2,1:-1]+a[2:,1:-1]+a[1:-1,:-2]+a[1:-1,2:]
    # Ignore white backgrounds for exposure scoring.
    subject = a[a < 245]
    exposure = float(np.mean((subject > 8) & (subject < 240))) if subject.size else 0
    sharpness = float(np.var(lap)) if lap.size else 0
    score = np.log1p(sharpness)*.75+exposure*.25
    small = np.asarray(im.resize((32,32)).convert('L'), dtype=float)/255
    return float(score), small

def choose_local(paths, count=5):
    candidates = []; hashes = set()
    for p in paths:
        h = fingerprint(p)
        if h not in hashes:
            score, feature = analyse(p); candidates.append((p,score,feature)); hashes.add(h)
    chosen = []
    while candidates and len(chosen)<count:
        def rank(c):
            distance = min(float(np.mean(abs(c[2]-s[2]))) for s in chosen) if chosen else 0
            return c[1] + distance*8
        best = max(candidates, key=rank); candidates.remove(best); chosen.append(best)
    return [(str(c[0]), f'View {i+1}') for i,c in enumerate(chosen)]

def choose_ai(paths, key, model, product):
    import requests
    if not key: raise ValueError('Enter an OpenAI API key in Connections to use AI selection.')
    # Bound cost and request size; local shortlist preserves quality/diversity.
    paths = [p for p,_ in choose_local(paths, 24)]
    content = [{'type':'text','text':f'Select up to five best distinct product photography views for {product}. Prioritize sharp subject, useful cutting features, clean framing and different actual viewing angles. Avoid near-duplicates even if rotated/cropped. Return fewer if insufficient usable views. Return JSON only: {{"selected":[{{"index":0,"view":"Main","reason":"..."}}]}}. Index is zero-based, order strongest hero first. View labels must be short, factual, unique, and describe only what is visible.'}]
    for i,p in enumerate(paths):
        im=load_image(p); im.thumbnail((768,768)); bg=Image.new('RGB',im.size,'white'); bg.paste(im,mask=im.getchannel('A'))
        b=io.BytesIO(); bg.save(b,'JPEG',quality=80)
        content += [{'type':'text','text':f'Photo index {i}'},{'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode()}}]
    r=requests.post('https://api.openai.com/v1/chat/completions',headers={'Authorization':'Bearer '+key},json={'model':model,'messages':[{'role':'user','content':content}],'response_format':{'type':'json_object'}},timeout=180)
    if not r.ok: raise ValueError(f'OpenAI request failed (HTTP {r.status_code}). Check key, billing and model access.')
    raw=json.loads(r.json()['choices'][0]['message']['content'])['selected']; chosen=[]; seen=set()
    for item in raw[:5]:
        i=int(item['index'])
        if not 0<=i<len(paths) or i in seen: raise ValueError('AI returned an invalid or duplicate photo index. Try again or use local selection.')
        seen.add(i); chosen.append((paths[i],clean_name(str(item['view']))[:40]))
    if not chosen: raise ValueError('AI found no usable photos. Select manually or use local selection.')
    return chosen

def export_batch(rows, product, settings):
    settings.validate(require_logo=False); base=clean_name(product)[:95].rstrip(' .')
    root=Path(settings.output_dir).expanduser().resolve()
    root.mkdir(parents=True,exist_ok=True)
    # A fresh batch folder avoids overwriting exports or source images.
    import tempfile
    folder=Path(tempfile.mkdtemp(prefix=base[:70]+' - ',dir=root)); manifest=[]
    for i,(path,view) in enumerate(rows,1):
        main=i==1
        stem=build_name(settings.filename_blocks,product,view,i,settings.separator,main,True)
        alt=build_name(settings.alt_blocks,product,view,i,settings.separator,main)
        fmt='PNG' if main else settings.format
        # Always preserve first-image transparency, regardless of other export settings.
        data,size=encode(render(path,settings,main=main),replace(settings,format=fmt))
        name=stem+('.jpg' if fmt=='JPEG' else '.png')
        # Blocks may omit sequence/view; prevent overwrites without changing the requested suffix.
        if any(Path(m['file']).name.casefold()==name.casefold() for m in manifest):
            stem=(stem.removesuffix(' - '+MAIN_SUFFIX)+f' - {i:02d} - '+MAIN_SUFFIX) if main else stem[:142]+f' - {i:02d}'
            name=stem+('.jpg' if fmt=='JPEG' else '.png')
        dest=folder/name; dest.write_bytes(data)
        from colour import write_preset
        write_preset(dest.with_suffix(dest.suffix+'.colour.json'),settings.colour_json)
        manifest.append({'source':str(path),'file':str(dest),'alt':alt,'mainshot':main,'colour_preset':str(dest.with_suffix(dest.suffix+'.colour.json')),'width':size[0],'height':size[1],'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    (folder/'manifest.json').write_text(json.dumps({'product':product,'settings':asdict(settings),'images':manifest},indent=2),encoding='utf-8')
    return manifest
