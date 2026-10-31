"""Numbered photo workflow and aspect-constrained crop interactions."""
import json
import tkinter as tk
from tkinter import ttk,messagebox
from pathlib import Path
from studio_v2 import App as V2,BlockEditor,GOLD,MUTED
from core import crop_for,source_size
from crop_geometry import RATIOS,fit_ratio,move_box,resize_corner
from video_ui_v4 import VideoPanel

class App(V2):
    def __init__(self):
        self.crop_gesture=None;self.live_crop=None
        super().__init__();self.title('Atlas Tools | Photo & Video Studio 4.0');self.geometry('1480x1050');self.minsize(1180,850)
        style=ttk.Style(self);style.configure('Step.TLabelframe',background='#111111',bordercolor='#3a3324',borderwidth=1,relief='solid');style.configure('Step.TLabelframe.Label',foreground=GOLD,font=('Segoe UI',11,'bold'))
        style.map('TCombobox',fieldbackground=[('readonly','#1e1e1e')],foreground=[('readonly','#ffffff')],selectbackground=[('readonly','#4b3510')])
        tabs=self.work.master;self.video=VideoPanel(tabs,self);tabs.insert(1,self.video,text='Video loop studio')
    def group(self,parent,title):return ttk.LabelFrame(parent,text=title,padding=10,style='Step.TLabelframe')
    def build_workspace(self):
        match=self.group(self.work,'01 / MATCH THE SHOPIFY PRODUCT');match.pack(fill='x',pady=(0,8))
        row=ttk.Frame(match);row.pack(fill='x')
        ttk.Label(row,text='Title / sku:CODE').pack(side='left',padx=(0,8));ttk.Entry(row,textvariable=self.search,width=36).pack(side='left',fill='x',expand=True)
        ttk.Button(row,text='Search Shopify',command=self.find_products).pack(side='left',padx=8)
        ttk.Button(row,text='Use selected product',command=self.use_product).pack(side='left')
        self.product_list=tk.Listbox(match,height=2,bg='#1d1d1d',fg='white',selectbackground='#4b3510',exportselection=False,font=('Segoe UI',10));self.product_list.pack(fill='x',pady=5);self.product_list.bind('<Double-1>',lambda e:self.use_product())
        self.product_label=ttk.Label(match,text='Upload target: none selected • connect Shopify in Connections & setup',foreground=GOLD);self.product_label.pack(anchor='w')
        self.row_entry(match,'Basic product name',self.name)
        body=ttk.Panedwindow(self.work,orient='horizontal');body.pack(fill='both',expand=True)
        left=ttk.Frame(body);right=ttk.Frame(body);body.add(left,weight=2);body.add(right,weight=3)
        views=self.group(left,'02 / IMPORT, SELECT & ORDER PHOTOS');views.pack(fill='both',expand=True,padx=(0,8))
        row=ttk.Frame(views);row.pack(fill='x')
        for label,cmd in [('Add photos',self.add_photos),('Add folder',self.add_folder),('Suggest 5',lambda:self.suggest(False)),('AI angles',lambda:self.suggest(True))]:ttk.Button(row,text=label,command=cmd).pack(side='left',padx=(0,4))
        ttk.Label(views,text='First included photo = mainshot. Double-click to include/exclude.',foreground=MUTED).pack(anchor='w',pady=6)
        tf=ttk.Frame(views);tf.pack(fill='both',expand=True)
        self.tree=ttk.Treeview(tf,columns=('use','file','view'),show='headings',selectmode='browse',height=5)
        for k,t,w in [('use','Use',40),('file','Photo',220),('view','View',110)]:self.tree.heading(k,text=t);self.tree.column(k,width=w,minwidth=35)
        sb=ttk.Scrollbar(tf,command=self.tree.yview);self.tree.configure(yscrollcommand=sb.set);sb.pack(side='right',fill='y');self.tree.pack(fill='both',expand=True)
        self.tree.bind('<<TreeviewSelect>>',self.on_select);self.tree.bind('<Double-1>',lambda e:self.toggle())
        bottom=ttk.Frame(views);bottom.pack(side='bottom',fill='x',before=tf,pady=6)
        row=ttk.Frame(bottom);row.pack(fill='x')
        for label,cmd in [('Include / exclude',self.toggle),('Up',lambda:self.move(-1)),('Down',lambda:self.move(1)),('Remove',self.remove)]:ttk.Button(row,text=label,command=cmd).pack(side='left',padx=(0,4))
        row=self.row_entry(bottom,'View label',self.view);ttk.Button(row,text='Apply',command=self.apply_view).pack(side='right',padx=5)
        names=self.group(left,'03 / BUILD FILENAMES & ALT TEXT');names.pack(side='bottom',fill='x',pady=(8,0),padx=(0,8),before=views)
        ttk.Button(names,text='Edit naming blocks',command=lambda:BlockEditor(self)).pack(anchor='w')
        self.name_example=ttk.Label(names,text='Select a photo to preview the filename and alt text.',wraplength=420,foreground=MUTED);self.name_example.pack(fill='x',pady=5)
        crop=self.group(right,'04 / FRAME THE TRANSPARENT MAINSHOT');crop.pack(fill='both',expand=True)
        row=ttk.Frame(crop);row.pack(fill='x')
        ttk.Button(row,text='Edit mainshot crop',command=self.start_crop).pack(side='left')
        ttk.Button(row,text='Finished preview',command=self.end_crop).pack(side='left',padx=6)
        ttk.Label(row,text='Aspect').pack(side='left',padx=(8,5));combo=ttk.Combobox(row,textvariable=self.vars['crop_aspect'],values=list(RATIOS),state='readonly',width=10);combo.pack(side='left');combo.bind('<<ComboboxSelected>>',lambda e:self.change_aspect())
        self.canvas=tk.Canvas(crop,bg='#080808',height=240,highlightthickness=0);self.canvas.pack(fill='both',expand=True,pady=6)
        self.canvas.bind('<Configure>',lambda e:self.schedule_preview());self.canvas.bind('<Button-1>',self.pointer_down);self.canvas.bind('<B1-Motion>',self.pointer_move);self.canvas.bind('<ButtonRelease-1>',self.pointer_up)
        crop_footer=ttk.Frame(crop);crop_footer.pack(side='bottom',fill='x',before=self.canvas)
        self.summary=ttk.Label(crop_footer,text='Drag inside the crop to move it; drag corner handles to resize.',foreground=MUTED);self.summary.pack(anchor='w')
        self.crop_fields={key:tk.StringVar(value='0') for key in ('Left','Top','Width','Height')}
        row=ttk.Frame(crop_footer);row.pack(fill='x',pady=5)
        for key,var in self.crop_fields.items():ttk.Label(row,text=key+' px').pack(side='left',padx=(0,3));ttk.Entry(row,textvariable=var,width=5).pack(side='left',padx=(0,7))
        ttk.Button(row,text='Apply',command=self.apply_pixel_crop).pack(side='left');ttk.Button(row,text='Reset',command=self.reset_crop).pack(side='left',padx=5)
        row=ttk.Frame(crop_footer);row.pack(fill='x',pady=2)
        for label,key in [('White threshold','white_threshold'),('Feather','white_feather')]:ttk.Label(row,text=label).pack(side='left',padx=(0,5));ttk.Entry(row,textvariable=self.vars[key],width=4).pack(side='left',padx=(0,10))
        ttk.Label(row,text='Logo on mainshot').pack(side='left');ttk.Combobox(row,textvariable=self.vars['main_logo'],values=['No','Yes'],state='readonly',width=5).pack(side='left',padx=5)
        logo=self.group(right,'05 / PLACE THE ATLAS LOGO');logo.pack(side='bottom',fill='x',pady=(8,0),before=crop)
        row=self.row_entry(logo,'Default logo file',self.vars['logo_path']);ttk.Button(row,text='Browse',command=self.browse_logo).pack(side='right',padx=5)
        row=ttk.Frame(logo);row.pack(fill='x',pady=4)
        for label,key in [('X px','logo_x'),('Y px','logo_y'),('Width %','logo_width'),('Opacity %','logo_opacity')]:ttk.Label(row,text=label).pack(side='left',padx=(0,4));ttk.Entry(row,textvariable=self.vars[key],width=6).pack(side='left',padx=(0,10))
        for label,a in [('Top left','tl'),('Top right','tr'),('Centre','c'),('Bottom left','bl'),('Bottom right','br')]:ttk.Button(logo,text=label,command=lambda anchor=a:self.pixel_preset(anchor),padding=4).pack(side='left',padx=2)
        out=self.group(self.work,'06 / EXPORT, REVIEW & UPLOAD');out.pack(side='bottom',fill='x',pady=(8,0),before=body)
        row=ttk.Frame(out);row.pack(fill='x',pady=3)
        for label,key in [('Output edge px','longest_edge'),('Target MB','max_mb'),('JPEG quality','quality')]:ttk.Label(row,text=label).pack(side='left',padx=(0,4));ttk.Entry(row,textvariable=self.vars[key],width=6).pack(side='left',padx=(0,10))
        ttk.Combobox(row,textvariable=self.vars['format'],values=['JPEG','PNG'],state='readonly',width=6).pack(side='left');ttk.Checkbutton(row,text='Square other images',variable=self.square).pack(side='left',padx=10)
        ttk.Label(row,text='Preview px').pack(side='left');ttk.Combobox(row,textvariable=self.vars['preview_edge'],values=['360','540','720','1080'],state='readonly',width=6).pack(side='left',padx=5)
        row=self.row_entry(out,'Export folder',self.vars['output_dir']);ttk.Button(row,text='Browse',command=self.browse_output).pack(side='right',padx=5)
        row=ttk.Frame(out);row.pack(fill='x',pady=4)
        for label,cmd,style in [('Export selected',self.export,'Gold.TButton'),('Approve & upload',self.upload,'TButton'),('Open exports',self.open_output,'TButton'),('Save defaults',self.save,'TButton'),('Clear batch',self.clear,'TButton')]:ttk.Button(row,text=label,command=cmd,style=style).pack(side='left',padx=(0,8))
        visual={'logo_path','logo_x','logo_y','logo_width','logo_opacity','longest_edge','white_threshold','white_feather','preview_edge','main_logo','crop_boxes'}
        for key,var in self.vars.items():var.trace_add('write',lambda *a,k=key:self.schedule_preview() if k in visual else self.update_names())
        self.name.trace_add('write',lambda *a:self.update_names());self.square.trace_add('write',lambda *a:self.schedule_preview())
    def build_connections(self):
        shop=self.group(self.conn,'01 / CONNECT SHOPIFY');shop.pack(fill='x',pady=(0,12))
        self.row_entry(shop,'Store domain',self.vars['shop']);self.row_entry(shop,'App Client ID',self.client_id)
        row=self.row_entry(shop,'App Client Secret',self.client_secret);row.winfo_children()[1].configure(show='•')
        row=self.row_entry(shop,'Admin API access token',self.token);row.winfo_children()[1].configure(show='•')
        ttk.Button(shop,text='Get / refresh 24-hour token',command=self.generate_token).pack(anchor='e')
        ttk.Label(shop,text='Use your permanent name.myshopify.com domain. Match products in the Photo workspace.',foreground=MUTED).pack(anchor='w',pady=5)
        ai=self.group(self.conn,'02 / OPTIONAL AI PHOTO SELECTION');ai.pack(fill='x',pady=(0,12))
        row=self.row_entry(ai,'OpenAI API key',self.ai_key);row.winfo_children()[1].configure(show='•');self.row_entry(ai,'Vision model',self.vars['model'])
        ttk.Label(ai,text='AI selection sends shortlisted photo previews to OpenAI when clicked. Separate API billing applies.',foreground=MUTED).pack(anchor='w')
        watch=self.group(self.conn,'03 / WATCH A PRODUCT FOLDER');watch.pack(fill='x',pady=(0,12))
        row=self.row_entry(watch,'Watch input folder',self.vars['watch_dir']);ttk.Button(row,text='Browse',command=self.browse_watch).pack(side='right',padx=5)
        ttk.Checkbutton(watch,text='Watch while open; add stable photos for review (one product per batch)',variable=self.watch).pack(anchor='w')
        save=self.group(self.conn,'04 / SAVE DEFAULTS & CREDENTIALS');save.pack(fill='x')
        for label,cmd in [('Save defaults',self.save),('Save credentials securely',self.save_secrets),('Forget saved credentials',self.forget_secrets)]:ttk.Button(save,text=label,command=cmd).pack(side='left',padx=(0,10))
    def pixel_box(self):
        i=self.current();path=self.photos[i]['path'];w,h=source_size(path);box=crop_for(path,self.get_settings());return [box[0]*w,box[1]*h,box[2]*w,box[3]*h],(w,h)
    def store_pixel_box(self,box,size):
        w,h=size;self.live_crop=None;self.set_crop([box[0]/w,box[1]/h,box[2]/w,box[3]/h])
    def draw_crop(self,path):
        box=self.live_crop or crop_for(path,self.get_settings());x,y,w,h=self.preview_bounds;self.canvas.delete('crop')
        coords=[x+box[0]*w,y+box[1]*h,x+box[2]*w,y+box[3]*h]
        self.canvas.create_rectangle(*coords,outline=GOLD,width=2,tags='crop')
        x0,y0,x1,y1=coords
        for px,py in [(x0,y0),(x1,y0),(x1,y1),(x0,y1)]:self.canvas.create_rectangle(px-5,py-5,px+5,py+5,fill=GOLD,outline='#111111',tags='crop')
    def pointer_down(self,e):
        if not self.crop_mode:return super().pointer_down(e)
        if self.busy or not hasattr(self,'preview_bounds'):return
        box,size=self.pixel_box();x,y,w,h=self.preview_bounds;bx=crop_for(self.photos[self.current()]['path'],self.get_settings());mode=None
        for corner,px,py in [('nw',bx[0],bx[1]),('ne',bx[2],bx[1]),('se',bx[2],bx[3]),('sw',bx[0],bx[3])]:
            if abs(e.x-(x+px*w))<=10 and abs(e.y-(y+py*h))<=10:mode=corner;break
        nx,ny=self.source_point(e);point=(nx*size[0],ny*size[1])
        if mode is None:mode='move' if box[0]<=point[0]<=box[2] and box[1]<=point[1]<=box[3] else 'draw'
        self.crop_gesture={'box':box,'size':size,'point':point,'mode':mode};self.canvas.configure(cursor='fleur' if mode=='move' else 'crosshair')
    def pointer_move(self,e):
        if not self.crop_mode:return super().pointer_move(e)
        if self.busy or not self.crop_gesture:return
        g=self.crop_gesture;box,size,point,mode=g['box'],g['size'],g['point'],g['mode'];nx,ny=self.source_point(e);current=(nx*size[0],ny*size[1]);ratio=RATIOS.get(self.vars['crop_aspect'].get())
        if mode=='move':new=move_box(box,current[0]-point[0],current[1]-point[1],size)
        elif mode=='draw':
            corner=('n' if current[1]<point[1] else 's')+('w' if current[0]<point[0] else 'e');new=resize_corner([point[0],point[1],point[0],point[1]],corner,current,size,ratio)
        else:new=resize_corner(box,mode,current,size,ratio)
        self.live_crop=[new[0]/size[0],new[1]/size[1],new[2]/size[0],new[3]/size[1]];self.draw_crop(self.photos[self.current()]['path'])
    def pointer_up(self,e):
        if not self.crop_mode:return super().pointer_up(e)
        if self.crop_gesture:
            self.pointer_move(e);self.crop_gesture=None;self.canvas.configure(cursor='')
            if self.live_crop:
                box=self.live_crop;w,h=self.pixel_box()[1]
                if (box[2]-box[0])*w>=1 and (box[3]-box[1])*h>=1:self.set_crop(box)
                self.live_crop=None
    def change_aspect(self):
        if self.current() is None:return
        box,size=self.pixel_box();self.store_pixel_box(fit_ratio(box,size,RATIOS.get(self.vars['crop_aspect'].get())),size)
    def enable_crop(self):
        self.crop_mode=True;self.change_aspect();self.sync_crop_fields();self.preview();self.status.set('Drag the crop interior to move it, corners to resize it, or outside to draw a new box.')
    def apply_pixel_crop(self):
        if self.current() is None:return
        try:
            _,size=self.pixel_box();left,top,cw,ch=[float(self.crop_fields[k].get()) for k in ('Left','Top','Width','Height')]
            if min(left,top)<0 or min(cw,ch)<1 or left+cw>size[0] or top+ch>size[1]:raise ValueError('Crop must fit inside the source photo.')
            self.store_pixel_box(fit_ratio([left,top,left+cw,top+ch],size,RATIOS.get(self.vars['crop_aspect'].get())),size);self.preview()
        except ValueError as e:messagebox.showerror('Crop',str(e))
    def reset_crop(self):
        if self.current() is None:return
        _,size=self.pixel_box();w,h=size;self.store_pixel_box(fit_ratio([0,0,w,h*.55],size,RATIOS.get(self.vars['crop_aspect'].get())),size)
    def close(self):
        if self.busy:messagebox.showinfo('Operation running','Wait for the current operation to finish.');return
        if hasattr(self,'video'):self.video.close()
        super().close()
