"""Crop geometry in oriented source-image pixels; independent of Tk."""
RATIOS={'1:1':1.0,'4:3':4/3,'3:2':1.5,'16:9':16/9,'9:16':9/16,'Freehand':None}

def fit_ratio(box,size,ratio):
    w,h=size;x0,y0,x1,y1=box;cx=(x0+x1)/2;cy=(y0+y1)/2
    bw=max(1,x1-x0);bh=max(1,y1-y0)
    if ratio:
        if bw/bh>ratio:bw=bh*ratio
        else:bh=bw/ratio
    scale=min(1,w/bw,h/bh);bw*=scale;bh*=scale
    x0=max(0,min(w-bw,cx-bw/2));y0=max(0,min(h-bh,cy-bh/2))
    return [x0,y0,x0+bw,y0+bh]

def move_box(box,dx,dy,size):
    x0,y0,x1,y1=box;w,h=size
    dx=max(-x0,min(size[0]-x1,dx));dy=max(-y0,min(size[1]-y1,dy))
    return [x0+dx,y0+dy,x1+dx,y1+dy]

def resize_corner(box,corner,point,size,ratio=None):
    w,h=size;x0,y0,x1,y1=box
    fixed={'nw':(x1,y1),'ne':(x0,y1),'se':(x0,y0),'sw':(x1,y0)}[corner]
    sx=-1 if corner in ('nw','sw') else 1;sy=-1 if corner in ('nw','ne') else 1
    fx,fy=fixed;px,py=point
    bw=max(1,sx*(px-fx));bh=max(1,sy*(py-fy))
    maxw=fx if sx<0 else w-fx;maxh=fy if sy<0 else h-fy
    if ratio:
        if bw/bh>ratio:bh=bw/ratio
        else:bw=bh*ratio
        scale=min(1,maxw/bw,maxh/bh);bw*=scale;bh*=scale
    else:bw=min(bw,maxw);bh=min(bh,maxh)
    px=fx+sx*bw;py=fy+sy*bh
    return [min(px,fx),min(py,fy),max(px,fx),max(py,fy)]
