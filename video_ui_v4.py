import json
from dataclasses import asdict,replace
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox,colorchooser
import numpy as np
from PIL import Image,ImageTk
from video_ui import VideoPanel as V3
from video_effects import Effects,mask_frame,pose,process_clip,plan_transforms,apply_transform
from colour_video import export_colour_loop
from legacy_ui import DATA

class EffectsDialog(tk.Toplevel):
    def __init__(self,panel):
        super().__init__(panel);self.panel=panel;self.title('Stabilization • Smart Aim Mask • Background');self.geometry('1050x820');self.configure(bg='#111111');self.transient(panel.app)
        s=panel.saved_effects;self.flags={k:tk.BooleanVar(value=getattr(s,k)) for k in ('stabilize','smart_aim','remove_background')};self.transparent=tk.BooleanVar(value=s.background=='transparent')
        self.v={k:tk.StringVar(value=str(getattr(s,k))) for k in ('key_color','background','tolerance','feather','strength','smoothing','max_shift','max_angle','border_crop','edge','target_x','target_y')}
        if s.background=='transparent':self.v['background'].set('#ffffff')
        self.roi=[tk.StringVar(value=str(round(n,5))) for n in s.roi]
        footer=ttk.Frame(self,padding=12);footer.pack(side='bottom',fill='x')
        ttk.Button(footer,text='Preview initial mask / vertical aim',command=self.preview).pack(side='left');ttk.Button(footer,text='Apply to all frames',style='Gold.TButton',command=self.apply).pack(side='right')
        body=ttk.Frame(self,padding=16);body.pack(fill='both',expand=True)
        group=ttk.LabelFrame(body,text='01 / TRACK & STABILIZE',padding=10);group.pack(fill='x',pady=5)
        for k,label in [('stabilize','Smooth position jitter (preserves deliberate rotation)'),('smart_aim','Smart Aim Mask: keep measured tool axis vertical at the initial target')]:ttk.Checkbutton(group,text=label,variable=self.flags[k]).pack(anchor='w')
        row=ttk.Frame(group);row.pack(fill='x',pady=7)
        for k,label in [('strength','Strength %'),('smoothing','Smooth seconds'),('max_shift','Max shift %'),('max_angle','Max aim angle °'),('border_crop','Safety crop %')]:ttk.Label(row,text=label).pack(side='left',padx=(0,4));ttk.Entry(row,textvariable=self.v[k],width=6).pack(side='left',padx=(0,12))
        ttk.Label(group,text='Precision shaft lock overrides these tracking modes when enabled. All modes use rigid 2D alignment.',foreground='#aaaaaa').pack(anchor='w')
        self.axis_lock=tk.BooleanVar(value=s.axis_lock)
        ttk.Checkbutton(group,text='Keep precision shaft lock enabled (edit its band from the video toolbar)',variable=self.axis_lock).pack(anchor='w')
        group=ttk.LabelFrame(body,text='02 / SET THE INITIAL TOOL TARGET',padding=10);group.pack(fill='x',pady=5)
        ttk.Label(group,text='Tracking rectangle: normalized X, Y, Width, Height (0–1). Include the entire tool and its movement.').pack(anchor='w')
        row=ttk.Frame(group);row.pack(fill='x',pady=6)
        for label,var in zip(('X','Y','Width','Height'),self.roi):ttk.Label(row,text=label).pack(side='left',padx=(0,5));ttk.Entry(row,textvariable=var,width=7).pack(side='left',padx=(0,12))
        row=ttk.Frame(group);row.pack(fill='x')
        for k,label in [('target_x','Target X (0–1)'),('target_y','Target Y (0–1)')]:ttk.Label(row,text=label).pack(side='left');ttk.Entry(row,textvariable=self.v[k],width=7).pack(side='left',padx=7)
        ttk.Button(row,text='Capture initial tool location',command=self.capture).pack(side='left',padx=10)
        ttk.Label(group,text='−1 automatically uses the initial measured centre. Short/round silhouettes skip axis correction.',foreground='#aaaaaa').pack(anchor='w',pady=4)
        group=ttk.LabelFrame(body,text='03 / SMART BACKGROUND MASK',padding=10);group.pack(fill='x',pady=5)
        ttk.Checkbutton(group,text='Remove background in every frame',variable=self.flags['remove_background']).pack(anchor='w')
        row=ttk.Frame(group);row.pack(fill='x',pady=5)
        for key,label in [('key_color','Original background'),('background','Replacement colour')]:
            ttk.Label(row,text=label).pack(side='left');ttk.Entry(row,textvariable=self.v[key],width=9).pack(side='left',padx=5);ttk.Button(row,text='Choose',command=lambda k=key:self.choose(k)).pack(side='left',padx=(0,10))
        ttk.Checkbutton(row,text='Transparent',variable=self.transparent).pack(side='left')
        row=ttk.Frame(group);row.pack(fill='x',pady=4)
        for key,label in [('tolerance','Colour tolerance'),('feather','Feather px'),('edge','Processing edge px')]:ttk.Label(row,text=label).pack(side='left');ttk.Entry(row,textvariable=self.v[key],width=7).pack(side='left',padx=8)
        ttk.Label(group,text='Colour-seeded segmentation keeps the largest target silhouette and fills interior highlights.\nWorks best with a plain, contrasting background. Inspect reflective edges and other objects.',foreground='#aaaaaa').pack(anchor='w',pady=4)
        self.canvas=tk.Canvas(body,height=210,bg='#080808',highlightthickness=0);self.canvas.pack(fill='both',expand=True,pady=8)
        self.note=ttk.Label(body,text='Preview shows original / first-frame mask / vertical target. Transparent output uses ProRes 4444 MOV.');self.note.pack(side='bottom',anchor='w',before=self.canvas)
    def choose(self,key):
        c=colorchooser.askcolor(self.v[key].get(),parent=self)[1]
        if c:self.v[key].set(c)
    def settings(self):
        s=replace(self.panel.saved_effects,**{k:v.get() for k,v in self.flags.items()},**{k:(int(v.get()) if k=='edge' else v.get() if k in ('key_color','background') else float(v.get())) for k,v in self.v.items()},roi=tuple(float(v.get()) for v in self.roi),axis_lock=self.axis_lock.get())
        if self.transparent.get():s.background='transparent'
        s.validate();return s
    def capture(self):
        try:
            s=self.settings();im=np.asarray(self.panel.original.frame(0));p=pose(mask_frame(im,s))
            if p is None:raise ValueError('No tool found. Adjust the mask controls or tracking rectangle.')
            self.v['target_x'].set(str(round(p[0][0]/im.shape[1],5)));self.v['target_y'].set(str(round(p[0][1]/im.shape[0],5)));self.preview()
        except Exception as e:messagebox.showerror('Initial target',str(e),parent=self)
    def preview(self):
        try:
            s=self.settings();rgb=np.asarray(self.panel.original.frame(0));alpha=mask_frame(rgb,s);p=pose(alpha)
            if p is None:raise ValueError('No target found. Adjust key colour, tolerance or rectangle.')
            from dataclasses import replace
            aim=replace(s,smart_aim=True);matrices,_=plan_transforms([p],(rgb.shape[1],rgb.shape[0]),self.panel.original.fps,aim)
            ideal=Image.fromarray(apply_transform(rgb,alpha,matrices[0],'#404040',s.key_color)).convert('RGB')
            ims=[Image.fromarray(rgb),Image.fromarray((alpha*255).astype('uint8')).convert('RGB'),ideal];self.photos=[];self.canvas.delete('all');w=max(600,self.canvas.winfo_width());h=max(120,self.canvas.winfo_height())
            for i,(label,im) in enumerate(zip(('ORIGINAL','MASK','VERTICAL TARGET'),ims)):
                im.thumbnail((w//3-16,h-28));ph=ImageTk.PhotoImage(im);self.photos.append(ph);self.canvas.create_text((i+.5)*w/3,12,text=label,fill='#f5a900');self.canvas.create_image((i+.5)*w/3,h/2+10,image=ph)
            self.note.configure(text=f'Initial axis {p[1]:.2f}° from vertical; centre {p[0][0]:.1f}, {p[0][1]:.1f} proxy px. Max-angle safety limit applies.')
        except Exception as e:messagebox.showerror('Mask preview',str(e),parent=self)
    def apply(self):
        try:s=self.settings()
        except Exception as e:messagebox.showerror('Effects settings',str(e),parent=self);return
        self.panel.apply_effects(s);self.destroy()

class VideoPanel(V3):
    def __init__(self,parent,app):
        super().__init__(parent,app);self.original=None;self.processed=None
        try:self.saved_effects=Effects(**json.loads((DATA/'video-effects.json').read_text()))
        except (OSError,ValueError,TypeError):self.saved_effects=Effects()
        self.toolbar=ttk.Frame(self,padding=(10,3));self.toolbar.pack(fill='x',before=self.winfo_children()[0])
        ttk.Button(self.toolbar,text='Precision shaft lock',style='Gold.TButton',command=self.shaft_dialog).pack(side='left')
        ttk.Button(self.toolbar,text='Stabilization / Background',command=self.effects_dialog).pack(side='left',padx=5);ttk.Button(self.toolbar,text='Original / processed',command=self.use_original).pack(side='left',padx=5)
        self.effect_status=ttk.Label(self.toolbar,text='Original video • effects not applied',foreground='#f5a900');self.effect_status.pack(side='left',padx=12)
        self.pass_toolbar=ttk.Frame(self,padding=(10,3));self.pass_toolbar.pack(fill='x',after=self.toolbar)
        ttk.Button(self.pass_toolbar,text='Second pass on processed video…',command=self.second_dialog).pack(side='left')
        ttk.Button(self.pass_toolbar,text='Compare first / second pass',command=self.compare_passes).pack(side='left',padx=8)
        self.axis_status=ttk.Label(self.pass_toolbar,text='',foreground='#aaaaaa');self.axis_status.pack(side='left',padx=8)
    def shaft_dialog(self):
        if not self.clip or self.app.busy:return
        self.stop()
        if self.original is None:self.original=self.clip
        from shaft_ui import ShaftDialog
        ShaftDialog(self)
    def effects_dialog(self):
        if not self.clip or self.app.busy:return
        if self.original is None:self.original=self.clip
        EffectsDialog(self)
    def apply_effects(self,s):
        if self.app.busy:return
        self.stop();original=self.original or self.clip;self.original=original
        self.app.run_job('Tracking and processing all frames before loop matching…',lambda:process_clip(original,s,lambda m:self.app.events.put(('log',m))),lambda clip:self.accept_processed(clip,s))
    def accept_processed(self,clip,s):
        if self.processed and getattr(clip,'first_pass',None) is not self.processed:self.processed.close()
        self.processed=clip;self.clip=clip;self.saved_effects=s;(DATA/'video-effects.json').write_text(json.dumps(asdict(s),indent=2));self.results.delete(*self.results.get_children());self.candidates=[];self.reset_crop()
        shaft=clip.effect_report.get('shaft_lock');second=clip.effect_report.get('second_pass')
        tracking=(shaft or {}).get('advanced_tracking',{})
        self.axis_status.configure(text=(f'{s.axis_strategy} • {s.render_quality} • {tracking.get("fallback_frames",0)} mask fallbacks' if tracking else '')+(' • fixed vertical finish' if second and s.second_mode=='lock' else ''))
        self.effect_status.configure(text=('Two passes' if second else 'Shaft lock' if shaft else 'Processed')+f' • {clip.effect_report["tracked_frames"]}/{clip.count} tracked')
        self.app.status.set('Effects applied. Find loop points again using the processed footage.');self.show_compare()
        limited=(shaft or {}).get('safety_limited_frames',0)+(second or {}).get('safety_limited_frames',0)
        if limited:messagebox.showwarning('Stabilization safety limits',f'{limited} frame-limit events were recorded across the passes. Some movement may remain. Review the result and adjust the limits if needed.')
    def second_dialog(self):
        if self.app.busy:return
        if self.processed is None or not self.processed.effects.axis_lock:
            messagebox.showinfo('Second pass','Apply Precision shaft lock first. The second pass reads that processed video.');return
        if self.processed.effect_report.get('second_pass'):
            messagebox.showinfo('Second pass','Second pass is already applied. Use Compare first / second pass to inspect it. Reapply shaft lock to change its settings.');return
        self.stop()
        from jitter_ui import JitterDialog
        JitterDialog(self)
    def apply_second_pass(self,s):
        if self.app.busy or self.processed is None:return
        from jitter_pass import second_pass_clip
        self.stop();first=self.processed
        self.app.run_job('Second pass: analysing the completed first-pass video…',lambda:second_pass_clip(first,s,lambda m:self.app.events.put(('log',m))),lambda clip:self.accept_processed(clip,s))
    def compare_passes(self):
        if self.app.busy:return
        first=getattr(self.processed,'first_pass',None)
        if first is None:
            messagebox.showinfo('Compare passes','Complete both passes first.');return
        self.stop();self.clip=first if self.clip is self.processed else self.processed
        self.results.delete(*self.results.get_children());self.candidates=[];self.reset_crop()
        self.effect_status.configure(text='First pass only' if self.clip is first else 'Second pass • final processed video');self.show_compare()
    def use_original(self):
        if self.app.busy or self.original is None:return
        self.stop()
        self.clip=self.processed if self.clip is self.original and self.processed else self.original
        self.results.delete(*self.results.get_children());self.candidates=[];self.reset_crop()
        self.effect_status.configure(text='Original video' if self.clip is self.original else 'Processed video • effects applied')
        self.show_compare()
    def open(self):
        if self.app.busy:return
        path=filedialog.askopenfilename(title='Open original rotating product video',filetypes=[('Video','*.mp4 *.mov *.m4v *.avi *.mkv *.webm')])
        if not path:return
        self.stop()
        from video_core import VideoClip
        def done(clip):
            for old in {self.clip,self.original,self.processed}:
                if old:old.close()
            self.processed=None;self.original=clip;self.clip=clip;self.path.set(clip.path);self.start.set('0');self.end.set(str(min(clip.count-1,max(2,round(7*clip.fps)))));self.reset_crop();self.results.delete(*self.results.get_children());self.candidates=[]
            self.effect_status.configure(text='Original video • effects not applied');self.info.set(f'{clip.size[0]} x {clip.size[1]} • {clip.duration:.2f}s • {clip.fps:.4f} fps. Apply effects before finding loop points.');self.show_compare()
            self.axis_status.configure(text='')
        self.app.run_job('Preparing original video proxies…',lambda:VideoClip(path,lambda m:self.app.events.put(('log',m))),done)
    def export(self):
        if self.app.busy:return
        try:
            a,b=self.bounds();crop=tuple(int(self.crop[k].get()) for k in ('X','Y','Width','Height'));edge=int(self.edge.get());lx=int(self.logo_x.get());ly=int(self.logo_y.get());lw=float(self.logo_width.get());opacity=float(self.opacity.get());logo=self.app.vars['logo_path'].get() if self.logo_on.get() else ''
            if self.logo_on.get() and not Path(logo).is_file():raise ValueError('Choose the default logo or disable the logo overlay.')
        except ValueError as e:messagebox.showerror('Video export',str(e));return
        transparent=bool(getattr(self.clip,'effects',None) and self.clip.effects.remove_background and self.clip.effects.background=='transparent');ext='.mov' if transparent else '.mp4'
        dest=filedialog.asksaveasfilename(title='Export loop with alpha' if transparent else 'Export loop',defaultextension=ext,initialfile=Path(getattr(self.clip,'original_source',self.clip.path)).stem+' - LOOP'+ext,filetypes=[('ProRes 4444 MOV' if transparent else 'H.264 MP4','*'+ext)])
        if not dest:return
        self.stop();clip=self.clip
        recipe=self.app.vars['colour_json'].get()
        self.app.run_job('Grading, exporting and verifying loop…',lambda:export_colour_loop(clip,a,b,dest,recipe,crop,edge,logo,lw,lx,ly,opacity,progress=lambda m:self.app.events.put(('log',m))),lambda info:self.app.status.set(f'Exported {dest} • {info["output_frames"]} frames • {info["bytes"]/1e6:.2f} MB'))
    def close(self):
        for old in {self.original,self.processed}:
            if old and old is not self.clip:old.close()
        super().close()
