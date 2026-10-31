from tkinter import ttk
from studio_v3 import App as V4
from colour_ui import ColourEditor

class App(V4):
 def __init__(self):
  super().__init__();self.title('Atlas Tools | Photo & Video Studio 6.0')
  # Add colour access to each workspace without moving the existing step containers.
  strip=ttk.Frame(self.work,padding=(0,0,0,7));strip.pack(fill='x',before=self.work.winfo_children()[0])
  ttk.Button(strip,text='Colour Studio • Photo & Video',style='Gold.TButton',command=lambda:self.edit_colour('photo')).pack(side='left')
  ttk.Label(strip,text='Shared recipe • presets import/export • settings saved beside every export',foreground='#aaaaaa').pack(side='left',padx=14)
  ttk.Button(self.video.toolbar,text='Colour Studio',command=lambda:self.edit_colour('video')).pack(side='right',padx=5)
  self.vars['colour_json'].trace_add('write',lambda *a:self.schedule_preview())
  self.colour_editor=None
 def edit_colour(self,source):
  if self.busy:return
  if self.colour_editor is not None:
   try:
    if self.colour_editor.winfo_exists():self.colour_editor.lift();return
   except Exception:pass
  self.colour_editor=ColourEditor(self,source)

 def close(self):
  if not self.busy and self.colour_editor is not None:
   try:self.colour_editor.close()
   except Exception:pass
  super().close()
