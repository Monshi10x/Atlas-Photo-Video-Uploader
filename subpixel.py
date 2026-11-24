"""Continuous-coordinate linear/cubic resampling for tiny corrections."""
import numpy as np
from scipy.ndimage import affine_transform,spline_filter


class SubpixelSampler:
    def __init__(self,image,transparent=False,quality='cubic'):
        self.a=np.asarray(image);self.transparent=transparent;self.h,self.w=self.a.shape[:2]
        self.order=1 if quality=='subpixel' else 3
        self.opaque_alpha=self.a.shape[2]==4 and not transparent and np.all(self.a[:,:,3]==255)
        work=(self.a[:,:,:3] if self.opaque_alpha else self.a).astype(np.float32)
        if transparent:
            work=work.copy();work[:,:,:3]*=work[:,:,3:4]/255
        self.mode='grid-constant' if transparent else 'mirror'
        # Filter once per frame, then reuse coefficients for crop checks and
        # final render. Float planes retain fractions smaller than one pixel.
        self.coeff=[spline_filter(work[:,:,j],order=3,output=np.float32,mode=self.mode) if self.order==3 else work[:,:,j] for j in range(work.shape[2])]
    def render(self,matrix,crop=None):
        left,top,right,bottom=crop or (0,0,self.w,self.h)
        inverse=np.linalg.inv(np.vstack((matrix,[0,0,1])))
        yx=inverse[:2,:2][::-1,::-1]
        offset=(inverse[:2,:2]@np.array([left,top])+inverse[:2,2])[::-1]
        out=np.stack([affine_transform(p,yx,offset,output_shape=(bottom-top,right-left),order=self.order,mode=self.mode,cval=0,prefilter=False) for p in self.coeff],axis=2)
        if self.transparent:
            # Cubic alpha can overshoot at an edge. Unpremultiply with that
            # same raw alpha before clipping it, otherwise colours get halos.
            alpha=out[:,:,3:4].copy()
            out[:,:,:3]=np.divide(out[:,:,:3]*255,alpha,out=np.zeros_like(out[:,:,:3]),where=alpha>.25);out[:,:,3:4]=np.clip(alpha,0,255)
        out=np.rint(np.clip(out,0,255)).astype(np.uint8)
        if self.opaque_alpha:out=np.dstack((out,np.full(out.shape[:2],255,np.uint8)))
        return out


def precision_warp(image,matrix,transparent=False,quality='cubic'):
    return SubpixelSampler(image,transparent,quality).render(matrix)


