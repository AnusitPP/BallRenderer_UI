"""Legacy Merge integration shared by live preview and final rendering."""
from .model import *

class MergeSimulation:
    def __init__(self, config):
        self.config=config
        args=config
        W,H=args.width,args.height
        cx=W//2; cy=int(H*0.62); R=int(min(W*0.455,H*0.34) * args.tank_scale)
        # Pipe inner width follows LV1 diameter plus adjustable clearance.
        pipe_w=int(LEVEL_RADII[1] * 2 + args.pipe_clearance)
        pipe_count=max(1,min(3,int(getattr(args,'pipe_count',1))))
        pipe_span=min(R*.48,max(0,(pipe_count-1)*(pipe_w+12)/2))
        pipe_centers=[cx] if pipe_count==1 else [cx-pipe_span+(2*pipe_span*i/(pipe_count-1)) for i in range(pipe_count)]
        pipe_top=max(30,cy-R-int(H*0.22))
        opening_y=cy-R
        skins=load_skins(args.assets,getattr(args,'asset_files',None))
        balls=[]; effects=[]; next_id=1; t=0.; spawn_t=0.; victory=False; victory_t=None
        dt=1/args.physics_hz
        rng=random.Random(args.seed)
        sound_events=[]
        self.W=W
        self.H=H
        self.cx=cx
        self.cy=cy
        self.R=R
        self.pipe_w=pipe_w
        self.pipe_centers=pipe_centers
        self.spawn_pipe_history=[]
        self.spawn_index=0
        self.pipe_top=pipe_top
        self.opening_y=opening_y
        self.skins=skins
        self.balls=balls
        self.effects=effects
        self.next_id=next_id
        self.t=t
        self.spawn_t=spawn_t
        self.victory=victory
        self.victory_t=victory_t
        self.rng=rng
        self.sound_events=sound_events
        self.dt=dt
        self.frame_index=0
        self.total_frames=max(1,int(float(args.seconds)*int(args.fps)))
        self.collision_count=0
        self.rotation=0.0
        self.substeps=max(1,round(args.physics_hz/args.fps))

    @property
    def state(self): return self
    @property
    def particles(self): return self.effects
    @property
    def elapsed_time(self): return self.t
    @property
    def audio_events(self): return self.sound_events
    @property
    def status(self): return 'victory' if self.victory else 'running'

    def advance_frame(self):
        for _ in range(self.substeps): self.step(self.dt)
        self.frame_index+=1
        return self.state

    def step(self, dt):
        args=self.config
        W=self.W
        H=self.H
        cx=self.cx
        cy=self.cy
        R=self.R
        pipe_w=self.pipe_w
        pipe_centers=self.pipe_centers
        pipe_top=self.pipe_top
        opening_y=self.opening_y
        skins=self.skins
        balls=self.balls
        effects=self.effects
        next_id=self.next_id
        t=self.t
        spawn_t=self.spawn_t
        victory=self.victory
        victory_t=self.victory_t
        rng=self.rng
        sound_events=self.sound_events
        spawn_index=self.spawn_index
        if not victory and t>=spawn_t:
            pipe_x=pipe_centers[spawn_index%len(pipe_centers)]; spawn_index+=1
            self.spawn_pipe_history.append(pipe_x)
            balls.append(Ball(pipe_x+rng.uniform(-pipe_w*.15,pipe_w*.15),pipe_top+30,rng.uniform(-18,18),0,1,next_id,percent=args.level_size_percent))
            next_id+=1; spawn_t += args.spawn_interval
        # integrate
        for b in balls:
            b.vy += args.gravity*dt
            b.x += b.vx*dt; b.y += b.vy*dt
            r=b.r
            # pipe walls while above circle opening
            if b.y < opening_y+r:
                pipe_x=min(pipe_centers,key=lambda value:abs(value-b.x))
                left=pipe_x-pipe_w/2+r; right=pipe_x+pipe_w/2-r
                if b.x<left: b.x=left; b.vx=abs(b.vx)*args.bounce
                if b.x>right: b.x=right; b.vx=-abs(b.vx)*args.bounce
            # circular tank collision, except permanent top opening
            dx=b.x-cx; dy=b.y-cy; d=math.hypot(dx,dy) or 1
            if d+r>R:
                angle=math.atan2(dy,dx)
                at_top = dy<0 and any(circle_pipe_opening_contains(b.x,pipe_x,pipe_w,r) for pipe_x in pipe_centers) and b.y <= opening_y+r*1.8
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
                    self.collision_count += 1
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
                    sound_events.append((t,9,True))
                    new.append(Ball(mx,my,vx,vy,9,next_id,percent=args.level_size_percent)); next_id+=1
                    effects.append([mx,my,0.0,9,1.0])
                else:
                    lv=a.level+1
                    sound_events.append((t,lv,False))
                    new.append(Ball(mx,my,vx,vy,lv,next_id,percent=args.level_size_percent)); next_id+=1
                    effects.append([mx,my,0.0,lv,1.0])
            balls=[b for b in balls if b.id not in remove]+new
        for e in effects: e[2]+=dt; e[4]=max(0,e[4]-dt*1.7)
        effects=[e for e in effects if e[4]>0]
        t+=dt
        self.W=W
        self.H=H
        self.cx=cx
        self.cy=cy
        self.R=R
        self.pipe_w=pipe_w
        self.pipe_top=pipe_top
        self.opening_y=opening_y
        self.skins=skins
        self.balls=balls
        self.effects=effects
        self.next_id=next_id
        self.t=t
        self.spawn_t=spawn_t
        self.victory=victory
        self.victory_t=victory_t
        self.rng=rng
        self.sound_events=sound_events
        self.spawn_index=spawn_index
        return self.state

    def draw_frame(self, width=None, height=None):
        args=self.config
        W=self.W
        H=self.H
        cx=self.cx
        cy=self.cy
        R=self.R
        pipe_w=self.pipe_w
        pipe_centers=self.pipe_centers
        pipe_top=self.pipe_top
        opening_y=self.opening_y
        skins=self.skins
        balls=self.balls
        effects=self.effects
        next_id=self.next_id
        t=self.t
        spawn_t=self.spawn_t
        victory=self.victory
        victory_t=self.victory_t
        dt=self.dt
        rng=self.rng
        sound_events=self.sound_events
        img=np.zeros((H,W,3),np.uint8)
        # arena: perfect circle with top circumference erased only at pipe opening
        cv2.circle(img,(cx,cy),R,(230,230,230),4,cv2.LINE_AA)
        # erase the circle segment under pipe, then draw straight open pipe sides
        y=openning_y=opening_y
        for pipe_x in pipe_centers:
            pipe_x=int(round(pipe_x))
            cv2.rectangle(img,(pipe_x-pipe_w//2-4,y-12),(pipe_x+pipe_w//2+4,y+16),(0,0,0),-1)
            cv2.line(img,(pipe_x-pipe_w//2,pipe_top),(pipe_x-pipe_w//2,y),(230,230,230),4,cv2.LINE_AA)
            cv2.line(img,(pipe_x+pipe_w//2,pipe_top),(pipe_x+pipe_w//2,y),(230,230,230),4,cv2.LINE_AA)
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
        if width is not None or height is not None:
            width=int(width or round(W*height/H))
            height=int(height or round(H*width/W))
            if (width,height)!=(W,H):
                img=cv2.resize(img,(width,height),interpolation=cv2.INTER_AREA)
        return img
