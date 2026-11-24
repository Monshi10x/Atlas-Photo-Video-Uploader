import math,queue,time
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from PIL import Image,ImageTk,ImageChops,ImageDraw
from video_core import VideoClip,export_loop
from core import load_proxy
GOLD='#f5a900'

class VideoPanel(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent,padding=12);self.app=app;self.clip=None;self.candidates=[];self.playing=False;self.play_id=None;self.images=[]
        self.path=tk.StringVar();self.target=tk.StringVar(value='7');self.tolerance=tk.StringVar(value='1.5');self.start=tk.StringVar(value='0');self.end=tk.StringVar(value='210');self.fixed_start=tk.BooleanVar(value=False)
        self.logo_on=tk.BooleanVar(value=True);self.logo_x=tk.StringVar(value='24');self.logo_y=tk.StringVar(value='24');self.logo_width=tk.StringVar(value='18');self.opacity=tk.StringVar(value='100');self.edge=tk.StringVar(value='1080')
        self.crop={k:tk.StringVar(value='0') for k in ('X','Y','Width','Height')};self.info=tk.StringVar(value='Open a rotating product video. Analysis and export run locally.')
        top=self.group(self,'01 / OPEN VIDEO & FIND A ROTATION');top.pack(fill='x',pady=(0,8))
        row=ttk.Frame(top);row.pack(fill='x');ttk.Entry(row,textvariable=self.path,state='readonly').pack(side='left',fill='x',expand=True);ttk.Button(row,text='Open video',command=self.open).pack(side='left',padx=8)
        row=ttk.Frame(top);row.pack(fill='x',pady=7)
        for label,var in [('Target seconds',self.target),('Search ± seconds',self.tolerance)]:ttk.Label(row,text=label).pack(side='left',padx=(0,5));ttk.Entry(row,textvariable=var,width=6).pack(side='left',padx=(0,12))
        ttk.Checkbutton(row,text='Keep current start frame',variable=self.fixed_start).pack(side='left');ttk.Button(row,text='Find best loop points',style='Gold.TButton',command=self.find).pack(side='right')
        ttk.Label(top,textvariable=self.info,foreground='#aaaaaa',wraplength=1250).pack(anchor='w')
        body=ttk.Panedwindow(self,orient='horizontal');body.pack(fill='both',expand=True)
        left=self.group(body,'02 / COMPARE CANDIDATES');right=self.group(body,'03 / CHECK THE JOIN');body.add(left,weight=1);body.add(right,weight=3)
        self.results=ttk.Treeview(left,columns=('duration','frames','error'),show='headings',height=7,selectmode='browse')
        for key,label,width in [('duration','Seconds',70),('frames','Start → return',130),('error','Error ↓',75)]:self.results.heading(key,text=label);self.results.column(key,width=width)
        self.results.pack(fill='both',expand=True);self.results.bind('<<TreeviewSelect>>',self.choose)
        ttk.Label(left,text='Lower error = closer visual/motion match.\nSymmetrical tools can give ambiguous matches.\nReview the seam before export.',foreground='#aaaaaa').pack(anchor='w',pady=10)
        row=ttk.Frame(right);row.pack(fill='x')
        for label,var in [('Start frame',self.start),('Matching return frame',self.end)]:
            ttk.Label(row,text=label).pack(side='left',padx=(0,4));ttk.Entry(row,textvariable=var,width=7).pack(side='left')
            for text,delta in [('−1',-1),('+1',1)]:ttk.Button(row,text=text,width=3,command=lambda v=var,d=delta:self.nudge(v,d)).pack(side='left',padx=2)
        self.canvas=tk.Canvas(right,height=270,bg='#080808',highlightthickness=0);self.canvas.pack(fill='both',expand=True,pady=8);self.canvas.bind('<Configure>',lambda e:self.show_compare())
        self.detail=ttk.Label(right,text='Start • matching return (excluded) • amplified difference',foreground='#aaaaaa');self.detail.pack(anchor='w')
        row=ttk.Frame(right);row.pack(fill='x',pady=7)
        for text,cmd in [('Play across join',lambda:self.play(True)),('Play whole loop',lambda:self.play(False)),('Stop / compare',self.stop)]:ttk.Button(row,text=text,command=cmd).pack(side='left',padx=(0,8))
        out=self.group(self,'04 / CROP, BRAND & EXPORT MP4');out.pack(side='bottom',fill='x',pady=(8,0),before=body)
        row=ttk.Frame(out);row.pack(fill='x',pady=4);ttk.Label(row,text='Spatial crop (source px)').pack(side='left',padx=(0,10))
        for key,var in self.crop.items():ttk.Label(row,text=key).pack(side='left',padx=(0,4));ttk.Entry(row,textvariable=var,width=6).pack(side='left',padx=(0,10))
        ttk.Label(row,text='Output edge px').pack(side='left',padx=(10,4));ttk.Entry(row,textvariable=self.edge,width=6).pack(side='left')
        ttk.Button(row,text='Reset full frame',command=self.reset_crop).pack(side='left',padx=10)
        row=ttk.Frame(out);row.pack(fill='x',pady=4);ttk.Checkbutton(row,text='Add default Atlas logo',variable=self.logo_on,command=self.show_compare).pack(side='left')
        for label,var in [('X px',self.logo_x),('Y px',self.logo_y),('Width %',self.logo_width),('Opacity %',self.opacity)]:ttk.Label(row,text=label).pack(side='left',padx=(10,4));ttk.Entry(row,textvariable=var,width=6).pack(side='left')
        ttk.Label(out,text='Uses the logo file set in Photo workspace. Logo X/Y are OUTPUT pixels; crop fields are SOURCE pixels. MP4 export is silent H.264.',foreground='#aaaaaa').pack(anchor='w',pady=4)
        row=ttk.Frame(out);row.pack(fill='x',pady=5);ttk.Button(row,text='Export looping MP4',style='Gold.TButton',command=self.export).pack(side='left');ttk.Label(row,text='The matching return frame is excluded to prevent a repeated-frame pause.',foreground=GOLD).pack(side='left',padx=15)
        for var in (self.start,self.end,*self.crop.values(),self.logo_x,self.logo_y,self.logo_width,self.opacity,self.edge):var.trace_add('write',lambda *a:self.schedule_compare())
    def group(self,parent,title):return ttk.LabelFrame(parent,text=title,padding=10,style='Step.TLabelframe')
    def open(self):
        if self.app.busy:return
        path=filedialog.askopenfilename(title='Open rotating product video',filetypes=[('Video','*.mp4 *.mov *.m4v *.avi *.mkv *.webm')])
        if not path:return
        self.stop()
        def done(clip):
            if self.clip:self.clip.close()
            self.clip=clip;self.path.set(clip.path);self.start.set('0');self.end.set(str(min(clip.count-1,max(2,round(7*clip.fps)))));self.reset_crop();self.results.delete(*self.results.get_children());self.candidates=[]
            self.info.set(f'{clip.size[0]} × {clip.size[1]} px • {clip.duration:.2f}s • analysis/export grid {clip.fps:.4f} fps • {clip.count} frames. Choose target duration and find loop points.')
            self.show_compare();self.app.status.set('Video ready. Find candidates, then review the join.')
        self.app.run_job('Decoding low-resolution video proxies…',lambda:VideoClip(path,lambda m:self.app.events.put(('log',m))),done)
    def find(self):
        if not self.clip or self.app.busy:return
        self.stop()
        try:target=float(self.target.get());tol=float(self.tolerance.get());hint=int(self.start.get()) if self.fixed_start.get() else None
        except ValueError:messagebox.showerror('Loop search','Enter valid numbers.');return
        clip=self.clip
        def done(candidates):
            self.candidates=candidates;self.results.delete(*self.results.get_children())
            for i,c in enumerate(candidates):self.results.insert('','end',iid=str(i),values=(f'{c.seconds:.4f}',f'{c.start} → {c.end}',f'{c.error:.6f}'))
            self.results.selection_set('0');self.choose();self.app.status.set('Loop candidates ready. Compare and play across the join; nudge frames if needed.')
        self.app.run_job('Comparing rotation phases and motion around potential joins…',lambda:clip.find_loops(target,tol,hint),done)
    def choose(self,e=None):
        selected=self.results.selection()
        if selected:
            c=self.candidates[int(selected[0])];self.start.set(str(c.start));self.end.set(str(c.end));self.stop()
    def nudge(self,var,delta):
        if not self.clip:return
        try:var.set(str(max(0,min(self.clip.count-1,int(var.get())+delta))))
        except ValueError:pass
    def bounds(self):
        if not self.clip:raise ValueError('Open a video first.')
        a,b=int(self.start.get()),int(self.end.get());self.clip.validate_bounds(a,b);return a,b
    def reset_crop(self):
        if self.clip:
            for key,v in zip(('X','Y','Width','Height'),(0,0,*self.clip.size)):self.crop[key].set(str(v))
    def schedule_compare(self):
        if hasattr(self,'compare_id'):
            try:self.after_cancel(self.compare_id)
            except tk.TclError:pass
        self.compare_id=self.after(100,self.show_compare)
    def visual_frame(self,index):
        im=self.clip.rgba_frame(index) if hasattr(self.clip,'rgba_frame') else self.clip.frame(index);w,h=self.clip.size
        try:
            x,y,cw,ch=[int(self.crop[k].get()) for k in ('X','Y','Width','Height')]
            if x<0 or y<0 or cw<2 or ch<2 or x+cw>w or y+ch>h:return im
            im=im.crop((round(x/w*im.width),round(y/h*im.height),max(1,round((x+cw)/w*im.width)),max(1,round((y+ch)/h*im.height))))
            from colour import apply_colour
            im=apply_colour(im,self.app.vars['colour_json'].get())
            if self.logo_on.get() and Path(self.app.vars['logo_path'].get()).is_file():
                logo=load_proxy(self.app.vars['logo_path'].get());logo=logo.crop(logo.getbbox());edge=int(self.edge.get());sc=min(1,edge/max(cw,ch));ow=max(2,int(cw*sc)//2*2);oh=max(2,int(ch*sc)//2*2)
                lw=max(1,round(ow*float(self.logo_width.get())/100));lh=max(1,round(logo.height*lw/logo.width))
                if lh>oh:lw=max(1,round(lw*oh/lh));lh=oh
                lx=max(0,min(ow-lw,int(self.logo_x.get())));ly=max(0,min(oh-lh,int(self.logo_y.get())))
                logo=logo.resize((max(1,round(lw*im.width/ow)),max(1,round(lh*im.height/oh))))
                opacity=float(self.opacity.get());logo.putalpha(logo.getchannel('A').point(lambda a:round(a*max(0,min(100,opacity))/100)))
                im=im.convert('RGBA');im.alpha_composite(logo,(round(lx*im.width/ow),round(ly*im.height/oh)))
        except (ValueError,TypeError):pass
        if im.mode=='RGBA':
            import numpy as np
            yy,xx=np.indices((im.height,im.width));grey=np.where((xx//12+yy//12)%2,70,45).astype(np.uint8);bg=Image.fromarray(np.dstack((grey,grey,grey))).convert('RGBA');bg.alpha_composite(im);im=bg.convert('RGB')
        return im
    def show_compare(self):
        if not self.clip or self.playing:return
        try:a,b=self.bounds();first=self.visual_frame(a);last=self.visual_frame(b)
        except (ValueError,OSError):return
        diff=ImageChops.difference(first,last).point(lambda p:min(255,p*4));self.canvas.delete('all');self.images=[]
        width=max(240,self.canvas.winfo_width());height=max(150,self.canvas.winfo_height())
        for i,(label,im) in enumerate([('START (included)',first),('RETURN (excluded)',last),('DIFFERENCE ×4',diff)]):
            im.thumbnail((max(60,width//3-20),max(80,height-50)),Image.Resampling.BILINEAR);photo=ImageTk.PhotoImage(im);self.images.append(photo)
            cx=(i+.5)*width/3;self.canvas.create_text(cx,16,text=label,fill=GOLD);self.canvas.create_image(cx,height/2+10,image=photo)
        self.detail.configure(text=f'Frames [{a}, {b}) → {b-a} frames / {(b-a)/self.clip.fps:.4f}s • matching-frame RMS {self.clip.compare(a,b):.6f}. Check motion with Play across join.')
    def stop(self):
        self.playing=False
        if self.play_id:
            try:self.after_cancel(self.play_id)
            except tk.TclError:pass
            self.play_id=None
        self.show_compare()
    def play(self,seam):
        if not self.clip:return
        try:a,b=self.bounds()
        except ValueError as e:messagebox.showerror('Loop bounds',str(e));return
        self.stop();self.playing=True;self.play_start=time.perf_counter();self.play_frames=(list(range(max(a,b-12),b))+list(range(a,min(b,a+12)))) if seam else list(range(a,b))
        def tick():
            if not self.playing:return
            i=int((time.perf_counter()-self.play_start)*self.clip.fps)%len(self.play_frames)
            im=self.visual_frame(self.play_frames[i]);im.thumbnail((max(200,self.canvas.winfo_width()-30),max(120,self.canvas.winfo_height()-30)),Image.Resampling.BILINEAR)
            self.play_image=ImageTk.PhotoImage(im);self.canvas.delete('all');self.canvas.create_image(self.canvas.winfo_width()/2,self.canvas.winfo_height()/2,image=self.play_image)
            self.play_id=self.after(round(1000/min(self.clip.fps,30)),tick)
        tick()
    def export(self):
        if self.app.busy:return
        try:
            a,b=self.bounds();crop=tuple(int(self.crop[k].get()) for k in ('X','Y','Width','Height'));edge=int(self.edge.get());lx=int(self.logo_x.get());ly=int(self.logo_y.get());lw=float(self.logo_width.get());opacity=float(self.opacity.get());logo=self.app.vars['logo_path'].get() if self.logo_on.get() else ''
            if self.logo_on.get() and not Path(logo).is_file():raise ValueError('Choose the default logo in Photo workspace, or untick Add default Atlas logo.')
        except ValueError as e:messagebox.showerror('Video export',str(e));return
        destination=filedialog.asksaveasfilename(title='Export looping MP4 (new filename)',defaultextension='.mp4',initialfile=Path(self.clip.path).stem+' - LOOP.mp4',filetypes=[('MP4','*.mp4')])
        if not destination:return
        self.stop();clip=self.clip
        self.app.run_job('Encoding and verifying the looping MP4…',lambda:export_loop(clip,a,b,destination,crop,edge,logo,lw,lx,ly,opacity),lambda info:self.app.status.set(f'Video exported: {destination} • {info["output_frames"]} frames • {info["duration_seconds"]:.4f}s • {info["bytes"]/1e6:.2f} MB'))
    def close(self):
        self.stop()
        # Cancel on the widget that registered the callback, before the root
        # clears its own timers. Otherwise Tk may delete this command twice.
        if hasattr(self,'compare_id'):
            try:self.after_cancel(self.compare_id)
            except tk.TclError:pass
            del self.compare_id
        if self.clip:self.clip.close()
