"""Frame-based falling-ball shatter simulation."""
from dataclasses import dataclass
from pathlib import Path
import math
import cv2
import numpy as np

from core.simulation_state import SimulationState
from engines.circle.drawing import parse_hex_color, draw_skin_circle


def recommended_foam_count(frame_width, ball_percent, foam_radius=8.0):
    """Estimate visible foam from projected ball area."""
    ball_radius=max(1.0,float(frame_width)*float(ball_percent)/200.0)
    piece_radius=max(1.0,float(foam_radius))
    return max(80,min(5000,int(round((ball_radius/piece_radius)**2*4.0))))


@dataclass
class DropBall:
    pos: np.ndarray
    vel: np.ndarray
    radius: float
    color: tuple
    alive: bool = True


@dataclass
class DropParticle:
    pos: np.ndarray
    vel: np.ndarray
    radius: float
    color: tuple
    life: float


class DropSimulation:
    def __init__(self, config):
        self.config = config
        self.W, self.H = int(config.width), int(config.height)
        self.FPS = max(1, int(config.fps))
        self.dt = 1.0 / self.FPS
        self.total_frames = max(1, int(float(config.seconds) * self.FPS))
        self.frame_index = 0
        self.elapsed_time = 0.0
        self.rng = np.random.default_rng(config.seed)
        self.box_left = self.W * .10
        self.box_right = self.W * .90
        self.box_bottom = self.H * .90
        self.box_top = self.H * .25
        spike_height = float(config.spike_height)
        spike_half_width = max(18.0, min(self.W * .13, spike_height * .58))
        center_x = self.W * .5
        self.spikes = [np.array([[center_x-spike_half_width,self.box_bottom],[center_x+spike_half_width,self.box_bottom],[center_x,self.box_bottom-spike_height]],dtype=np.float64)]
        self.balls = []
        self.particles = []
        self.audio_events = []
        self.floor_sound_accumulator = 0.0
        self.shatter_count = 0
        self.total_particles_created = 0
        self.size_script=[]
        for raw in str(getattr(config,'size_script','')).split(','):
            try:
                if raw.strip(): self.size_script.append(max(1.0,min(1000.0,float(raw))))
            except ValueError:
                continue
        self.script_index=0
        self.next_spawn = float(config.segment_seconds) if self.size_script else float(config.spawn_interval)
        self.skin = cv2.imread(str(config.ball_image), cv2.IMREAD_UNCHANGED) if config.ball_image and Path(config.ball_image).is_file() else None
        foam_image=getattr(config,'foam_image','')
        self.foam_skin = cv2.imread(str(foam_image), cv2.IMREAD_UNCHANGED) if foam_image and Path(foam_image).is_file() else None
        self.state = SimulationState()
        if self.size_script:
            self._spawn_ball(self.W*self.size_script[0]/200.0); self.script_index=1
        else:
            self._spawn_ball()
        self._sync()

    def _spawn_ball(self,radius=None):
        radius = float(self.config.ball_size if radius is None else radius)
        x = self.W * .5
        self.balls.append(DropBall(np.array([x, -radius]), np.array([self.rng.uniform(-25, 25), float(self.config.initial_speed)]), radius, parse_hex_color(self.config.ball_color)))

    def _shatter(self, ball):
        if getattr(self.config,'auto_foam_from_size',0):
            percent=ball.radius*200.0/self.W
            desired_count=recommended_foam_count(self.W,percent,self.config.particle_size)
            budget=max(50,min(5000,int(getattr(self.config,'particle_budget',600))))
            count=min(desired_count,budget)
            radius_scale=min(4.0,math.sqrt(desired_count/max(1,count)))
        else:
            count = max(1, int(self.config.particle_count))
            radius_scale=1.0
        for _ in range(count):
            angle = self.rng.uniform(math.pi * 1.05, math.pi * 1.95)
            speed = self.rng.uniform(float(self.config.particle_speed) * .55, float(self.config.particle_speed))
            velocity = np.array([math.cos(angle) * speed, math.sin(angle) * speed])
            radius = self.rng.uniform(max(1.0, self.config.particle_size * .45), max(1.0, self.config.particle_size))*radius_scale
            spread_angle=self.rng.uniform(0.0,math.tau)
            spread_radius=ball.radius*1.35*math.sqrt(self.rng.uniform(0.0,1.0))
            offset=np.array([math.cos(spread_angle),math.sin(spread_angle)])*spread_radius
            self.particles.append(DropParticle(ball.pos.copy()+offset, velocity, radius, parse_hex_color(self.config.foam_color), float(self.config.particle_life)))
        self.total_particles_created += count
        self.shatter_count += 1
        # advance_frame draws the updated state as the current video frame,
        # whose timestamp is one frame earlier than elapsed_time.
        event_time=max(0.0,self.elapsed_time-self.dt)
        self.audio_events.append((event_time, 1, False))
        ball.alive = False

    def _sync(self):
        self.state.balls = self.balls
        self.state.particles = self.particles
        self.state.audio_events = self.audio_events
        self.state.elapsed_time = self.elapsed_time
        self.state.collision_count = self.shatter_count
        self.state.status = 'complete' if self.frame_index >= self.total_frames else 'running'
        return self.state

    def _solve_particle_pairs(self):
        if len(self.particles) < 2:
            return
        cell_size=max(2.0,max(p.radius for p in self.particles)*2.1)
        grid={}
        for index,particle in enumerate(self.particles):
            key=(int(math.floor(particle.pos[0]/cell_size)),int(math.floor(particle.pos[1]/cell_size)))
            grid.setdefault(key,[]).append(index)
        for index,first in enumerate(self.particles):
            cx=int(math.floor(first.pos[0]/cell_size)); cy=int(math.floor(first.pos[1]/cell_size))
            for gx in range(cx-1,cx+2):
                for gy in range(cy-1,cy+2):
                    for other_index in grid.get((gx,gy),()):
                        if other_index<=index: continue
                        second=self.particles[other_index]
                        delta=second.pos-first.pos
                        distance=float(np.linalg.norm(delta))
                        minimum=first.radius+second.radius
                        if distance>=minimum: continue
                        normal=delta/distance if distance>1e-9 else np.array([1.0,0.0])
                        correction=normal*((minimum-distance)*.5)
                        first.pos-=correction; second.pos+=correction
                        relative=float(np.dot(second.vel-first.vel,normal))
                        if relative<0.0:
                            impulse=normal*(-relative*.62)
                            first.vel-=impulse; second.vel+=impulse
                        first.vel*=.998; second.vel*=.998

    def advance_frame(self):
        self.elapsed_time += self.dt
        if self.size_script and self.script_index<len(self.size_script) and self.elapsed_time+1e-9>=self.next_spawn:
            self._spawn_ball(self.W*self.size_script[self.script_index]/200.0)
            self.script_index+=1
            self.next_spawn+=max(.05,float(self.config.segment_seconds))
        elif not self.size_script and not self.config.one_shot and self.elapsed_time + 1e-9 >= self.next_spawn:
            self._spawn_ball()
            self.next_spawn += max(.05, float(self.config.spawn_interval))
        gravity = float(self.config.gravity)
        for ball in self.balls:
            if not ball.alive:
                continue
            ball.vel[1] += gravity * self.dt
            ball.pos += ball.vel * self.dt
            spike_tip_y = self.spikes[0][2][1]
            if ball.pos[1] + ball.radius >= spike_tip_y:
                ball.pos[1] = spike_tip_y - ball.radius
                self._shatter(ball)
        survivors = []
        for particle in self.particles:
            particle.life -= self.dt
            if particle.life <= 0:
                continue
            foam_gravity=self.H*.75
            particle.vel[1] += foam_gravity * self.dt
            particle.vel *= math.exp(-.35 * self.dt)
            particle.pos += particle.vel * self.dt
            if particle.pos[0] - particle.radius < self.box_left:
                particle.pos[0] = self.box_left + particle.radius
                particle.vel[0] = abs(particle.vel[0]) * .52
            elif particle.pos[0] + particle.radius > self.box_right:
                particle.pos[0] = self.box_right - particle.radius
                particle.vel[0] = -abs(particle.vel[0]) * .52
            if particle.pos[1] + particle.radius > self.box_bottom:
                if getattr(self.config,'remove_foam_on_floor',0):
                    chance=max(0.0,min(1.0,float(getattr(self.config,'floor_sound_chance',.5))))
                    self.floor_sound_accumulator+=chance
                    if self.floor_sound_accumulator>=1.0:
                        self.audio_events.append((max(0.0,self.elapsed_time-self.dt),1,True))
                        self.floor_sound_accumulator-=1.0
                    continue
                particle.pos[1] = self.box_bottom - particle.radius
                particle.vel[1] = -abs(particle.vel[1]) * .30
                particle.vel[0] *= .97
                if abs(particle.vel[1]) < 12.0:
                    particle.vel[1] = 0.0
            for a,b in ((self.spikes[0][0],self.spikes[0][2]),(self.spikes[0][2],self.spikes[0][1])):
                ab=b-a
                t=max(0.0,min(1.0,float(np.dot(particle.pos-a,ab)/max(1e-9,np.dot(ab,ab)))))
                closest=a+ab*t
                delta=particle.pos-closest
                distance=float(np.linalg.norm(delta))
                if distance < particle.radius:
                    normal=delta/distance if distance>1e-9 else np.array([0.0,-1.0])
                    particle.pos=closest+normal*particle.radius
                    normal_speed=float(np.dot(particle.vel,normal))
                    if normal_speed < 0.0:
                        particle.vel-=normal*(1.42*normal_speed)
                    particle.vel*=.96
            survivors.append(particle)
        self.particles = survivors
        self._solve_particle_pairs()
        for particle in self.particles:
            particle.pos[0]=max(self.box_left+particle.radius,min(self.box_right-particle.radius,particle.pos[0]))
            particle.pos[1]=min(self.box_bottom-particle.radius,particle.pos[1])
        self.frame_index += 1
        return self._sync()

    def draw_frame(self, width=None, height=None):
        image = np.zeros((self.H, self.W, 3), dtype=np.uint8)
        wall_color=(205,205,215)
        thickness=max(3,int(round(self.W/180)))
        cv2.line(image,(int(self.box_left),int(self.box_top)),(int(self.box_left),int(self.box_bottom)),wall_color,thickness,cv2.LINE_AA)
        cv2.line(image,(int(self.box_right),int(self.box_top)),(int(self.box_right),int(self.box_bottom)),wall_color,thickness,cv2.LINE_AA)
        cv2.line(image,(int(self.box_left),int(self.box_bottom)),(int(self.box_right),int(self.box_bottom)),wall_color,thickness,cv2.LINE_AA)
        cv2.fillConvexPoly(image,np.round(self.spikes[0]).astype(np.int32),(70,70,235),cv2.LINE_AA)
        for particle in self.particles:
            center=tuple(np.round(particle.pos).astype(int)); radius=max(1,int(round(particle.radius)))
            if self.foam_skin is None or not draw_skin_circle(image,self.foam_skin,center[0],center[1],radius):
                cv2.circle(image,center,radius,particle.color,-1,cv2.LINE_AA)
        for ball in self.balls:
            if not ball.alive:
                continue
            center = tuple(np.round(ball.pos).astype(int))
            radius = max(1, int(round(ball.radius)))
            if self.skin is None or not draw_skin_circle(image, self.skin, center[0], center[1], radius):
                cv2.circle(image, center, radius, ball.color, -1, cv2.LINE_AA)
                cv2.circle(image, center, radius, (245, 245, 245), max(2, radius // 12), cv2.LINE_AA)
        if width is not None or height is not None:
            image = cv2.resize(image, (int(width or self.W), int(height or self.H)), interpolation=cv2.INTER_AREA)
        return image
