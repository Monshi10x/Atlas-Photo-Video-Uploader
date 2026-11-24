from __future__ import annotations
import json, os, queue, threading, tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from dataclasses import asdict, fields
from PIL import Image, ImageTk, ImageOps
from core import Settings, SUPPORTED, load_image, render, choose_local, choose_ai, export_batch
from shopify_api import Shopify, request_access_token

DATA=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'.config')))/'AtlasPhotoStudio'
DATA.mkdir(parents=True,exist_ok=True)
CONFIG=DATA/'settings.json'

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title('Atlas Tools | Photo Studio'); self.geometry('1380x920'); self.minsize(1120,760)
        self.configure(bg='#101216'); self.events=queue.Queue(); self.busy=False; self.photos=[]; self.exports=[]; self.export_signature=None; self.product=None; self.products=[]; self.watch_seen={}; self.watch_stable={}
        try: saved=json.loads(CONFIG.read_text(encoding='utf-8'))
        except (OSError,ValueError): saved={}
        valid={f.name for f in fields(Settings)}; self.settings=Settings(**{k:v for k,v in saved.items() if k in valid})
        self.vars={k:tk.StringVar(value=str(v)) for k,v in asdict(self.settings).items() if k!='square'}
        self.square=tk.BooleanVar(value=self.settings.square); self.watch=tk.BooleanVar(value=False)
        self.name=tk.StringVar(value='Atlas Tools TCT Router Bit 3F 8x22 ZrN'); self.view=tk.StringVar(value='Main'); self.status=tk.StringVar(value='Choose your edited photos and logo to begin.')
        self.client_id=tk.StringVar(); self.client_secret=tk.StringVar(); self.token=tk.StringVar(); self.ai_key=tk.StringVar(); self.search=tk.StringVar(); self.selected=tk.BooleanVar(value=True)
        self.load_secrets()
        style=ttk.Style(self); style.theme_use('clam')
        style.configure('.',background='#171a20',foreground='#edf0f5',fieldbackground='#252a33',font=('Segoe UI',10))
        style.configure('TButton',padding=(12,8),background='#303743'); style.map('TButton',background=[('active','#485262')])
        style.configure('Gold.TButton',background='#d7ac46',foreground='#111111',font=('Segoe UI',10,'bold'))
        style.configure('TNotebook.Tab',padding=(15,9)); style.configure('Treeview',rowheight=31,background='#20242c',fieldbackground='#20242c'); style.map('Treeview',background=[('selected','#665326')])
        header=ttk.Frame(self,padding=(22,17)); header.pack(fill='x')
        ttk.Label(header,text='ATLAS TOOLS',font=('Segoe UI',18,'bold'),foreground='#e0b64c').pack(side='left')
        ttk.Label(header,text='PHOTO STUDIO',font=('Segoe UI',16)).pack(side='left',padx=18)
        ttk.Label(header,text='PREPARE  /  REVIEW  /  PUBLISH',foreground='#aeb6c3').pack(side='right')
        tabs=ttk.Notebook(self); tabs.pack(fill='both',expand=True,padx=16,pady=(0,10))
        self.work=ttk.Frame(tabs,padding=14); conn_outer=ttk.Frame(tabs); conn_canvas=tk.Canvas(conn_outer,bg='#171a20',highlightthickness=0); conn_scroll=ttk.Scrollbar(conn_outer,orient='vertical',command=conn_canvas.yview); conn_canvas.configure(yscrollcommand=conn_scroll.set); conn_scroll.pack(side='right',fill='y'); conn_canvas.pack(side='left',fill='both',expand=True); self.conn=ttk.Frame(conn_canvas,padding=24); conn_window=conn_canvas.create_window((0,0),window=self.conn,anchor='nw'); self.conn.bind('<Configure>',lambda e:conn_canvas.configure(scrollregion=conn_canvas.bbox('all'))); conn_canvas.bind('<Configure>',lambda e:conn_canvas.itemconfigure(conn_window,width=e.width))
        tabs.add(self.work,text='Photo workspace'); tabs.add(conn_outer,text='Connections & setup')
        self.build_workspace(); self.build_connections()
        ttk.Label(self,textvariable=self.status,padding=(20,10),foreground='#e0b64c').pack(fill='x')
        self.after(100,self.pump); self.after(2500,self.poll_watch)
        self.protocol('WM_DELETE_WINDOW',self.close)
    def load_secrets(self):
        try:
            import keyring
            self.client_id.set(keyring.get_password('AtlasPhotoStudio','client_id') or '')
            self.client_secret.set(keyring.get_password('AtlasPhotoStudio','client_secret') or '')
            self.token.set(keyring.get_password('AtlasPhotoStudio','shopify') or '')
            self.ai_key.set(keyring.get_password('AtlasPhotoStudio','openai') or '')
        except Exception: pass
    def row_entry(self,parent,label,var,width=40):
        frame=ttk.Frame(parent); frame.pack(fill='x',pady=5)
        ttk.Label(frame,text=label,width=21).pack(side='left'); e=ttk.Entry(frame,textvariable=var,width=width); e.pack(side='left',fill='x',expand=True); return frame
    def build_workspace(self):
        top=ttk.Frame(self.work); top.pack(fill='x')
        ttk.Label(top,text='Product / export name').pack(side='left'); ttk.Entry(top,textvariable=self.name).pack(side='left',fill='x',expand=True,padx=12)
        ttk.Button(top,text='Add photos',command=self.add_photos,style='Gold.TButton').pack(side='left',padx=4)
        ttk.Button(top,text='Add folder',command=self.add_folder).pack(side='left',padx=4)
        body=ttk.Panedwindow(self.work,orient='horizontal'); body.pack(fill='both',expand=True,pady=12)
        left=ttk.Frame(body,padding=8); right=ttk.Frame(body,padding=8); body.add(left,weight=2); body.add(right,weight=3)
        ttk.Label(left,text='01   SELECT & ORDER',font=('Segoe UI',12,'bold')).pack(anchor='w',pady=(0,9))
        tools=ttk.Frame(left); tools.pack(fill='x',pady=4)
        ttk.Button(tools,text='Suggest 5 locally',command=lambda:self.suggest(False)).pack(side='left')
        ttk.Button(tools,text='AI: choose angles',command=lambda:self.suggest(True)).pack(side='left',padx=6)
        ttk.Label(left,text='Local = sharpness + visual variety. AI = angle assessment.\nReview the selected views before upload.',foreground='#aeb6c3').pack(anchor='w',pady=6)
        self.tree=ttk.Treeview(left,columns=('use','file','view'),show='headings',selectmode='browse',height=11)
        for k,t,w in [('use','Use',42),('file','Source photo',210),('view','View / angle',130)]: self.tree.heading(k,text=t); self.tree.column(k,width=w,minwidth=35)
        self.tree.pack(fill='both',expand=True); self.tree.bind('<<TreeviewSelect>>',self.on_select)
        self.tree.bind('<Double-1>',lambda e:self.toggle())
        edit=ttk.Frame(left); edit.pack(fill='x',pady=7)
        ttk.Button(edit,text='Include / exclude',command=self.toggle).pack(side='left')
        ttk.Button(edit,text='↑',width=3,command=lambda:self.move(-1)).pack(side='left',padx=4)
        ttk.Button(edit,text='↓',width=3,command=lambda:self.move(1)).pack(side='left')
        ttk.Button(edit,text='Remove',command=self.remove).pack(side='right')
        self.row_entry(left,'View label',self.view)
        ttk.Button(left,text='Apply view label',command=self.apply_view).pack(anchor='e')
        self.canvas=tk.Canvas(right,bg='#0f1115',highlightthickness=0,height=300); self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda e:self.preview()); self.canvas.bind('<Button-1>',self.place_logo); self.canvas.bind('<B1-Motion>',self.place_logo)
        ttk.Label(right,text='Live export preview • click or drag to position the logo',foreground='#aeb6c3').pack(pady=5)
        self.summary=ttk.Label(right,text='No photo selected'); self.summary.pack()
        controls=ttk.Frame(right); controls.pack(fill='x')
        logo=self.row_entry(controls,'Default logo file',self.vars['logo_path']); ttk.Button(logo,text='Browse',command=self.browse_logo).pack(side='right',padx=5)
        for key,label,lo,hi in [('logo_width','Logo width %',1,95),('logo_opacity','Opacity %',0,100),('margin','Edge margin %',0,20),('position_x','Horizontal %',0,100),('position_y','Vertical %',0,100)]:
            f=ttk.Frame(controls); f.pack(fill='x',pady=1); ttk.Label(f,text=label,width=17).pack(side='left')
            ttk.Scale(f,from_=lo,to=hi,variable=self.vars[key],command=lambda v:self.schedule_preview()).pack(side='left',fill='x',expand=True)
            ttk.Entry(f,textvariable=self.vars[key],width=7).pack(side='left',padx=6)
        presets=ttk.Frame(controls); presets.pack(fill='x',pady=4)
        for label,x,y in [('Top left',0,0),('Top right',100,0),('Centre',50,50),('Bottom left',0,100),('Bottom right',100,100)]:
            ttk.Button(presets,text=label,command=lambda a=x,b=y:self.preset(a,b),padding=4).pack(side='left',padx=2)
        bottom=ttk.Frame(self.work); bottom.pack(fill='x')
        for label,key,width in [('Longest edge px','longest_edge',6),('Target MB','max_mb',5),('Quality','quality',4)]:
            ttk.Label(bottom,text=label).pack(side='left',padx=(0,5)); ttk.Entry(bottom,textvariable=self.vars[key],width=width).pack(side='left',padx=(0,12))
        ttk.Combobox(bottom,textvariable=self.vars['format'],values=['JPEG','PNG'],state='readonly',width=7).pack(side='left')
        ttk.Checkbutton(bottom,text='Square white canvas',variable=self.square,command=self.preview).pack(side='left',padx=10)
        ttk.Button(bottom,text='Save defaults',command=self.save).pack(side='right')
        dest=self.row_entry(self.work,'Export folder',self.vars['output_dir']); ttk.Button(dest,text='Browse',command=self.browse_output).pack(side='right',padx=5)
        actions=ttk.Frame(self.work); actions.pack(fill='x',pady=(8,0))
        ttk.Button(actions,text='02   Export selected photos',command=self.export,style='Gold.TButton').pack(side='left')
        ttk.Button(actions,text='03   Approve & upload to Shopify',command=self.upload).pack(side='left',padx=10)
        ttk.Button(actions,text='Open export folder',command=self.open_output).pack(side='left')
        ttk.Button(actions,text='Clear batch',command=self.clear).pack(side='right')
        for var in list(self.vars.values())+[self.name]: var.trace_add('write',lambda *a:self.schedule_preview())
        self.square.trace_add('write',lambda *a:self.schedule_preview())
    def build_connections(self):
        ttk.Label(self.conn,text='SHOPIFY',font=('Segoe UI',14,'bold'),foreground='#e0b64c').pack(anchor='w')
        self.row_entry(self.conn,'Store domain',self.vars['shop'])
        self.row_entry(self.conn,'App Client ID',self.client_id)
        f=self.row_entry(self.conn,'App Client Secret',self.client_secret); list(f.winfo_children())[1].configure(show='•')
        ttk.Button(self.conn,text='Get / refresh 24-hour access token',command=self.generate_token).pack(anchor='e',pady=4)
        f=self.row_entry(self.conn,'Admin API access token',self.token); list(f.winfo_children())[1].configure(show='•')
        ttk.Label(self.conn,text='Use name.myshopify.com. App scopes: read_products, write_products, read_files, write_files.\nCredentials are kept in memory unless you save them to Windows Credential Manager.',foreground='#aeb6c3').pack(anchor='w',pady=5)
        search=self.row_entry(self.conn,'Product title / SKU query',self.search)
        ttk.Button(search,text='Search Shopify',command=self.find_products).pack(side='right',padx=5)
        ttk.Label(self.conn,text='For an exact SKU, enter sku:YOUR-SKU. Select the matching product below.').pack(anchor='w')
        self.product_list=tk.Listbox(self.conn,height=6,bg='#252a33',fg='white',selectbackground='#665326',font=('Segoe UI',11),exportselection=False); self.product_list.pack(fill='x',pady=9)
        ttk.Button(self.conn,text='Use selected Shopify product',command=self.use_product).pack(anchor='e')
        self.product_label=ttk.Label(self.conn,text='Upload target: none selected',foreground='#e0b64c'); self.product_label.pack(anchor='w',pady=9)
        ttk.Separator(self.conn).pack(fill='x',pady=16)
        ttk.Label(self.conn,text='OPTIONAL AI SELECTION',font=('Segoe UI',12,'bold')).pack(anchor='w')
        f=self.row_entry(self.conn,'OpenAI API key',self.ai_key); list(f.winfo_children())[1].configure(show='•')
        self.row_entry(self.conn,'Vision model',self.vars['model'])
        ttk.Label(self.conn,text='AI selection sends up to 24 shortlisted image previews to OpenAI only when clicked.\nRequires separate API billing. Local selection and export work without an AI key.',foreground='#aeb6c3').pack(anchor='w',pady=5)
        ttk.Separator(self.conn).pack(fill='x',pady=16)
        f=self.row_entry(self.conn,'Watch input folder',self.vars['watch_dir']); ttk.Button(f,text='Browse',command=self.browse_watch).pack(side='right',padx=5)
        ttk.Checkbutton(self.conn,text='Watch while app is open: add stable photos to this review batch',variable=self.watch).pack(anchor='w')
        ttk.Label(self.conn,text='One product per batch. Watching adds files for review; export and upload require a click.').pack(anchor='w',pady=5)
        buttons=ttk.Frame(self.conn); buttons.pack(fill='x',pady=12)
        ttk.Button(buttons,text='Save defaults',command=self.save).pack(side='left')
        ttk.Button(buttons,text='Save credentials securely',command=self.save_secrets).pack(side='left',padx=10)
        ttk.Button(buttons,text='Forget saved credentials',command=self.forget_secrets).pack(side='left')
    def get_settings(self):
        s=Settings(**{k:v.get().strip() for k,v in self.vars.items()},square=self.square.get()); s.validate(); return s
    def save(self):
        try:
            s=self.get_settings(); CONFIG.write_text(json.dumps(asdict(s),indent=2),encoding='utf-8'); self.status.set('Default logo path and export settings saved.')
        except Exception as e: messagebox.showerror('Settings',str(e))
    def save_secrets(self):
        try:
            import keyring
            if self.client_id.get(): keyring.set_password('AtlasPhotoStudio','client_id',self.client_id.get())
            if self.client_secret.get(): keyring.set_password('AtlasPhotoStudio','client_secret',self.client_secret.get())
            if self.token.get(): keyring.set_password('AtlasPhotoStudio','shopify',self.token.get())
            if self.ai_key.get(): keyring.set_password('AtlasPhotoStudio','openai',self.ai_key.get())
            self.status.set('Credentials saved in the operating system credential store.')
        except Exception: messagebox.showerror('Credentials','Secure storage unavailable. Credentials remain in memory; no plaintext copy was saved.')
    def forget_secrets(self):
        try:
            import keyring
            for key in ('shopify','openai','client_id','client_secret'):
                try: keyring.delete_password('AtlasPhotoStudio',key)
                except keyring.errors.PasswordDeleteError: pass
            self.token.set(''); self.ai_key.set(''); self.client_id.set(''); self.client_secret.set(''); self.status.set('Saved credentials removed.')
        except Exception as e: messagebox.showerror('Credentials',str(e))
    def browse_logo(self):
        p=filedialog.askopenfilename(title='Choose logo (transparent PNG recommended)',filetypes=[('Logo images','*.png *.webp *.jpg *.jpeg *.tif *.tiff *.bmp')])
        if p: self.vars['logo_path'].set(p); self.preview()
    def browse_output(self):
        p=filedialog.askdirectory(title='Choose export folder')
        if p: self.vars['output_dir'].set(p)
    def browse_watch(self):
        p=filedialog.askdirectory(title='Choose input folder (one product)')
        if p: self.vars['watch_dir'].set(p); self.watch_stable={}
    def add_photos(self): self.add_paths(filedialog.askopenfilenames(title='Choose edited photos',filetypes=[('Photos','*.jpg *.jpeg *.png *.webp *.tif *.tiff *.bmp')]))
    def add_folder(self):
        p=filedialog.askdirectory(title='Choose product photo folder')
        if p: self.add_paths(sorted(Path(p).iterdir()))
    def add_paths(self,paths):
        if self.busy: return
        known={p['path'] for p in self.photos}; added=0; errors=[]
        for path in paths:
            p=Path(path).resolve()
            if not p.is_file() or p.suffix.lower() not in SUPPORTED or str(p) in known: continue
            try: load_image(p)
            except Exception as e: errors.append(f'{p.name}: {e}'); continue
            self.photos.append({'path':str(p),'view':f'View {len(self.photos)+1}','use':False}); known.add(str(p)); added+=1
        self.refresh(); self.status.set(f'{added} photos added. Select up to five to export.'+ (f' {len(errors)} unreadable files skipped.' if errors else ''))
        if errors: messagebox.showwarning('Skipped files','\n'.join(errors[:8]))
    def current(self):
        sel=self.tree.selection(); return int(sel[0]) if sel else None
    def refresh(self,index=None):
        self.tree.delete(*self.tree.get_children())
        for i,p in enumerate(self.photos): self.tree.insert('', 'end',iid=str(i),values=('✓' if p['use'] else '',Path(p['path']).name,p['view']))
        if self.photos:
            index=min(index if index is not None else 0,len(self.photos)-1); self.tree.selection_set(str(index)); self.tree.see(str(index))
    def on_select(self,e=None):
        i=self.current()
        if i is not None: self.view.set(self.photos[i]['view']); self.preview()
    def toggle(self):
        if self.busy:return
        i=self.current()
        if i is None:return
        p=self.photos[i]
        if not p['use'] and sum(x['use'] for x in self.photos)>=5: messagebox.showinfo('Selection','Select a maximum of five photos.'); return
        p['use']=not p['use']; self.refresh(i)
    def apply_view(self):
        if self.busy:return
        i=self.current()
        if i is not None and self.view.get().strip(): self.photos[i]['view']=self.view.get().strip(); self.refresh(i)
    def move(self,delta):
        if self.busy:return
        i=self.current()
        if i is not None and 0<=i+delta<len(self.photos): self.photos[i],self.photos[i+delta]=self.photos[i+delta],self.photos[i]; self.refresh(i+delta)
    def remove(self):
        if self.busy:return
        i=self.current()
        if i is not None: self.photos.pop(i); self.refresh(i); self.preview()
    def preset(self,x,y): self.vars['position_x'].set(str(x)); self.vars['position_y'].set(str(y)); self.preview()
    def schedule_preview(self):
        if hasattr(self,'preview_timer'): self.after_cancel(self.preview_timer)
        self.preview_timer=self.after(150,self.preview)
    def preview(self):
        if not hasattr(self,'canvas'):return
        self.canvas.delete('all'); i=self.current()
        if i is None: self.canvas.create_text(180,110,text='Add a photo to preview your logo',fill='#aeb6c3'); return
        try:
            try: im=render(self.photos[i]['path'],self.get_settings()); note='Logo preview'
            except Exception: im=load_image(self.photos[i]['path']); note='Choose a valid logo to preview branding'
            w,h=max(200,self.canvas.winfo_width()-24),max(120,self.canvas.winfo_height()-24)
            im.thumbnail((w,h),Image.Resampling.LANCZOS)
            self.preview_bounds=((self.canvas.winfo_width()-im.width)//2,(self.canvas.winfo_height()-im.height)//2,im.width,im.height)
            self.preview_image=ImageTk.PhotoImage(im); x,y,_,_=self.preview_bounds
            self.canvas.create_image(x,y,anchor='nw',image=self.preview_image)
            self.summary.configure(text=f'{note} • {sum(p["use"] for p in self.photos)}/5 selected')
        except Exception as e:self.status.set(str(e))
    def place_logo(self,e):
        if not hasattr(self,'preview_bounds'):return
        x,y,w,h=self.preview_bounds
        # Click maps to the centre of the logo within its allowed travel area.
        try:
            s=self.get_settings(); logo=load_image(s.logo_path); box=logo.getbbox(); logo=logo.crop(box)
            lw=min(w*float(s.logo_width)/100,w*(1-2*float(s.margin)/100)); lh=logo.height*lw/logo.width
            if lh>h*(1-2*float(s.margin)/100): lw*=h*(1-2*float(s.margin)/100)/lh; lh=h*(1-2*float(s.margin)/100)
            mx=w*float(s.margin)/100; my=h*float(s.margin)/100
            self.vars['position_x'].set(str(round(max(0,min(100,(e.x-x-mx-lw/2)/max(1,w-2*mx-lw)*100)),1)))
            self.vars['position_y'].set(str(round(max(0,min(100,(e.y-y-my-lh/2)/max(1,h-2*my-lh)*100)),1)))
        except Exception:pass
    def run_job(self,label,work,done):
        if self.busy:return
        self.busy=True; self.status.set(label)
        def worker():
            try: self.events.put(('done',done,work()))
            except Exception as e:self.events.put(('error',str(e)))
        threading.Thread(target=worker,daemon=True).start()
    def pump(self):
        try:
            while True:
                event=self.events.get_nowait()
                if event[0]=='done': self.busy=False; event[1](event[2])
                elif event[0]=='error': self.busy=False; self.status.set('Stopped: '+event[1]); messagebox.showerror('Operation stopped',event[1])
                else:self.status.set(event[1])
        except queue.Empty:pass
        self.after(100,self.pump)
    def suggest(self,ai):
        if not self.photos:return
        paths=[p['path'] for p in self.photos]; key=self.ai_key.get(); model=self.vars['model'].get(); product=self.name.get()
        if ai and not messagebox.askokcancel('AI photo selection','Send up to 24 shortlisted image previews to OpenAI for angle selection? API usage charges apply.'):return
        def done(chosen):
            mapping={p['path']:p for p in self.photos}; rows=[]
            for p in self.photos:p['use']=False
            for path,view in chosen:
                p=mapping[path]; p.update(use=True,view=view); rows.append(p)
            self.photos=rows+[p for p in self.photos if not p['use']]; self.refresh(); self.status.set(f'{len(rows)} photos selected. Review labels and order before export.')
        self.run_job('Assessing photos…',lambda:choose_ai(paths,key,model,product) if ai else choose_local(paths),done)
    def batch_signature(self):
        s=self.get_settings()
        rows=[(p['path'],p['view'],Path(p['path']).stat().st_mtime_ns,Path(p['path']).stat().st_size) for p in self.photos if p['use']]
        return json.dumps([self.name.get(),asdict(s),rows,Path(s.logo_path).stat().st_mtime_ns],sort_keys=True)
    def export(self):
        if self.busy:return
        try:
            settings=self.get_settings(); rows=[(p['path'],p['view']) for p in self.photos if p['use']]
            if not 1<=len(rows)<=5:raise ValueError('Select one to five photos first.')
            if not settings.output_dir:raise ValueError('Choose an export folder first.')
            signature=self.batch_signature(); product=self.name.get()
        except Exception as e:messagebox.showerror('Export',str(e)); return
        def done(images):
            self.exports=images; self.export_signature=signature; self.status.set(f'Exported {len(images)} photos. Largest: {max(i["bytes"] for i in images)/1e6:.2f} MB. Ready for upload.')
        self.run_job('Adding logo and exporting…',lambda:export_batch(rows,product,settings),done)
    def generate_token(self):
        shop=self.vars['shop'].get(); cid=self.client_id.get(); secret=self.client_secret.get()
        def done(token):
            self.token.set(token); self.status.set('Access token ready. Valid for about 24 hours; refresh here when needed.')
        self.run_job('Requesting Shopify access token…',lambda:request_access_token(shop,cid,secret),done)
    def client(self):return Shopify(self.vars['shop'].get(),self.token.get())
    def find_products(self):
        try:client=self.client(); q=self.search.get().strip()
        except Exception as e:messagebox.showerror('Shopify',str(e));return
        if not q:messagebox.showinfo('Search','Enter a title or sku:YOUR-SKU.');return
        def done(products):
            self.products=products;self.product_list.delete(0,'end')
            for p in products:self.product_list.insert('end',p['title']+'  |  '+p['handle'])
            self.status.set(f'{len(products)} products found. Select the exact product.')
        self.run_job('Searching Shopify…',lambda:client.search(q),done)
    def use_product(self):
        if self.busy:return
        selected=self.product_list.curselection()
        if not selected:return
        self.product={**self.products[selected[0]],'shop':self.client().shop}; self.name.set(self.product['title'])
        self.product_label.configure(text='Upload target: '+self.product['title']+'  |  '+self.product['handle']); self.status.set('Product selected. Return to Photo workspace.')
    def upload(self):
        if self.busy:return
        try:
            client=self.client()
            if not self.product or self.product['shop']!=client.shop:raise ValueError('Search and select a Shopify product in Connections first.')
            if not self.exports or self.batch_signature()!=self.export_signature:raise ValueError('Export this batch again: settings, photos or names changed.')
            pid=self.product['id']; images=list(self.exports)
        except Exception as e:messagebox.showerror('Upload',str(e));return
        if not messagebox.askyesno('Approve upload',f'Upload {len(images)} images to:\n{self.product["title"]}\n{client.shop}\n\nThe first selected image becomes the main image.\nExisting photos stay after this new batch. Continue?'):return
        self.run_job('Uploading to Shopify…',lambda:client.upload(pid,images,DATA/'uploads.json',lambda m:self.events.put(('log',m))),lambda _:self.status.set('Upload complete. Image processing, alt text and order verified.'))
    def open_output(self):
        folder=Path(self.exports[0]['file']).parent if self.exports else Path(self.vars['output_dir'].get())
        if not folder.is_dir():return
        import subprocess,sys
        if sys.platform=='win32':os.startfile(str(folder))
        elif sys.platform=='darwin':subprocess.Popen(['open',str(folder)])
        else:subprocess.Popen(['xdg-open',str(folder)])
    def clear(self):
        if self.busy:return
        if self.photos and not messagebox.askyesno('Clear batch','Clear the review list? Source files and exports are kept.'):return
        self.photos=[];self.exports=[];self.export_signature=None;self.refresh();self.preview();self.status.set('Batch cleared. Select the next product.')
    def poll_watch(self):
        if self.watch.get() and not self.busy:
            try:
                root=Path(self.vars['watch_dir'].get()); paths=[]
                if root.is_dir():
                    for p in root.iterdir():
                        if not p.is_file() or p.suffix.lower() not in SUPPORTED:continue
                        sig=(p.stat().st_size,p.stat().st_mtime_ns); key=str(p.resolve())
                        if self.watch_stable.get(key)==sig and self.watch_seen.get(key)!=sig:
                            paths.append(p);self.watch_seen[key]=sig
                        self.watch_stable[key]=sig
                if paths:self.add_paths(paths)
            except OSError as e:self.status.set('Watch folder: '+str(e))
        self.after(2500,self.poll_watch)
    def close(self):
        if self.busy:
            messagebox.showinfo('Operation running','Wait for the current operation to finish before closing.');return
        self.destroy()

if __name__=='__main__': App().mainloop()
