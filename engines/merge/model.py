import argparse, math, random, subprocess, shutil, wave, struct, tempfile, os
from dataclasses import dataclass
from pathlib import Path
import cv2, numpy as np

LEVEL_RADII = {1:24,2:30,3:37,4:45,5:54,6:64,7:75,8:88}

def level_radius(level, percent=0.0):
    base = LEVEL_RADII[int(level)]
    if int(level) == 1:
        return base
    return max(2, round(base * (1.0 + float(percent) / 100.0)))

LEVEL_COLORS = {
1:(80,80,255),2:(80,180,255),3:(80,255,180),4:(80,255,255),
5:(255,180,80),6:(255,100,180),7:(220,100,255),8:(255,255,255)}
EXTS = (".webp",".png",".jpg",".jpeg")

def skin_path(folder, level):
    p=Path(folder)
    for ext in EXTS:
        f=p/f"{level}{ext}"
        if f.exists(): return f
    return None

def load_skins(folder):
    out={}
    for lv in range(1,9):
        p=skin_path(folder,lv)
        if p:
            im=cv2.imread(str(p),cv2.IMREAD_UNCHANGED)
            if im is not None: out[lv]=im
    return out


@dataclass
class Ball:
    x:float; y:float; vx:float; vy:float; level:int; id:int
    pending:bool=False
    percent:float=0.0
    @property
    def r(self): return level_radius(self.level, self.percent)
    @property
    def mass(self): return max(1.0,(self.r/24.0)**2)

def same_level_merge(a,b):
    return (not a.pending and not b.pending and a.level==b.level)

def momentum_velocity(a,b):
    m=a.mass+b.mass
    return ((a.vx*a.mass+b.vx*b.mass)/m,(a.vy*a.mass+b.vy*b.mass)/m)

def circle_pipe_opening_contains(x,cx,pipe_w,ball_r):
    return abs(x-cx) <= max(0,pipe_w/2-ball_r)

def draw_skin(img, skin, cx, cy, r):
    if skin is None: return False
    size=max(2,int(2*r))
    im=cv2.resize(skin,(size,size),interpolation=cv2.INTER_AREA)
    yy1=max(0,cy-r); yy2=min(img.shape[0],cy+r)
    xx1=max(0,cx-r); xx2=min(img.shape[1],cx+r)
    if yy2<=yy1 or xx2<=xx1:return False
    sy1=yy1-(cy-r); sy2=sy1+(yy2-yy1); sx1=xx1-(cx-r); sx2=sx1+(xx2-xx1)
    crop=im[sy1:sy2,sx1:sx2]
    mask=np.zeros((crop.shape[0],crop.shape[1]),np.uint8)
    cv2.circle(mask,(crop.shape[1]//2,crop.shape[0]//2),min(crop.shape[:2])//2,255,-1)
    if crop.shape[2] == 4:
        alpha=(crop[:,:,3].astype(np.float32)/255.0)*(mask.astype(np.float32)/255.0)
        rgb=crop[:,:,:3]
    else:
        alpha=mask.astype(np.float32)/255.0; rgb=crop[:,:,:3]
    roi=img[yy1:yy2,xx1:xx2]
    img[yy1:yy2,xx1:xx2]=(rgb*alpha[:,:,None]+roi*(1-alpha[:,:,None])).astype(np.uint8)
    return True

