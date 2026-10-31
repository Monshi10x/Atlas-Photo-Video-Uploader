"""Atlas Photo Studio v2 desktop workspace."""
import json, queue, threading, time
from pathlib import Path
from dataclasses import asdict
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw
from legacy_ui import App as BaseApp, CONFIG
from core import (Settings, SUPPORTED, load_proxy, render, source_size, canvas_size,
                  crop_for, logo_geometry, build_name, parse_blocks, remove_white)

GOLD='#f5a900'; BG='#050505'; PANEL='#111111'; INK='#ffffff'; MUTED='#a9a9a9'

class BlockEditor(tk.Toplevel):
    def __init__(self,app):
        super().__init__(app);self.app=app;self.title('Image names & alt text • Block builder');self.geometry('900x650');self.configure(bg=BG);self.transient(app)
        self.blocks={k:parse_blocks(app.vars[k].get()) for k in ('filename_blocks','alt_blocks')};self.trees={}
        ttk.Label(self,text='BUILD YOUR IMAGE NAMES',font=('Segoe UI',18,'bold'),foreground=GOLD).pack(anchor='w',padx=20,pady=(20,5))
        ttk.Label(self,text='Order blocks from left to right. Add text before the name for a prefix, or after it for a postfix.').pack(anchor='w',padx=20)
        tabs=ttk.Notebook(self);tabs.pack(fill='both',expand=True,padx=20,pady=14)
        for key,title in [('filename_blocks','Filename'),('alt_blocks','Alt text')]:
            frame=ttk.Frame(tabs,padding=12);tabs.add(frame,text=title)
            tree=ttk.Treeview(frame,columns=('on','type','text'),show='headings',selectmode='browse',height=8)
            for col,label,width in [('on','On',50),('type','Block type',130),('text','Custom text',450)]:tree.heading(col,text=label);tree.column(col,width=width)
            tree.pack(fill='both',expand=True);self.trees[key]=tree
            tree.bind('<Double-1>',lambda e,k=key:self.edit(k))
            tools=ttk.Frame(frame);tools.pack(side='bottom',fill='x',before=tree)
            bar=ttk.Frame(tools);bar.pack(fill='x',pady=10)
            for label,kind in [('Add custom text','text'),('Add basic name','name'),('Add sequence','sequence'),('Add view','view')]:
                ttk.Button(bar,text=label,command=lambda k=key,t=kind:self.add(k,t)).pack(side='left',padx=3)
            bar=ttk.Frame(tools);bar.pack(fill='x')
            for label,command in [('Enable / disable',lambda k=key:self.toggle(k)),('Edit text',lambda k=key:self.edit(k)),('Remove',lambda k=key:self.remove(k)),('↑',lambda k=key:self.move(k,-1)),('↓',lambda k=key:self.move(k,1))]:
                ttk.Button(bar,text=label,command=command).pack(side='left',padx=3)
            self.refresh(key)
        f=ttk.Frame(self);f.pack(fill='x',padx=20)
        ttk.Label(f,text='Separator').pack(side='left');self.sep=tk.StringVar(value=app.vars['separator'].get());ttk.Entry(f,textvariable=self.sep,width=12).pack(side='left',padx=10)
        mandatory=ttk.Label(self,text='The first image always ends with MAINSHOT CLOSEUP. Duplicate filenames get a sequence suffix.',foreground=GOLD);mandatory.pack(anchor='w',padx=20,pady=10)
        self.example=ttk.Label(self,wraplength=840);self.example.pack(fill='x',padx=20,pady=8)
        apply_button=ttk.Button(self,text='Apply & save naming defaults',style='Gold.TButton',command=self.apply);apply_button.pack(anchor='e',padx=20,pady=(0,20))
        for widget in (apply_button,self.example,mandatory,f):widget.pack_configure(side='bottom',before=tabs)
        self.sep.trace_add('write',lambda *a:self.examples());self.examples()
    def index(self,key):
        sel=self.trees[key].selection();return int(sel[0]) if sel else None
    def refresh(self,key,index=None):
        t=self.trees[key];t.delete(*t.get_children())
        for i,b in enumerate(self.blocks[key]):t.insert('','end',iid=str(i),values=('✓' if b.get('enabled',True) else '',b['kind'],b.get('value','')))
        if self.blocks[key]:t.selection_set(str(min(index or 0,len(self.blocks[key])-1)))
        if hasattr(self,'example'):self.examples()
    def text_dialog(self,initial=''):
        from tkinter.simpledialog import askstring
        return askstring('Custom text block','Text for this block:',initialvalue=initial,parent=self)
    def add(self,key,kind):
        value=self.text_dialog() if kind=='text' else ''
        if value is None:return
        self.blocks[key].append({'kind':kind,'value':value,'enabled':True});self.refresh(key,len(self.blocks[key])-1)
    def toggle(self,key):
        i=self.index(key)
        if i is not None:self.blocks[key][i]['enabled']=not self.blocks[key][i].get('enabled',True);self.refresh(key,i)
    def edit(self,key):
        i=self.index(key)
        if i is None or self.blocks[key][i]['kind']!='text':return
        value=self.text_dialog(self.blocks[key][i].get('value',''))
        if value is not None:self.blocks[key][i]['value']=value;self.refresh(key,i)
    def remove(self,key):
        i=self.index(key)
        if i is not None:self.blocks[key].pop(i);self.refresh(key,i)
    def move(self,key,d):
        i=self.index(key)
        if i is not None and 0<=i+d<len(self.blocks[key]):self.blocks[key][i],self.blocks[key][i+d]=self.blocks[key][i+d],self.blocks[key][i];self.refresh(key,i+d)
    def examples(self):
        try:
            name=build_name(json.dumps(self.blocks['filename_blocks']),self.app.name.get(),'Main',1,self.sep.get(),True,True)+'.png'
            alt=build_name(json.dumps(self.blocks['alt_blocks']),self.app.name.get(),'Main',1,self.sep.get(),True)
            self.example.configure(text='Filename: '+name+'\nAlt text: '+alt)
        except Exception as e:self.example.configure(text=str(e))
    def apply(self):
        try:
            for k,v in self.blocks.items():build_name(json.dumps(v),self.app.name.get(),'Main',1,self.sep.get(),True,k=='filename_blocks')
            for k,v in self.blocks.items():self.app.vars[k].set(json.dumps(v))
            self.app.vars['separator'].set(self.sep.get());self.app.save();self.app.preview();self.destroy()
        except Exception as e:messagebox.showerror('Naming blocks',str(e),parent=self)

class App(BaseApp):
    def __init__(self):
        self.preview_queue=queue.Queue();self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='atlas-preview');self.preview_future=None;self.preview_id=0;self.crop_mode=False;self.drag_start=None
        super().__init__();self.title('Atlas Tools | Photo Studio 2.0');self.geometry('1450x960');self.minsize(1120,780)
        style=ttk.Style(self)
        style.configure('.',background=PANEL,foreground=INK,fieldbackground='#1e1e1e',font=('Segoe UI',10))
        style.configure('TButton',background='#222222',foreground=INK,padding=(10,8),borderwidth=1)
        style.map('TButton',background=[('active','#363636')])
        style.configure('Gold.TButton',background=GOLD,foreground=BG,font=('Segoe UI',10,'bold'))
        style.map('Gold.TButton',background=[('active','#ffbd32')],foreground=[('active',BG)])
        style.configure('TNotebook',background=BG,borderwidth=0)
        style.configure('TNotebook.Tab',background='#191919',foreground=INK,padding=(18,10));style.map('TNotebook.Tab',background=[('selected',GOLD)],foreground=[('selected',BG)])
        style.configure('Treeview',background='#151515',fieldbackground='#151515',rowheight=34)
        style.configure('Treeview.Heading',background='#242014',foreground=GOLD,font=('Segoe UI',10,'bold'))
        style.map('Treeview',background=[('selected','#4b3510')],foreground=[('selected',INK)])
        self.configure(bg=BG)
        def recolour(w):
            try:
                if str(w.cget('foreground')) in ('#e0b64c','#d7ac46'):w.configure(foreground=GOLD)
            except tk.TclError:pass
            for child in w.winfo_children():recolour(child)
        recolour(self)
        # Reserve the status line before allowing the notebook to expand.
        status_widget=self.winfo_children()[-1];status_widget.pack_configure(side='bottom',before=self.work.master)
        self.vars['shop'].trace_add('write',lambda *a:self.schedule_domain_save())
        self.after(60,self.receive_previews)
    def build_workspace(self):
        top=ttk.Frame(self.work);top.pack(fill='x',pady=(0,12))
        ttk.Label(top,text='PRODUCT PHOTOGRAPHY',font=('Segoe UI',15,'bold'),foreground=GOLD).pack(side='left')
        ttk.Button(top,text='Add edited photos',style='Gold.TButton',command=self.add_photos).pack(side='right',padx=4)
        ttk.Button(top,text='Add folder',command=self.add_folder).pack(side='right',padx=4)
        self.row_entry(self.work,'Basic product name',self.name)
        body=ttk.Panedwindow(self.work,orient='horizontal');body.pack(fill='both',expand=True,pady=10)
        left=ttk.Frame(body,padding=(0,0,12,0));right=ttk.Frame(body);body.add(left,weight=2);body.add(right,weight=3)
        ttk.Label(left,text='01 / SELECT YOUR VIEWS',font=('Segoe UI',12,'bold'),foreground=GOLD).pack(anchor='w',pady=8)
        bar=ttk.Frame(left);bar.pack(fill='x',pady=5)
        ttk.Button(bar,text='Suggest 5 locally',command=lambda:self.suggest(False)).pack(side='left')
        ttk.Button(bar,text='AI: choose angles',command=lambda:self.suggest(True)).pack(side='left',padx=8)
        ttk.Label(left,text='First included photo = transparent mainshot.\nDouble-click to include / exclude. Order with the arrows.',foreground=MUTED).pack(anchor='w',pady=7)
        tf=ttk.Frame(left);tf.pack(fill='both',expand=True)
        self.tree=ttk.Treeview(tf,columns=('use','file','view'),show='headings',selectmode='browse',height=10)
        for k,t,w in [('use','Use',45),('file','Edited photo',210),('view','View',115)]:self.tree.heading(k,text=t);self.tree.column(k,width=w,minwidth=35)
        scroll=ttk.Scrollbar(tf,orient='vertical',command=self.tree.yview);self.tree.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');self.tree.pack(fill='both',expand=True)
        self.tree.bind('<<TreeviewSelect>>',self.on_select);self.tree.bind('<Double-1>',lambda e:self.toggle())
        left_footer=ttk.Frame(left);left_footer.pack(side='bottom',fill='x',before=tf)
        bar=ttk.Frame(left_footer);bar.pack(fill='x',pady=8)
        for label,fn in [('Include / exclude',self.toggle),('↑',lambda:self.move(-1)),('↓',lambda:self.move(1)),('Remove',self.remove)]:ttk.Button(bar,text=label,command=fn).pack(side='left',padx=2)
        self.row_entry(left_footer,'View label',self.view);ttk.Button(left_footer,text='Apply view label',command=self.apply_view).pack(anchor='e')
        ttk.Separator(left_footer).pack(fill='x',pady=12)
        ttk.Button(left_footer,text='Configure filename & alt-text blocks',command=lambda:BlockEditor(self)).pack(fill='x')
        self.name_example=ttk.Label(left_footer,text='',wraplength=390,foreground=MUTED);self.name_example.pack(fill='x',pady=8)
        ttk.Label(right,text='02 / PREVIEW & MAINSHOT',font=('Segoe UI',12,'bold'),foreground=GOLD).pack(anchor='w',pady=8)
        bar=ttk.Frame(right);bar.pack(fill='x',pady=4)
        ttk.Button(bar,text='Edit mainshot crop',command=self.start_crop).pack(side='left')
        ttk.Button(bar,text='Show finished preview',command=self.end_crop).pack(side='left',padx=8)
        self.canvas=tk.Canvas(right,bg='#080808',highlightthickness=1,highlightbackground='#3a3324',height=260);self.canvas.pack(fill='both',expand=True,pady=6)
        self.canvas.bind('<Configure>',lambda e:self.schedule_preview());self.canvas.bind('<Button-1>',self.pointer_down);self.canvas.bind('<B1-Motion>',self.pointer_move);self.canvas.bind('<ButtonRelease-1>',self.pointer_up)
        self.summary=ttk.Label(right,text='Low-resolution preview • full-quality export',foreground=MUTED);self.summary.pack(anchor='w',pady=3)
        controls=ttk.Notebook(right);controls.pack(fill='x',pady=6)
        logo=ttk.Frame(controls,padding=8);main=ttk.Frame(controls,padding=8);quality=ttk.Frame(controls,padding=8)
        controls.add(logo,text='Logo');controls.add(main,text='Mainshot crop');controls.add(quality,text='Export & preview')
        f=self.row_entry(logo,'Default logo file',self.vars['logo_path']);ttk.Button(f,text='Browse',command=self.browse_logo).pack(side='right',padx=5)
        f=ttk.Frame(logo);f.pack(fill='x',pady=6)
        for label,key,width in [('X px','logo_x',7),('Y px','logo_y',7),('Width %','logo_width',6),('Opacity %','logo_opacity',6)]:
            ttk.Label(f,text=label).pack(side='left',padx=(0,4));ttk.Entry(f,textvariable=self.vars[key],width=width).pack(side='left',padx=(0,10))
        f=ttk.Frame(logo);f.pack(fill='x')
        for label,anchor in [('Top left','tl'),('Top right','tr'),('Centre','c'),('Bottom left','bl'),('Bottom right','br')]:ttk.Button(f,text=label,command=lambda a=anchor:self.pixel_preset(a),padding=4).pack(side='left',padx=2)
        ttk.Label(logo,text='X/Y = logo top-left in output-canvas pixels. Origin (0,0) is the image top-left.\nDrag on the preview to move it. Coordinates are clamped to fit.',foreground=MUTED).pack(anchor='w',pady=(7,0))
        self.crop_fields={k:tk.StringVar(value='0') for k in ('Left','Top','Width','Height')}
        f=ttk.Frame(main);f.pack(fill='x',pady=4)
        for label,v in self.crop_fields.items():ttk.Label(f,text=label+' px').pack(side='left',padx=(0,3));ttk.Entry(f,textvariable=v,width=6).pack(side='left',padx=(0,8))
        f=ttk.Frame(main);f.pack(fill='x',pady=4)
        ttk.Button(f,text='Apply pixel crop',command=self.apply_pixel_crop).pack(side='left');ttk.Button(f,text='Reset to top 55%',command=self.reset_crop).pack(side='left',padx=6)
        for label,key in [('White threshold','white_threshold'),('Feather range','white_feather')]:ttk.Label(f,text=label).pack(side='left',padx=(8,3));ttk.Entry(f,textvariable=self.vars[key],width=4).pack(side='left')
        f=ttk.Frame(main);f.pack(fill='x',pady=4);ttk.Label(f,text='Add logo to mainshot').pack(side='left');ttk.Combobox(f,textvariable=self.vars['main_logo'],values=['No','Yes'],state='readonly',width=6).pack(side='left',padx=8)
        ttk.Label(main,text='Draw a rectangle on the original photo in crop mode. Pixel fields use source-image pixels.\nMainshot is always a transparent PNG with MAINSHOT CLOSEUP at the end of both names.',foreground=MUTED).pack(anchor='w',pady=4)
        f=ttk.Frame(quality);f.pack(fill='x',pady=4)
        for label,key,width in [('Output edge px','longest_edge',6),('Target MB','max_mb',5),('JPEG quality','quality',4)]:ttk.Label(f,text=label).pack(side='left',padx=(0,4));ttk.Entry(f,textvariable=self.vars[key],width=width).pack(side='left',padx=(0,9))
        f=ttk.Frame(quality);f.pack(fill='x',pady=6)
        ttk.Label(f,text='Other images').pack(side='left');ttk.Combobox(f,textvariable=self.vars['format'],values=['JPEG','PNG'],state='readonly',width=7).pack(side='left',padx=8)
        ttk.Checkbutton(f,text='Square white canvas (other images)',variable=self.square).pack(side='left')
        ttk.Label(quality,text='Preview edge px (lower = faster)').pack(side='left',pady=5)
        ttk.Combobox(quality,textvariable=self.vars['preview_edge'],values=['360','540','720','1080'],width=7,state='readonly').pack(side='left',padx=8)
        footer=ttk.Frame(self.work);footer.pack(side='bottom',fill='x',pady=8,before=body)
        f=self.row_entry(footer,'Export folder',self.vars['output_dir']);ttk.Button(f,text='Browse',command=self.browse_output).pack(side='right',padx=5)
        actions=ttk.Frame(footer);actions.pack(fill='x',pady=(6,0))
        for label,cmd,style in [('Export selected',self.export,'Gold.TButton'),('Approve & upload',self.upload,'TButton'),('Open exports',self.open_output,'TButton'),('Save defaults',self.save,'TButton'),('Clear batch',self.clear,'TButton')]:ttk.Button(actions,text=label,command=cmd,style=style).pack(side='left',padx=(0,8))
        visual={'logo_path','logo_x','logo_y','logo_width','logo_opacity','longest_edge','white_threshold','white_feather','preview_edge','main_logo','crop_boxes'}
        for k,v in self.vars.items():v.trace_add('write',lambda *a,key=k:self.schedule_preview() if key in visual else self.update_names())
        self.name.trace_add('write',lambda *a:self.update_names());self.square.trace_add('write',lambda *a:self.schedule_preview())
    def get_settings(self):
        s=Settings(**{k:v.get() for k,v in self.vars.items()},square=self.square.get());s.validate(require_logo=False);return s
    def save(self):
        try:
            s=self.get_settings();self.write_config(asdict(s));self.status.set('Defaults saved, including Shopify domain and naming blocks.')
        except Exception as e:messagebox.showerror('Settings',str(e))
    def write_config(self,data):
        CONFIG.parent.mkdir(parents=True,exist_ok=True);temp=CONFIG.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2),encoding='utf-8');temp.replace(CONFIG)
    def schedule_domain_save(self):
        if hasattr(self,'domain_timer'):self.after_cancel(self.domain_timer)
        self.domain_timer=self.after(500,self.save_domain)
    def save_domain(self):
        try:
            try:raw=json.loads(CONFIG.read_text(encoding='utf-8'))
            except (OSError,ValueError):raw={}
            raw['shop']=self.vars['shop'].get().strip();self.write_config(raw)
        except OSError as e:self.status.set('Could not save store domain: '+str(e))
    def add_paths(self,paths):
        if self.busy:return
        paths=list(paths);known={p['path'] for p in self.photos}
        def work():
            accepted=[];errors=[]
            for path in paths:
                p=Path(path).resolve()
                if not p.is_file() or p.suffix.lower() not in SUPPORTED or str(p) in known:continue
                try:load_proxy(p,720);source_size(p)
                except Exception as e:errors.append(f'{p.name}: {e}');continue
                known.add(str(p));accepted.append(str(p))
            return accepted,errors
        def done(result):
            accepted,errors=result
            for p in accepted:self.photos.append({'path':p,'view':f'View {len(self.photos)+1}','use':False})
            self.refresh();self.status.set(f'{len(accepted)} photos imported with cached previews. Choose up to five.')
            if errors:messagebox.showwarning('Skipped files','\n'.join(errors[:8]))
        self.run_job('Preparing fast photo previews…',work,done)
    def main_path(self):return next((p['path'] for p in self.photos if p['use']),self.photos[0]['path'] if self.photos else None)
    def is_main(self,path):return path==self.main_path()
    def on_select(self,e=None):
        if self.crop_mode:self.crop_mode=False
        super().on_select(e);self.update_names();self.sync_crop_fields()
    def update_names(self):
        if not hasattr(self,'name_example'):return
        i=self.current()
        if i is None:self.name_example.configure(text='Filename and alt-text examples appear here.');return
        p=self.photos[i];chosen=[x for x in self.photos if x['use']];n=chosen.index(p)+1 if p in chosen else i+1;main=self.is_main(p['path'])
        try:
            s=self.get_settings();stem=build_name(s.filename_blocks,self.name.get(),p['view'],n,s.separator,main,True);alt=build_name(s.alt_blocks,self.name.get(),p['view'],n,s.separator,main)
            self.name_example.configure(text='FILE\n'+stem+('.png' if main or s.format=='PNG' else '.jpg')+'\n\nALT TEXT\n'+alt)
        except Exception as e:self.name_example.configure(text=str(e))
    def schedule_preview(self):
        if hasattr(self,'preview_timer'):
            try:self.after_cancel(self.preview_timer)
            except tk.TclError:pass
        self.preview_timer=self.after(80,self.preview)
    def preview(self):
        if not hasattr(self,'canvas'):return
        self.update_names();i=self.current();self.preview_id+=1;request=self.preview_id
        if i is None:self.canvas.delete('all');self.canvas.create_text(220,110,text='ADD EDITED PHOTOS TO BEGIN',fill=GOLD,font=('Segoe UI',12,'bold'));return
        try:s=self.get_settings();path=self.photos[i]['path'];main=self.is_main(path);crop_mode=self.crop_mode
        except Exception as e:self.summary.configure(text=str(e));return
        if self.preview_future and not self.preview_future.running():self.preview_future.cancel()
        def work():
            start=time.perf_counter()
            try:
                im=load_proxy(path,int(s.preview_edge)) if crop_mode else render(path,s,main=main,preview=True)
                result=(im,canvas_size(path,s,main),time.perf_counter()-start,main,crop_mode,None)
            except Exception as e:
                try:result=(load_proxy(path,int(s.preview_edge)),canvas_size(path,s,main),0,main,crop_mode,str(e))
                except Exception as inner:result=(None,None,0,main,crop_mode,str(inner))
            self.preview_queue.put((request,path,result))
        self.preview_future=self.pool.submit(work)
    def checker(self,size):
        im=Image.new('RGBA',size,'#242424');draw=ImageDraw.Draw(im)
        for y in range(0,size[1],14):
            for x in range(0,size[0],14):
                if (x//14+y//14)%2:draw.rectangle((x,y,x+13,y+13),fill='#303030')
        return im
    def receive_previews(self):
        try:
            while True:
                request,path,result=self.preview_queue.get_nowait()
                if request!=self.preview_id:continue
                im,final,elapsed,main,mode,error=result
                if im is None:self.summary.configure(text=error);continue
                im.thumbnail((max(100,self.canvas.winfo_width()-24),max(80,self.canvas.winfo_height()-24)),Image.Resampling.BILINEAR)
                self.preview_bounds=((self.canvas.winfo_width()-im.width)//2,(self.canvas.winfo_height()-im.height)//2,im.width,im.height)
                self.preview_final=final;self.canvas.delete('all');self.preview_image=ImageTk.PhotoImage(Image.alpha_composite(self.checker(im.size),im))
                x,y,w,h=self.preview_bounds;self.canvas.create_image(x,y,anchor='nw',image=self.preview_image)
                self.summary.configure(text=error or (('CROP ORIGINAL' if mode else 'MAINSHOT PNG' if main else 'LOGO PREVIEW')+f' • canvas {final[0]} × {final[1]} px • preview {elapsed*1000:.0f} ms'))
                if mode:self.draw_crop(path)
        except queue.Empty:pass
        self.after(60,self.receive_previews)
    def draw_crop(self,path):
        x,y,w,h=self.preview_bounds;box=crop_for(path,self.get_settings());self.canvas.delete('crop')
        self.canvas.create_rectangle(x+box[0]*w,y+box[1]*h,x+box[2]*w,y+box[3]*h,outline=GOLD,width=3,tags='crop')
    def source_point(self,event):
        x,y,w,h=self.preview_bounds;return max(0,min(1,(event.x-x)/w)),max(0,min(1,(event.y-y)/h))
    def pointer_down(self,e):
        if self.busy or not hasattr(self,'preview_bounds'):return
        if self.crop_mode:self.drag_start=self.source_point(e)
        else:
            try:
                i=self.current();s=self.get_settings();path=self.photos[i]['path'];main=self.is_main(path)
                if main and s.main_logo!='Yes':self.status.set('Mainshot logo is off. Enable it under Mainshot crop if required.');return
                final=canvas_size(path,s,main);logo=load_proxy(s.logo_path);gx,gy,lw,lh=logo_geometry(final,logo,s)
                nx,ny=self.source_point(e);px,py=nx*final[0],ny*final[1]
                self.logo_drag_offset=(px-gx,py-gy) if gx<=px<=gx+lw and gy<=py<=gy+lh else (lw/2,lh/2)
                self.move_logo(e)
            except Exception as error:self.status.set(str(error))
    def move_logo(self,e):
        if not hasattr(self,'preview_final'):return
        try:
            nx,ny=self.source_point(e);fw,fh=self.preview_final;s=self.get_settings();i=self.current();size=canvas_size(self.photos[i]['path'],s,self.is_main(self.photos[i]['path']));_,_,lw,lh=logo_geometry(size,load_proxy(s.logo_path),s)
            ox,oy=getattr(self,'logo_drag_offset',(lw/2,lh/2))
            self.vars['logo_x'].set(str(round(max(0,min(fw-lw,nx*fw-ox)))))
            self.vars['logo_y'].set(str(round(max(0,min(fh-lh,ny*fh-oy)))))
        except Exception:pass
    def pointer_move(self,e):
        if self.busy:return
        if self.crop_mode and self.drag_start:
            x0,y0=self.drag_start;x1,y1=self.source_point(e);x,y,w,h=self.preview_bounds;self.canvas.delete('crop')
            self.canvas.create_rectangle(x+x0*w,y+y0*h,x+x1*w,y+y1*h,outline=GOLD,width=3,tags='crop')
        elif not self.crop_mode:self.move_logo(e)
    def pointer_up(self,e):
        if self.busy:return
        if self.crop_mode and self.drag_start:
            x0,y0=self.drag_start;x1,y1=self.source_point(e);self.drag_start=None
            if abs(x1-x0)<.01 or abs(y1-y0)<.01:return
            self.set_crop([min(x0,x1),min(y0,y1),max(x0,x1),max(y0,y1)])
    def start_crop(self):
        path=self.main_path()
        if not path:return
        i=next(i for i,p in enumerate(self.photos) if p['path']==path);self.tree.selection_set(str(i));self.update_idletasks();self.after(20,self.enable_crop)
    def enable_crop(self):self.crop_mode=True;self.sync_crop_fields();self.preview();self.status.set('Drag a rectangle around the tool tip. Then click Show finished preview.')
    def end_crop(self):self.crop_mode=False;self.preview()
    def sync_crop_fields(self):
        i=self.current()
        if i is None or not hasattr(self,'crop_fields'):return
        try:
            path=self.photos[i]['path'];w,h=source_size(path);x0,y0,x1,y1=crop_for(path,self.get_settings())
            for key,val in zip(('Left','Top','Width','Height'),(round(x0*w),round(y0*h),round(x1*w)-round(x0*w),round(y1*h)-round(y0*h))):self.crop_fields[key].set(str(val))
        except Exception:pass
    def set_crop(self,box):
        i=self.current()
        if i is None:return
        boxes=json.loads(self.vars['crop_boxes'].get());boxes[self.photos[i]['path']]=box;self.vars['crop_boxes'].set(json.dumps(boxes));self.sync_crop_fields();self.preview()
    def apply_pixel_crop(self):
        i=self.current()
        if i is None:return
        try:
            path=self.photos[i]['path'];w,h=source_size(path);left,top,cw,ch=[float(self.crop_fields[k].get()) for k in ('Left','Top','Width','Height')]
            if left<0 or top<0 or cw<1 or ch<1 or left+cw>w or top+ch>h:raise ValueError('Crop must have positive width/height and fit inside the source photo.')
            self.set_crop([left/w,top/h,(left+cw)/w,(top+ch)/h]);self.crop_mode=False;self.preview()
        except Exception as e:messagebox.showerror('Crop',str(e))
    def reset_crop(self):self.set_crop([0,0,1,.55])
    def pixel_preset(self,anchor):
        i=self.current()
        if i is None:return
        try:
            s=self.get_settings();size=canvas_size(self.photos[i]['path'],s,self.is_main(self.photos[i]['path']));_,_,lw,lh=logo_geometry(size,load_proxy(s.logo_path),s);w,h=size
            x=0 if anchor.endswith('l') else w-lw if anchor.endswith('r') else (w-lw)//2;y=0 if anchor.startswith('t') else h-lh if anchor.startswith('b') else (h-lh)//2
            self.vars['logo_x'].set(str(x));self.vars['logo_y'].set(str(y));self.preview()
        except Exception as e:self.status.set(str(e))
    def batch_signature(self):
        s=self.get_settings()
        rows=[(p['path'],p['view'],Path(p['path']).stat().st_mtime_ns,Path(p['path']).stat().st_size) for p in self.photos if p['use']]
        logo=Path(s.logo_path)
        stamp=(logo.stat().st_mtime_ns,logo.stat().st_size) if logo.is_file() else None
        return json.dumps([self.name.get(),asdict(s),rows,stamp],sort_keys=True)
    def close(self):
        if self.busy:messagebox.showinfo('Operation running','Wait for the current operation to finish.');return
        self.save_domain();self.preview_id+=1;self.pool.shutdown(wait=False,cancel_futures=True)
        for callback in self.tk.call('after','info'):
            try:self.after_cancel(callback)
            except tk.TclError:pass
        self.destroy()
