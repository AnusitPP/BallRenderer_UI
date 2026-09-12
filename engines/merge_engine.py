import argparse, math, random, subprocess, shutil, wave, struct, tempfile, os
from dataclasses import dataclass
from pathlib import Path
import cv2, numpy as np

LEVEL_RADII = {1:24,2:30,3:37,4:45,5:54,6:64,7:75,8:88}
LEVEL_SIZE_PERCENT = 0.0

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


def _write_event_wav(path, events, duration, volume=0.8, sample_rate=44100):
    n=max(1,int(duration*sample_rate))
    audio=np.zeros(n,dtype=np.float32)
    for t,lv,is_victory in events:
        start=max(0,int(t*sample_rate))
        dur=0.42 if is_victory else 0.14+lv*0.018
        count=min(n-start,max(1,int(dur*sample_rate)))
        if count<=0: continue
        tt=np.arange(count,dtype=np.float32)/sample_rate
        freq=(760.0 if is_victory else 220.0*(2**((lv-1)/12.0)))
        env=np.exp(-tt*(5.0 if is_victory else 18.0))
        tone=(np.sin(2*np.pi*freq*tt)+0.35*np.sin(2*np.pi*freq*2*tt))*env
        audio[start:start+count]+=tone*(0.35+0.05*lv)
    peak=float(np.max(np.abs(audio))) if len(audio) else 0
    if peak>1: audio/=peak
    audio=np.clip(audio*float(volume),-1,1)
    pcm=(audio*32767).astype(np.int16)
    with wave.open(str(path),"wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sample_rate); w.writeframes(pcm.tobytes())


def find_ffmpeg():
    env=os.environ.get("FFMPEG_EXE","").strip()
    candidates=[
        env,
        shutil.which("ffmpeg") or "",
        str(Path(__file__).resolve().parents[1] / "ffmpeg.exe"),
        r"C:\Users\Acer\Downloads\ffmpeg-9.0.1-essentials_build\bin\ffmpeg.exe",
    ]
    for item in candidates:
        if item and Path(item).is_file():
            return str(Path(item))
    return None

def audio_mux_plan(events, merge_sound_file="", victory_sound_file=""):
    # All events are rendered into one temporary timeline before the final mux.
    return {"ffmpeg_input_count": 2, "event_count": len(events)}

def _decode_audio_mono(path, ffmpeg, sample_rate=44100):
    """Decode any FFmpeg-supported audio file to mono float32 PCM."""
    if not path or not Path(path).is_file():
        return None
    cmd=[ffmpeg,"-v","error","-i",str(path),"-f","f32le","-ac","1","-ar",str(sample_rate),"pipe:1"]
    result=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if result.returncode!=0 or not result.stdout:
        return None
    return np.frombuffer(result.stdout,dtype=np.float32).copy()

def _mix_audio_timeline(path, events, duration, volume, merge_clip=None, victory_clip=None, sample_rate=44100):
    n=max(1,int((duration+1.0)*sample_rate))
    audio=np.zeros(n,dtype=np.float32)
    for t,lv,is_victory in events:
        clip=victory_clip if is_victory else merge_clip
        if clip is None:
            # fallback generated sound
            dur=0.42 if is_victory else 0.14+lv*0.018
            count=max(1,int(dur*sample_rate))
            tt=np.arange(count,dtype=np.float32)/sample_rate
            freq=760.0 if is_victory else 220.0*(2**((lv-1)/12.0))
            env=np.exp(-tt*(5.0 if is_victory else 18.0))
            clip=((np.sin(2*np.pi*freq*tt)+0.35*np.sin(2*np.pi*freq*2*tt))*env).astype(np.float32)
        start=max(0,int(t*sample_rate))
        count=min(len(clip),n-start)
        if count>0:
            audio[start:start+count]+=clip[:count]
    peak=float(np.max(np.abs(audio))) if len(audio) else 0.0
    if peak>1.0: audio/=peak
    audio=np.clip(audio*float(volume),-1,1)
    pcm=(audio*32767).astype(np.int16)
    with wave.open(str(path),"wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sample_rate); w.writeframes(pcm.tobytes())

def mux_merge_audio(video_path, events, args):
    if not args.merge_sound or not events:
        return
    ffmpeg=find_ffmpeg()
    if not ffmpeg:
        print("WARNING: FFmpeg not found; Merge audio skipped.", flush=True)
        return
    video=Path(video_path)
    if not video.exists():
        return
    tmp=video.with_name(video.stem+"_silent.mp4")
    timeline=video.with_name(video.stem+"_audio_timeline.wav")
    merge_clip=_decode_audio_mono(args.merge_sound_file,ffmpeg) if args.merge_sound_file else None
    victory_clip=_decode_audio_mono(args.victory_sound_file,ffmpeg) if args.victory_sound_file else None
    _mix_audio_timeline(timeline,events,args.seconds,args.merge_volume,merge_clip,victory_clip)
    video.replace(tmp)
    # Constant-size command: only silent video + one pre-mixed WAV timeline.
    cmd=[ffmpeg,"-y","-v","error","-i",str(tmp),"-i",str(timeline),
         "-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","aac","-shortest",str(video)]
    result=subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    if result.returncode!=0:
        print("WARNING: audio mux failed: "+result.stderr.decode(errors="replace")[-500:], flush=True)
        tmp.replace(video)
    else:
        tmp.unlink(missing_ok=True)
    timeline.unlink(missing_ok=True)

@dataclass
class Ball:
    x:float; y:float; vx:float; vy:float; level:int; id:int
    pending:bool=False
    @property
    def r(self): return level_radius(self.level, LEVEL_SIZE_PERCENT)
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

def render(args):
    global LEVEL_SIZE_PERCENT
    LEVEL_SIZE_PERCENT = float(args.level_size_percent)
    sound_events=[]
    W,H=args.width,args.height
    cx=W//2; cy=int(H*0.62); R=int(min(W*0.455,H*0.34) * args.tank_scale)
    # Pipe inner width follows LV1 diameter plus adjustable clearance.
    pipe_w=int(LEVEL_RADII[1] * 2 + args.pipe_clearance)
    pipe_top=max(30,cy-R-int(H*0.22))
    opening_y=cy-R
    skins=load_skins(args.assets)
    balls=[]; effects=[]; next_id=1; t=0.; spawn_t=0.; victory=False; victory_t=None
    dt=1/args.physics_hz
    writer=cv2.VideoWriter(args.out,cv2.VideoWriter_fourcc(*"mp4v"),args.fps,(W,H))
    frames=int(args.seconds*args.fps); sub=max(1,round(args.physics_hz/args.fps))
    rng=random.Random(args.seed)
    for fi in range(frames):
        for _ in range(sub):
            if not victory and t>=spawn_t:
                balls.append(Ball(cx+rng.uniform(-pipe_w*.15,pipe_w*.15),pipe_top+30,rng.uniform(-18,18),0,1,next_id))
                next_id+=1; spawn_t += args.spawn_interval
            # integrate
            for b in balls:
                b.vy += args.gravity*dt
                b.x += b.vx*dt; b.y += b.vy*dt
                r=b.r
                # pipe walls while above circle opening
                if b.y < opening_y+r:
                    left=cx-pipe_w/2+r; right=cx+pipe_w/2-r
                    if b.x<left: b.x=left; b.vx=abs(b.vx)*args.bounce
                    if b.x>right: b.x=right; b.vx=-abs(b.vx)*args.bounce
                # circular tank collision, except permanent top opening
                dx=b.x-cx; dy=b.y-cy; d=math.hypot(dx,dy) or 1
                if d+r>R:
                    angle=math.atan2(dy,dx)
                    at_top = dy<0 and circle_pipe_opening_contains(b.x,cx,pipe_w,r) and b.y <= opening_y+r*1.8
                    if not at_top:
                        nx,ny=dx/d,dy/d
                        b.x=cx+nx*(R-r); b.y=cy+ny*(R-r)
                        vn=b.vx*nx+b.vy*ny
                        if vn>0:
                            b.vx-= (1+args.bounce)*vn*nx
                            b.vy-= (1+args.bounce)*vn*ny
            # ball collisions / merge
            merges=[]
            for i in range(len(balls)):
                a=balls[i]
                if a.pending: continue
                for j in range(i+1,len(balls)):
                    b=balls[j]
                    if b.pending: continue
                    dx=b.x-a.x; dy=b.y-a.y; dist=math.hypot(dx,dy) or .001
                    min_d=a.r+b.r
                    if dist < min_d:
                        nx,ny=dx/dist,dy/dist
                        if same_level_merge(a,b):
                            a.pending=b.pending=True
                            merges.append((a,b)); break
                        overlap=min_d-dist
                        a.x-=nx*overlap*.5; a.y-=ny*overlap*.5
                        b.x+=nx*overlap*.5; b.y+=ny*overlap*.5
                        rvx=b.vx-a.vx; rvy=b.vy-a.vy
                        rel=rvx*nx+rvy*ny
                        if rel<0:
                            imp=-(1+args.bounce)*rel/(1/a.mass+1/b.mass)
                            a.vx-=imp*nx/a.mass; a.vy-=imp*ny/a.mass
                            b.vx+=imp*nx/b.mass; b.vy+=imp*ny/b.mass
            if merges:
                remove=set()
                new=[]
                for a,b in merges:
                    remove|={a.id,b.id}
                    mx,my=(a.x+b.x)/2,(a.y+b.y)/2
                    vx,vy=momentum_velocity(a,b)
                    if a.level==8:
                        victory=True; victory_t=t
                        sound_events.append((t,8,True))
                        effects.append([mx,my,0.0,8,1.0])
                    else:
                        lv=a.level+1
                        sound_events.append((t,lv,False))
                        new.append(Ball(mx,my,vx,vy,lv,next_id)); next_id+=1
                        effects.append([mx,my,0.0,lv,1.0])
                balls=[b for b in balls if b.id not in remove]+new
            for e in effects: e[2]+=dt; e[4]=max(0,e[4]-dt*1.7)
            effects=[e for e in effects if e[4]>0]
            t+=dt
        img=np.zeros((H,W,3),np.uint8)
        # arena: perfect circle with top circumference erased only at pipe opening
        cv2.circle(img,(cx,cy),R,(230,230,230),4,cv2.LINE_AA)
        # erase the circle segment under pipe, then draw straight open pipe sides
        y=openning_y=opening_y
        cv2.rectangle(img,(cx-pipe_w//2-4,y-12),(cx+pipe_w//2+4,y+16),(0,0,0),-1)
        cv2.line(img,(cx-pipe_w//2,pipe_top),(cx-pipe_w//2,y),(230,230,230),4,cv2.LINE_AA)
        cv2.line(img,(cx+pipe_w//2,pipe_top),(cx+pipe_w//2,y),(230,230,230),4,cv2.LINE_AA)
        for b in balls:
            c=LEVEL_COLORS[b.level]; x,y=int(b.x),int(b.y); r=int(b.r)
            if not draw_skin(img,skins.get(b.level),x,y,r):
                cv2.circle(img,(x,y),r,c,-1,cv2.LINE_AA)
        for ex,ey,age,lv,alpha in effects:
            rr=int(level_radius(lv, args.level_size_percent)*(1+age*5))
            col=LEVEL_COLORS[lv]
            cv2.circle(img,(int(ex),int(ey)),rr,col,max(1,int(5*alpha)),cv2.LINE_AA)
            for k in range(12):
                ang=k*math.tau/12
                d=rr*.75
                px=int(ex+math.cos(ang)*d); py=int(ey+math.sin(ang)*d)
                cv2.circle(img,(px,py),max(1,int(4*alpha)),col,-1,cv2.LINE_AA)
        if victory:
            text="VICTORY  LV8 + LV8"
            (tw,_),_=cv2.getTextSize(text,cv2.FONT_HERSHEY_SIMPLEX,1.1,3)
            cv2.putText(img,text,((W-tw)//2,H//2),cv2.FONT_HERSHEY_SIMPLEX,1.1,(255,255,255),3,cv2.LINE_AA)
        writer.write(img)
        if fi % max(1, frames // 100) == 0:
            print(f"APP_PROGRESS {100.0 * (fi + 1) / max(1, frames):.2f} Merge Ball LV1-8", flush=True)
    writer.release()
    mux_merge_audio(args.out, sound_events, args)
    print("APP_PROGRESS 100.00 เสร็จแล้ว", flush=True)

def cli(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--out",default="output/merge_ball.mp4")
    p.add_argument("--assets",default="assets/balls")
    p.add_argument("--width",type=int,default=540); p.add_argument("--height",type=int,default=960)
    p.add_argument("--fps",type=int,default=60); p.add_argument("--physics-hz",type=int,default=240)
    p.add_argument("--seconds",type=float,default=30); p.add_argument("--spawn-interval",type=float,default=.8)
    p.add_argument("--gravity",type=float,default=980); p.add_argument("--bounce",type=float,default=.78)
    p.add_argument("--tank-scale",type=float,default=1.0)
    p.add_argument("--pipe-clearance",type=float,default=8.0)
    p.add_argument("--seed",type=int,default=7)
    p.add_argument("--level-size-percent",type=float,default=0.0)
    p.add_argument("--merge-sound",action="store_true")
    p.add_argument("--merge-volume",type=float,default=0.8)
    p.add_argument("--merge-sound-file",default="")
    p.add_argument("--victory-sound-file",default="")
    return p.parse_args(argv)

def main(argv=None):
    render(cli(argv))

if __name__=="__main__": main()
