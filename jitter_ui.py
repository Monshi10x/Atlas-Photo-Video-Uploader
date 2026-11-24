"""Shared controls for automatic and standalone second-pass jitter removal."""
from dataclasses import replace
import tkinter as tk
from tkinter import ttk,messagebox


class JitterControls(ttk.LabelFrame):
    def __init__(self,parent,s,toggle=True):
        super().__init__(parent,text='03 / SECOND PASS — RESIDUAL JITTER',padding=8)
        self.enabled=tk.BooleanVar(value=s.second_pass)
        if toggle:ttk.Checkbutton(self,text='Run a second pass on the completed first-pass video',variable=self.enabled).pack(anchor='w')
        else:self.enabled.set(True)
        self.mode=tk.StringVar(value=s.second_mode)
        row=ttk.Frame(self);row.pack(fill='x',pady=4);ttk.Label(row,text='Strategy').pack(side='left');ttk.Combobox(row,textvariable=self.mode,values=('smooth','lock'),state='readonly',width=10).pack(side='left',padx=8)
        ttk.Label(row,text='smooth: reduce quick jitter • lock: pin measured axis vertically at a fixed position').pack(side='left')
        self.v={k:tk.StringVar(value=str(getattr(s,k))) for k in ('second_strength','second_smoothing','second_max_shift','second_max_angle')}
        row=ttk.Frame(self);row.pack(fill='x',pady=4)
        for k,label in [('second_strength','Strength %'),('second_smoothing','Smooth seconds'),('second_max_shift','Max shift px'),('second_max_angle','Max angle °')]:
            ttk.Label(row,text=label).pack(side='left');entry=ttk.Entry(row,textvariable=self.v[k],width=7);entry.pack(side='left',padx=(4,12))
            if k=='second_smoothing':self.smooth_entry=entry
        self.mode.trace_add('write',lambda *args:self.smooth_entry.configure(state='disabled' if self.mode.get()=='lock' else 'normal'))
        self.smooth_entry.configure(state='disabled' if self.mode.get()=='lock' else 'normal')
        ttk.Label(self,text='Measures the rendered shaft again. Small sideways/tilt corrections; preserves spin, frame count and alpha.').pack(anchor='w')
    def values(self):
        return {'second_pass':self.enabled.get(),'second_mode':self.mode.get(),**{k:float(v.get()) for k,v in self.v.items()}}
    def load(self,s):
        self.enabled.set(s.second_pass)
        self.mode.set(s.second_mode)
        for k,v in self.v.items():v.set(str(getattr(s,k)))


class JitterDialog(tk.Toplevel):
    def __init__(self,panel):
        super().__init__(panel);self.panel=panel;self.first=panel.processed;self.title('Second pass • processed footage');self.geometry('900x290');self.transient(panel.app)
        ttk.Label(self,text='Read the current first-pass result and remove remaining shaft-axis jitter.',padding=12).pack(anchor='w')
        self.controls=JitterControls(self,self.first.effects,toggle=False);self.controls.pack(fill='x',padx=12)
        ttk.Button(self,text='Run second pass on processed video',style='Gold.TButton',command=self.apply).pack(side='right',padx=12,pady=12)
    def apply(self):
        try:
            s=replace(self.first.effects,**self.controls.values());s.validate()
        except Exception as e:messagebox.showerror('Second-pass settings',str(e),parent=self);return
        self.panel.apply_second_pass(s);self.destroy()
