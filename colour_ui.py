import json,threading,queue
from dataclasses import replace
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from PIL import Image,ImageTk,ImageDraw
import numpy as np
from colour import GROUPS,SPECS,DEFAULT,validate,apply_colour,read_preset,write_preset
from core import load_proxy

class ColourEditor(tk.Toplevel):
 def __init__(self,app,source='photo'):
  super().__init__(app);self.app=app;self.source=source;self.picking=False;self.title('Atlas Colour Studio • Photo & Video');self.geometry('1220x900');self.minsize(1000,760);self.configure(bg='#111111');self.transient(app)
  current=validate(app.vars['colour_json'].get());self.v={k:tk.StringVar(value=str(v)) for k,v in current.items() if k in SPECS};self.curves={k:tk.StringVar(value=json.dumps(current[k])) for k in current if k.startswith('curve_')};self.jobs=queue.Queue();self.counter=0;self.executor=None;self.dirty=False
  header=ttk.Frame(self,padding=12);header.pack(fill='x');ttk.Label(header,text='COLOUR STUDIO',foreground='#f5a900',font=('Segoe UI',17,'bold')).pack(side='left');ttk.Label(header,text='Shared photo/video recipe • exports include importable JSON sidecars').pack(side='left',padx=18)
  ttk.Button(header,text='Neutral eyedropper',command=self.pick_mode).pack(side='right')
  footer=ttk.Frame(self,padding=12);footer.pack(side='bottom',fill='x')
  for label,cmd in [('Import preset',self.import_preset),('Export preset',self.export_preset),('Reset all',self.reset),('Apply & save defaults',self.apply)]:ttk.Button(footer,text=label,command=cmd,style='Gold.TButton' if label.startswith('Apply') else 'TButton').pack(side='left',padx=(0,10))
  self.status=ttk.Label(footer,text='Preview: before / after');self.status.pack(side='right')
  body=ttk.Panedwindow(self,orient='horizontal');body.pack(fill='both',expand=True,padx=12)
  controls=ttk.Frame(body);preview=ttk.Frame(body);body.add(controls,weight=2);body.add(preview,weight=3)
  tabs=ttk.Notebook(controls);tabs.pack(fill='both',expand=True)
  for title,rows in GROUPS.items():
   page=ttk.Frame(tabs);tabs.add(page,text={'Light':'Light','White balance & colour':'WB','Presence & detail':'Detail','Effects':'FX','Colour grading':'Grade','HSL / Colour mixer':'HSL'}[title]);canvas=tk.Canvas(page,bg='#111111',highlightthickness=0);scroll=ttk.Scrollbar(page,command=canvas.yview);canvas.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');canvas.pack(fill='both',expand=True);frame=ttk.Frame(canvas,padding=10);window=canvas.create_window((0,0),window=frame,anchor='nw');frame.bind('<Configure>',lambda e,c=canvas:c.configure(scrollregion=c.bbox('all')));canvas.bind('<Configure>',lambda e,c=canvas,w=window:c.itemconfigure(w,width=e.width))
   for k,label,lo,hi,default in rows:
    row=ttk.Frame(frame);row.pack(fill='x',pady=5);ttk.Label(row,text=label).pack(anchor='w');sub=ttk.Frame(row);sub.pack(fill='x');ttk.Scale(sub,from_=lo,to=hi,variable=self.v[k],command=lambda value:self.schedule()).pack(side='left',fill='x',expand=True);entry=ttk.Entry(sub,textvariable=self.v[k],width=8);entry.pack(side='left',padx=5);entry.bind('<Return>',lambda e:self.schedule());entry.bind('<FocusOut>',lambda e:self.schedule());ttk.Button(sub,text='↺',width=2,command=lambda key=k,d=default:self.set_value(key,d)).pack(side='left')
  page=ttk.Frame(tabs,padding=12);tabs.add(page,text='Curves')
  ttk.Label(page,text='Control points [input, output], normalized 0–1.\nStart at input 0, end at input 1. Piecewise-linear curves.\nExample S curve: [[0,0],[0.25,0.18],[0.75,0.82],[1,1]]',wraplength=450).pack(anchor='w',pady=10)
  for k,var in self.curves.items():ttk.Label(page,text=k.replace('_',' ').title()).pack(anchor='w',pady=(12,4));e=ttk.Entry(page,textvariable=var);e.pack(fill='x');e.bind('<Return>',lambda event:self.schedule())
  ttk.Button(page,text='Preview curves',command=self.schedule).pack(anchor='w',pady=12)
  self.canvas=tk.Canvas(preview,bg='#080808',highlightthickness=0,height=500);self.canvas.pack(fill='both',expand=True,padx=8);self.canvas.bind('<Configure>',lambda e:self.schedule());self.canvas.bind('<Button-1>',self.pick_neutral);self.hist=tk.Canvas(preview,bg='#181818',height=100,highlightthickness=0);self.hist.pack(fill='x',padx=8,pady=8)
  ttk.Label(preview,text='Display-referred controls for edited images/video. No RAW recovery or Lightroom XMP compatibility.\nGrade is applied before logo overlays; alpha is preserved. Detail preview is approximate.',wraplength=600,foreground='#aaaaaa').pack(anchor='w',padx=8,pady=8)
  self.base=self.get_base();self.after(80,self.poll);self.schedule();self.protocol('WM_DELETE_WINDOW',self.close)
 def get_base(self):
  try:
   if self.source=='video' and self.app.video.clip:
    clip=self.app.video.clip;index=max(0,min(clip.count-1,int(self.app.video.start.get())));im=clip.rgba_frame(index) if hasattr(clip,'rgba_frame') else clip.frame(index);im.thumbnail((540,540));return im
   i=self.app.current()
   if i is not None:return load_proxy(self.app.photos[i]['path'],540)
  except Exception:pass
  # Neutral ramp is useful when configuring presets before importing media.
  ramp=np.tile(np.arange(256,dtype=np.uint8),(256,1));return Image.fromarray(np.dstack((ramp,ramp,ramp)))
 def settings(self):return validate({**{k:float(v.get()) for k,v in self.v.items()},**{k:json.loads(v.get()) for k,v in self.curves.items()}})
 def set_value(self,key,value):self.v[key].set(str(value));self.schedule()
 def schedule(self,*args):
  if hasattr(self,'timer'):
   try:self.after_cancel(self.timer)
   except tk.TclError:pass
  self.timer=self.after(160,self.preview)
 def preview(self):
  try:s=self.settings()
  except Exception as e:self.status.configure(text=str(e));return
  self.counter+=1;request=self.counter;self.status.configure(text='Rendering preview…')
  # One bounded worker at a time; changing controls replaces pending work.
  from concurrent.futures import ThreadPoolExecutor
  if self.executor is None:self.executor=ThreadPoolExecutor(max_workers=1)
  if hasattr(self,'future') and not self.future.running():self.future.cancel()
  def work():
   try:self.jobs.put((request,apply_colour(self.base,s),None))
   except Exception as e:self.jobs.put((request,None,str(e)))
  self.future=self.executor.submit(work)
 def poll(self):
  try:
   while True:
    request,after,error=self.jobs.get_nowait()
    if request!=self.counter:continue
    if error:self.status.configure(text=error);continue
    self.draw(after);self.status.configure(text='Before / after • RGB histogram')
  except queue.Empty:pass
  self.poll_id=self.after(80,self.poll)
 def draw(self,after):
  self.canvas.delete('all');self.images=[];w=max(300,self.canvas.winfo_width());h=max(180,self.canvas.winfo_height())
  for i,(label,im) in enumerate([('BEFORE',self.base.copy()),('AFTER',after.copy())]):
   im.thumbnail((w//2-12,h-50));
   if i==0:self.before_bounds=((i+.5)*w/2-im.width/2,h/2+10-im.height/2,im.width,im.height)
   ph=ImageTk.PhotoImage(im);self.images.append(ph);self.canvas.create_text((i+.5)*w/2,20,text=label,fill='#f5a900');self.canvas.create_image((i+.5)*w/2,h/2+10,image=ph)
  self.hist.delete('all');arr=np.asarray(after.convert('RGB'));hw=max(256,self.hist.winfo_width());hh=100
  for c,color in enumerate(('#e66b6b','#64ca83','#6e95ed')):
   counts=np.histogram(arr[:,:,c],bins=128,range=(0,256))[0];counts=np.log1p(counts);counts/=max(1,counts.max());points=[]
   for x,y in enumerate(counts):points.extend((x/127*hw,hh-y*(hh-6)))
   self.hist.create_line(*points,fill=color)
 def pick_mode(self):
  self.picking=True;self.canvas.configure(cursor='crosshair');self.status.configure(text='Click a neutral grey patch in BEFORE')
 def pick_neutral(self,event):
  if not self.picking or not hasattr(self,'before_bounds'):return
  x,y,w,h=self.before_bounds
  if not x<=event.x<x+w or not y<=event.y<y+h:return
  px=int((event.x-x)/w*self.base.width);py=int((event.y-y)/h*self.base.height);a=np.asarray(self.base.convert('RGBA'));patch=a[max(0,py-2):py+3,max(0,px-2):px+3]
  rgb=patch[:,:,:3][patch[:,:,3]>127]
  if not len(rgb):return
  sample=np.median(rgb,axis=0)
  if sample.min()<8:self.status.configure(text='Choose a brighter neutral patch');return
  gains=sample.mean()/sample
  self.v['temperature'].set('0');self.v['tint'].set('0')
  for key,gain in zip(('red_gain','green_gain','blue_gain'),gains):self.v[key].set(str(round(float(np.clip((gain-1)/.005,-100,100)),2)))
  self.picking=False;self.canvas.configure(cursor='');self.schedule()
 def load(self,s):
  for k,v in s.items():
   if k in self.v:self.v[k].set(str(v))
   elif k in self.curves:self.curves[k].set(json.dumps(v))
  self.schedule()
 def reset(self):self.load(DEFAULT)
 def import_preset(self):
  path=filedialog.askopenfilename(parent=self,title='Import Atlas colour preset',filetypes=[('Atlas colour JSON','*.json')])
  if path:
   try:self.load(read_preset(path))
   except Exception as e:messagebox.showerror('Preset import',str(e),parent=self)
 def export_preset(self):
  path=filedialog.asksaveasfilename(parent=self,title='Export Atlas colour preset',defaultextension='.json',initialfile='Atlas Colour Preset.json',filetypes=[('JSON','*.json')])
  if path:
   try:write_preset(path,self.settings())
   except Exception as e:messagebox.showerror('Preset export',str(e),parent=self)
 def apply(self):
  try:self.app.vars['colour_json'].set(json.dumps(self.settings()));self.app.save();self.app.preview();self.app.video.show_compare();self.close()
  except Exception as e:messagebox.showerror('Colour settings',str(e),parent=self)
 def close(self):
  self.counter+=1
  for attr in ('timer','poll_id'):
   if hasattr(self,attr):
    try:self.after_cancel(getattr(self,attr))
    except tk.TclError:pass
  if self.executor:self.executor.shutdown(wait=False,cancel_futures=True)
  self.destroy()
