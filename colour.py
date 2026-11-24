"""Deterministic display-referred colour recipes shared by photos and video."""
import json,math
from pathlib import Path
import numpy as np
import cv2
from PIL import Image

# key, label, minimum, maximum, default; no hidden per-frame auto exposure.
GROUPS={
 'Light': [('exposure','Exposure (EV)',-5,5,0),('contrast','Contrast',-100,100,0),('highlights','Highlights',-100,100,0),('shadows','Shadows',-100,100,0),('whites','Whites',-100,100,0),('blacks','Blacks / black balance',-100,100,0),('gamma','Midtone gamma',.2,3,1)],
 'White balance & colour':[('temperature','Temperature',-100,100,0),('tint','Tint',-100,100,0),('vibrance','Vibrance',-100,100,0),('saturation','Saturation',-100,100,0),('red_gain','Red balance',-100,100,0),('green_gain','Green balance',-100,100,0),('blue_gain','Blue balance',-100,100,0),('red_black','Red black balance',-100,100,0),('green_black','Green black balance',-100,100,0),('blue_black','Blue black balance',-100,100,0)],
 'Presence & detail':[('texture','Texture',-100,100,0),('clarity','Clarity',-100,100,0),('dehaze','Dehaze',-100,100,0),('sharpen','Sharpening',0,100,0),('noise','Luminance noise reduction',0,100,0),('colour_noise','Colour noise reduction',0,100,0)],
 'Effects':[('vignette','Vignette',-100,100,0),('vignette_midpoint','Vignette midpoint',10,90,50),('grain','Grain amount',0,100,0),('monochrome','Black & white mix',0,100,0)],
 'Colour grading':[('shadow_hue','Shadow hue',0,360,0),('shadow_sat','Shadow tint strength',0,100,0),('midtone_hue','Midtone hue',0,360,0),('midtone_sat','Midtone tint strength',0,100,0),('highlight_hue','Highlight hue',0,360,0),('highlight_sat','Highlight tint strength',0,100,0),('grading_balance','Grading balance',-100,100,0)]}
BANDS={'red':0,'orange':30,'yellow':60,'green':120,'aqua':180,'blue':240,'purple':275,'magenta':315}
for band in BANDS:
 GROUPS.setdefault('HSL / Colour mixer',[]).extend([(band+'_hue',band.title()+' hue',-100,100,0),(band+'_sat',band.title()+' saturation',-100,100,0),(band+'_lum',band.title()+' luminance',-100,100,0)])
SPECS={row[0]:row for rows in GROUPS.values() for row in rows}
DEFAULT={k:r[4] for k,r in SPECS.items()}
DEFAULT.update({'curve_master':[[0,0],[1,1]],'curve_red':[[0,0],[1,1]],'curve_green':[[0,0],[1,1]],'curve_blue':[[0,0],[1,1]]})

def validate(value):
 if isinstance(value,str):value=json.loads(value)
 if not isinstance(value,dict):raise ValueError('Colour settings must be a JSON object.')
 if set(value)-set(DEFAULT):raise ValueError('Unrecognized colour controls: '+', '.join(sorted(set(value)-set(DEFAULT))))
 out={**DEFAULT,**value}
 for k,(_,label,lo,hi,_) in SPECS.items():
  n=float(out[k])
  if not math.isfinite(n) or not lo<=n<=hi:raise ValueError(f'{label} must be {lo}–{hi}.')
  out[k]=n
 for k in ('curve_master','curve_red','curve_green','curve_blue'):
  points=out[k]
  if not isinstance(points,list) or not 2<=len(points)<=32:raise ValueError('Curves need 2–32 [input,output] points in 0–1.')
  try:points=[[float(x),float(y)] for x,y in points]
  except (TypeError,ValueError):raise ValueError('Invalid curve points.') from None
  if not all(math.isfinite(x) and math.isfinite(y) and 0<=x<=1 and 0<=y<=1 for x,y in points) or any(points[i][0]>=points[i+1][0] for i in range(len(points)-1)):raise ValueError('Curve inputs must increase strictly, with all values in 0–1.')
  if points[0][0]!=0 or points[-1][0]!=1:raise ValueError('Curves must start at input 0 and end at input 1.')
  out[k]=points
 return out

def payload(settings):return {'format':'atlas-colour','version':1,'working_space':'display-referred sRGB','adjustments':validate(settings)}
def write_preset(path,settings):
 Path(path).write_text(json.dumps(payload(settings),indent=2),encoding='utf-8')
def read_preset(path):
 p=Path(path)
 if p.stat().st_size>1_000_000:raise ValueError('Colour preset exceeds 1 MB.')
 data=json.loads(p.read_text(encoding='utf-8'))
 if data.get('format')!='atlas-colour' or data.get('version')!=1:raise ValueError('Choose an Atlas colour preset v1 JSON, not a Lightroom XMP file.')
 return validate(data['adjustments'])

def apply_colour(image,settings):
 s=validate(settings)
 if s==DEFAULT:return image.copy()
 rgba=image.convert('RGBA');alpha=np.asarray(rgba)[:,:,3].copy();a=np.asarray(rgba)[:,:,:3].astype(np.float32)/255
 # White balance is a relative display-space adjustment, not a camera Kelvin profile.
 gains=np.array([1+s['temperature']*.003+s['red_gain']*.005,1-s['tint']*.002+s['green_gain']*.005,1-s['temperature']*.003+s['blue_gain']*.005],np.float32)
 gains[[0,2]]+=s['tint']*.001;a*=gains
 a=np.power(np.maximum(a,0),2.2)*2**s['exposure'];a=np.power(a,1/2.2)
 lum=np.clip(a@np.array([.2126,.7152,.0722],np.float32),0,1)
 sh=(1-lum)**2;hi=lum**2
 lift=(s['shadows']*.003*sh+s['highlights']*.003*hi+s['whites']*.0025*lum**4+s['blacks']*.0025*(1-lum)**4)
 a+=lift[:,:,None];a+=sh[:,:,None]*np.array([s['red_black'],s['green_black'],s['blue_black']],np.float32)*.0025
 a=(a-.5)*2**(s['contrast']/100)+.5;a=np.maximum(a,0)**(1/s['gamma'])
 for channel,k in enumerate(('curve_red','curve_green','curve_blue')):
  for points in (s['curve_master'],s[k]):
   a[:,:,channel]=np.interp(a[:,:,channel],*[np.array(points)[:,i] for i in (0,1)])
 a=np.clip(a,0,1).astype(np.float32)
 if any(s[k]!=0 for k in s if k.endswith(('_hue','_sat','_lum')) and k.split('_')[0] in BANDS):
  hsv=cv2.cvtColor(a,cv2.COLOR_RGB2HSV);base=hsv[:,:,0].copy();ds=np.zeros_like(base);dh=ds.copy();dv=ds.copy()
  for band,center in BANDS.items():
   distance=np.abs((base-center+180)%360-180);weight=np.maximum(0,1-distance/45)
   dh+=weight*s[band+'_hue']*.3;ds+=weight*s[band+'_sat']/100;dv+=weight*s[band+'_lum']*.003
  hsv[:,:,0]=(base+dh)%360;hsv[:,:,1]=np.clip(hsv[:,:,1]*(1+ds),0,1);hsv[:,:,2]=np.clip(hsv[:,:,2]+dv,0,1);a=cv2.cvtColor(hsv,cv2.COLOR_HSV2RGB)
 lum=a@np.array([.2126,.7152,.0722],np.float32);chroma=a.max(axis=2)-a.min(axis=2)
 factor=np.maximum(0,(1+s['saturation']/100)*(1+s['vibrance']/100*(1-chroma)))
 a=lum[:,:,None]+(a-lum[:,:,None])*factor[:,:,None]
 for zone,weight in [('shadow',np.clip(1-lum*2+s['grading_balance']/200,0,1)),('midtone',np.maximum(0,1-abs(lum-.5)*2)),('highlight',np.clip(lum*2-1+s['grading_balance']/200,0,1))]:
  hsv=np.array([[[s[zone+'_hue'],1,1]]],np.float32);tint=cv2.cvtColor(hsv,cv2.COLOR_HSV2RGB)[0,0]-.5
  a+=weight[:,:,None]*tint*s[zone+'_sat']*.004
 if s['dehaze']:a=(a-.5)*(1+s['dehaze']*.006)+.5-s['dehaze']*.0003
 if s['noise'] or s['colour_noise']:
  blur=cv2.GaussianBlur(a,(0,0),1+s['noise']/40)
  weight=s['noise']/100*.8;a=a*(1-weight)+blur*weight
  if s['colour_noise']:
   lab=cv2.cvtColor(np.clip(a,0,1),cv2.COLOR_RGB2Lab);ab=cv2.GaussianBlur(lab[:,:,1:],(0,0),1.5);weight=s['colour_noise']/100;lab[:,:,1:]=lab[:,:,1:]*(1-weight)+ab*weight;a=cv2.cvtColor(lab,cv2.COLOR_Lab2RGB)
 # Relative radii keep low-res previews close to final renders; zero alpha stays unchanged.
 scale=max(a.shape[:2])/1080
 for k,radius,amount in [('texture',1.5,.008),('clarity',12,.008),('sharpen',.7,.012)]:
  if s[k]:a+=(a-cv2.GaussianBlur(a,(0,0),max(.35,radius*scale)))*s[k]*amount
 mono=s['monochrome']/100
 if mono:a=a*(1-mono)+(a@np.array([.2126,.7152,.0722],np.float32))[:,:,None]*mono
 if s['vignette']:
  y,x=np.indices(a.shape[:2],dtype=np.float32);r=np.sqrt(((x/(max(1,a.shape[1]-1))-.5)*2)**2+((y/(max(1,a.shape[0]-1))-.5)*2)**2)
  mask=np.clip((r-s['vignette_midpoint']/100)/max(.1,1.4-s['vignette_midpoint']/100),0,1)**2;a*=1+s['vignette']/100*mask[:,:,None]*.9
 if s['grain']:
  # Fixed seed gives deterministic re-exports and avoids frame-to-frame noise flicker.
  a+=np.random.default_rng(4105).normal(0,s['grain']*.0005,(*a.shape[:2],1)).astype(np.float32)
 out=np.dstack((np.clip(np.round(a*255),0,255).astype(np.uint8),alpha));return Image.fromarray(out)
