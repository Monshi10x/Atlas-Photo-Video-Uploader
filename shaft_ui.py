"""Interactive precision-shaft band selection and reusable effects presets."""
import json
from dataclasses import replace,asdict
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import numpy as np
from PIL import Image,ImageTk
import imageio_ffmpeg as ffmpeg
from shaft_tracking import shaft_pose
from video_effects import Effects
from jitter_ui import JitterControls
from advanced_axis import STRATEGIES,geometry,AxisTracker


class ShaftDialog(tk.Toplevel):
    def __init__(self,panel):
        super().__init__(panel);self.panel=panel;self.clip=panel.original or panel.clip
        self.title('Advanced verticality • geometry masks • two-pass stabilization');self.geometry('1120x950');self.transient(panel.app)
        self.s=replace(panel.saved_effects);self.s.axis_lock=True
        self.s.strength=100;self.s.target_x=self.s.target_y=-1
        self.band=tuple(self.s.axis_roi);self.drag=None;self.index=tk.StringVar(value='0')
        self.v={k:tk.StringVar(value=str(getattr(self.s,k))) for k in ('axis_contrast','tracking_edge','strength','max_angle','max_shift','axis_reference','axis_mask_min_score')}
        self.strategy=tk.StringVar(value=STRATEGIES[self.s.axis_strategy]);self.quality=tk.StringVar(value=self.s.render_quality)
        self.keep_background=tk.BooleanVar(value=not self.s.remove_background)
        foot=ttk.Frame(self,padding=12);foot.pack(side='bottom',fill='x')
        ttk.Button(foot,text='Import settings',command=self.load).pack(side='left');ttk.Button(foot,text='Export settings',command=self.save).pack(side='left',padx=8)
        ttk.Button(foot,text='Apply shaft lock to all frames',style='Gold.TButton',command=self.apply).pack(side='right')
        body=ttk.Frame(self,padding=14);body.pack(fill='both',expand=True)
        ttk.Label(body,text='01 / DRAW A BAND AROUND THE STRAIGHT SHANK',font=('Segoe UI',13,'bold')).pack(anchor='w')
        ttk.Label(body,text='Drag a rectangle on the image. Include a long straight section, with clear background on both sides.\nExclude the flutes, tip, base, shadow and logo. The band must contain the shaft throughout the rotation.').pack(anchor='w',pady=7)
        self.canvas=tk.Canvas(body,bg='#181818',height=380,highlightthickness=0);self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda e:self.draw());self.canvas.bind('<ButtonPress-1>',self.start_drag);self.canvas.bind('<B1-Motion>',self.move_drag);self.canvas.bind('<ButtonRelease-1>',self.end_drag)
        self.note=ttk.Label(body,text='');self.note.pack(anchor='w',pady=5)
        row=ttk.Frame(body);row.pack(fill='x',pady=5)
        ttk.Label(row,text='Inspect frame').pack(side='left');ttk.Spinbox(row,from_=0,to=self.clip.count-1,textvariable=self.index,width=7).pack(side='left',padx=6)
        ttk.Button(row,text='Show frame',command=self.show).pack(side='left')
        ttk.Checkbutton(row,text='Keep original background (disable background removal)',variable=self.keep_background).pack(side='left',padx=16)
        tabs=ttk.Notebook(body);tabs.pack(fill='x',pady=7)
        basic=ttk.Frame(tabs,padding=10);advanced=ttk.Frame(tabs,padding=10);second=ttk.Frame(tabs,padding=5)
        tabs.add(basic,text='02 / Axis lock');tabs.add(advanced,text='02 / Advanced strategy');tabs.add(second,text='03 / Second pass')
        ttk.Label(basic,text='LOCK TO A FIXED VERTICAL AXIS',font=('Segoe UI',12,'bold')).pack(anchor='w',pady=6)
        row=ttk.Frame(basic);row.pack(fill='x')
        for k,label in [('axis_contrast','Edge contrast'),('tracking_edge','Tracking px'),('strength','Lock %'),('max_angle','Max angle °'),('max_shift','Max shift %')]:
            ttk.Label(row,text=label).pack(side='left');ttk.Entry(row,textvariable=self.v[k],width=6).pack(side='left',padx=(4,12))
        ttk.Button(row,text='Check band',command=self.draw).pack(side='left')
        ttk.Label(basic,text='100% locks the measured axis. The reference frame supplies the fixed target position.\nPreserves spin and size. Does not reconstruct depth tilt, bending or changing tip height. Add the logo afterwards.').pack(anchor='w',pady=8)
        row=ttk.Frame(advanced);row.pack(fill='x',pady=4)
        ttk.Label(row,text='Tracking strategy').pack(side='left');ttk.Combobox(row,textvariable=self.strategy,values=list(STRATEGIES.values()),state='readonly',width=34).pack(side='left',padx=8)
        ttk.Label(row,text='Resampling').pack(side='left');ttk.Combobox(row,textvariable=self.quality,values=('fast','subpixel','cubic'),state='readonly',width=8).pack(side='left',padx=8)
        ttk.Button(row,text='Use advanced recommended',command=self.recommended).pack(side='left',padx=8)
        row=ttk.Frame(advanced);row.pack(fill='x',pady=6)
        ttk.Label(row,text='Reference frame').pack(side='left');ttk.Entry(row,textvariable=self.v['axis_reference'],width=7).pack(side='left',padx=7)
        ttk.Button(row,text='Capture shown frame / preview masks',command=self.capture_reference).pack(side='left',padx=7)
        ttk.Label(row,text='Min mask score').pack(side='left');ttk.Entry(row,textvariable=self.v['axis_mask_min_score'],width=7).pack(side='left',padx=7)
        ttk.Label(advanced,text='Robust: several edge thresholds + band consensus. Reference: align each mask to a captured vertical ideal.\nHybrid: combine both, falling back to robust geometry when registration is unreliable. No accumulated tracking drift.\nUse only the stable shank. Subpixel = precise linear; cubic = precise, sharper and slower.').pack(anchor='w',pady=5)
        self.jitter=JitterControls(second,self.s);self.jitter.pack(fill='x',pady=4)
        self.rgb=None;self.show()

    def settings(self):
        updates={k:int(v.get()) if k in ('tracking_edge','axis_reference') else float(v.get()) for k,v in self.v.items()}
        strategy=next(k for k,v in STRATEGIES.items() if v==self.strategy.get())
        s=replace(self.s,**updates,**self.jitter.values(),axis_strategy=strategy,render_quality=self.quality.get(),axis_roi=tuple(self.band),axis_lock=True,smart_aim=False,stabilize=False,remove_background=not self.keep_background.get(),target_x=-1,target_y=-1)
        s.validate();return s

    def recommended(self):
        self.strategy.set(STRATEGIES['hybrid']);self.quality.set('subpixel');self.v['axis_mask_min_score'].set('.98')
        self.jitter.enabled.set(True);self.jitter.mode.set('lock');self.jitter.v['second_strength'].set('100');self.jitter.v['second_max_shift'].set('1');self.jitter.v['second_max_angle'].set('.5');self.draw()

    def capture_reference(self):
        try:
            self.v['axis_reference'].set(self.index.get());s=self.settings();tracker=AxisTracker(self.rgb,s)
            dialog=tk.Toplevel(self);dialog.title('Captured geometric mask and vertical ideal');dialog.geometry('940x430');dialog.transient(self)
            ttk.Label(dialog,text=f'Reference frame {s.axis_reference}. Each later frame is compared to this fixed ideal within the selected band.',padding=10).pack(anchor='w')
            row=ttk.Frame(dialog);row.pack(fill='both',expand=True);dialog.photos=[]
            x,y,rw,rh=self.band;h,w=self.rgb.shape[:2]
            images=[Image.fromarray(self.rgb).crop((round(x*w),round(y*h),round((x+rw)*w),round((y+rh)*h))),Image.fromarray(np.rint(tracker.reference[1]*255).astype('uint8')),Image.fromarray(np.rint(np.clip(tracker.template,0,1)*255).astype('uint8'))]
            for label,im in zip(('SOURCE SHANK','CAPTURED GEOMETRY','VERTICAL IDEAL'),images):
                box=ttk.Frame(row,padding=10);box.pack(side='left',fill='both',expand=True);ttk.Label(box,text=label).pack();preview=im.copy();preview.thumbnail((260,300));photo=ImageTk.PhotoImage(preview);dialog.photos.append(photo);ttk.Label(box,image=photo).pack()
            def save():
                path=filedialog.asksaveasfilename(parent=dialog,defaultextension='.png',initialfile='Vertical_ideal_mask.png',filetypes=[('PNG mask','*.png')])
                if path:
                    try:images[-1].save(path)
                    except OSError as e:messagebox.showerror('Save mask',str(e),parent=dialog)
            ttk.Button(dialog,text='Save ideal mask PNG…',command=save).pack(side='bottom',pady=8)
        except Exception as e:messagebox.showerror('Reference mask',str(e),parent=self)

    def show(self):
        try:
            i=int(self.index.get())
            if not 0<=i<self.clip.count:raise ValueError('Frame is outside the clip.')
            # Decode source pixels rather than the 256 px navigation proxy.
            ratio=min(1,1080/max(self.clip.size));w,h=(max(2,round(v*ratio)) for v in self.clip.size)
            reader=ffmpeg.read_frames(self.clip.path,pix_fmt='rgb24',output_params=['-vf',f'fps={self.clip.fps:.8f},select=eq(n\\,{i}),scale={w}:{h}','-vsync','0','-frames:v','1','-an']);next(reader)
            try:self.rgb=np.frombuffer(next(reader),np.uint8).reshape(h,w,3).copy()
            finally:reader.close()
            self.draw()
        except Exception as e:messagebox.showerror('Shaft preview',str(e),parent=self)

    def draw(self):
        if getattr(self,'rgb',None) is None:return
        self.canvas.delete('all');h,w=self.rgb.shape[:2];cw=max(100,self.canvas.winfo_width());ch=max(100,self.canvas.winfo_height())
        scale=min(cw/w,ch/h);dw,dh=max(1,round(w*scale)),max(1,round(h*scale));ox,oy=(cw-dw)/2,(ch-dh)/2;self.display=(ox,oy,dw,dh)
        self.photo=ImageTk.PhotoImage(Image.fromarray(self.rgb).resize((dw,dh),Image.Resampling.BILINEAR));self.canvas.create_image(ox,oy,anchor='nw',image=self.photo)
        x,y,rw,rh=self.band;self.canvas.create_rectangle(ox+x*dw,oy+y*dh,ox+(x+rw)*dw,oy+(y+rh)*dh,outline='#f5a900',width=2)
        try:
            if self.strategy.get()==STRATEGIES['legacy']:p=shaft_pose(self.rgb,self.band,float(self.v['axis_contrast'].get()))
            else:
                g=geometry(self.rgb,self.band,float(self.v['axis_contrast'].get()));p=g[0] if g else None
            if p is None:self.note.configure(text='No reliable straight axis found. Use a longer, wider band or lower edge contrast.');return
            center,angle,coverage=p;slope=np.tan(np.radians(angle))
            coords=[]
            for sy in (0,h):coords.extend((ox+(center[0]+(sy-center[1])*slope)*dw/w,oy+sy*dh/h))
            self.canvas.create_line(*coords,fill='#00dc95',width=2)
            metric='rows tracked' if self.strategy.get()==STRATEGIES['legacy'] else 'geometry confidence (edge preview)'
            self.note.configure(text=f'Frame {self.index.get()}: axis {angle:+.3f}° from vertical • {coverage:.0%} {metric} • band {tuple(round(v,4) for v in self.band)}')
        except ValueError:self.note.configure(text='Enter a numeric edge contrast.')

    def point(self,e):
        ox,oy,dw,dh=self.display
        return (min(1,max(0,(e.x-ox)/dw)),min(1,max(0,(e.y-oy)/dh)))
    def start_drag(self,e):
        if hasattr(self,'display'):self.drag=self.point(e)
    def move_drag(self,e):
        if self.drag is None:return
        x,y=self.point(e);a,b=self.drag
        self.band=(min(a,x),min(b,y),max(.001,abs(x-a)),max(.001,abs(y-b)));self.draw()
    def end_drag(self,e):self.move_drag(e);self.drag=None

    def load(self):
        path=filedialog.askopenfilename(parent=self,filetypes=[('Atlas shaft settings','*.json')])
        if not path:return
        try:
            from pathlib import Path
            p=Path(path)
            if p.stat().st_size>100000:raise ValueError('Settings file is too large.')
            data=json.loads(p.read_text(encoding='utf-8'))
            if data.get('format')!='atlas-shaft-lock' or data.get('version')!=1:raise ValueError('Choose an Atlas shaft-lock settings file.')
            s=Effects(**data['settings']);s.validate();self.s=s;self.band=tuple(s.axis_roi)
            for k,v in self.v.items():v.set(str(getattr(s,k)))
            self.jitter.load(s)
            self.strategy.set(STRATEGIES[s.axis_strategy]);self.quality.set(s.render_quality)
            self.keep_background.set(not s.remove_background);self.draw()
        except Exception as e:messagebox.showerror('Import settings',str(e),parent=self)
    def save(self):
        try:s=self.settings()
        except Exception as e:messagebox.showerror('Settings',str(e),parent=self);return
        path=filedialog.asksaveasfilename(parent=self,defaultextension='.json',initialfile='Shaft_lock.json',filetypes=[('Atlas shaft settings','*.json')])
        if not path:return
        try:
            from pathlib import Path
            Path(path).write_text(json.dumps({'format':'atlas-shaft-lock','version':1,'settings':asdict(s)},indent=2),encoding='utf-8')
        except OSError as e:messagebox.showerror('Export settings',str(e),parent=self)
    def apply(self):
        try:s=self.settings()
        except Exception as e:messagebox.showerror('Shaft settings',str(e),parent=self);return
        self.panel.apply_effects(s);self.destroy()
