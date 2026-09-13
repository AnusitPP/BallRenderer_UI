from pathlib import Path
import ast,textwrap
s=Path('tests/circle_baseline_source.txt').read_text()
for p in ['core','engines','engines/circle']:
 Path(p).mkdir(exist_ok=True); Path(p,'__init__.py').touch()
models=s[s.index('@dataclass'):s.index('def length')]
Path('core/models.py').write_text('from dataclasses import dataclass\nimport numpy as np\n\n'+models)
physics=s[:s.index('def midi_to_hz')]
physics=physics[:physics.index('@dataclass')]+'from core.models import Ball, Particle\n\n'+physics[physics.index('def length'):]
Path('engines/circle/physics.py').write_text(physics)
Path('core/config.py').write_text('import argparse\nfrom engines.circle.physics import DEFAULT_BALL_COLORS\n\n'+s[s.index('def build_arg_parser'):s.index('def main(argv')])
Path('engines/circle/drawing.py').write_text('import math\nimport cv2\nimport numpy as np\nfrom engines.circle.physics import *\n\n'+s[s.index('def draw_rainbow_ring'):s.index('def build_arg_parser')])
body=s[s.index('    args.ball_count ='):s.index('    writer = cv2.VideoWriter(')]
a=body.index('    final_out ='); b=body.index('    melody =',a); body=body[:a]+body[b:]
body=body.replace('    print(f"Pattern: {pattern_name}", flush=True)\n','')
shared=set()
for node in ast.walk(ast.parse(textwrap.dedent(body))):
 if isinstance(node,ast.Name) and isinstance(node.ctx,ast.Store): shared.add(node.id)
shared-= {'i','ball','n'}
shared|={'args','source_samples','spikes'}
class Rewrite(ast.NodeTransformer):
 def visit_Name(self,node):
  if node.id in shared:return ast.copy_location(ast.Attribute(value=ast.Name(id='self',ctx=ast.Load()),attr=node.id,ctx=node.ctx),node)
  return node
def convert(code):return ast.unparse(ast.fix_missing_locations(Rewrite().visit(ast.parse(textwrap.dedent(code)))))
step=s[s.index('            pattern_index = apply_pattern_events_up_to(',s.index('    for frame in range(total_frames):')):s.index('        if args.motion_trail:',s.index('    for frame in range(total_frames):'))]
step=step.replace('                if hit_spike and ball.spike_hit_cooldown <= 0.0:\n','                if hit_spike and ball.spike_hit_cooldown <= 0.0:\n                    self.collision_count += 1\n').replace('                if wall_hit and ball.wall_hit_cooldown <= 0.0:\n','                if wall_hit and ball.wall_hit_cooldown <= 0.0:\n                    self.collision_count += 1\n')
trail=s[s.index('        if args.motion_trail:',s.index('    for frame in range(total_frames):')):s.index('        img = np.zeros')]
draw=s[s.index('        img = np.zeros'):s.index('        writer.write(img)')]
state='''from dataclasses import dataclass, field

@dataclass
class SimulationState:
    balls: list = field(default_factory=list)
    particles: list = field(default_factory=list)
    spikes: list = field(default_factory=list)
    elapsed_time: float = 0.0
    rotation: float = 0.0
    audio_events: list = field(default_factory=list)
    collision_count: int = 0
    status: str = "ready"
'''
Path('core/simulation_state.py').write_text(state)
code='''"""Deterministic legacy Circle simulation shared by previews and final rendering."""
import copy
from core.simulation_state import SimulationState
from engines.circle.physics import *
from engines.circle.drawing import *

class CircleSimulation:
    def __init__(self, config, source_samples=None):
        self.args = copy.deepcopy(config)
        self.config = self.args
        self.source_samples = source_samples if source_samples is not None else []
        self.frame_index = 0
        self.collision_count = 0
        self.state = SimulationState()
'''+textwrap.indent(convert(body),'        ')+'''
        self.spikes = []
        self._sync_state()

    def _sync_state(self):
        self.state.balls = self.balls
        self.state.particles = self.particles
        self.state.spikes = self.spikes
        self.state.elapsed_time = self.sim_time
        self.state.rotation = self.rotation_angle
        self.state.audio_events = self.sound_events
        self.state.collision_count = self.collision_count
        self.state.status = "complete" if self.frame_index >= self.total_frames else "running"
        return self.state

    def step(self, dt=None):
        configured_dt = self.dt
        if dt is not None:
            self.dt = float(dt)
'''+textwrap.indent(convert(step),'        ')+'''
        self.dt = configured_dt
        return self._sync_state()

    def advance_frame(self):
        for _ in range(self.substeps):
            self.step()
'''+textwrap.indent(convert(trail),'        ')+'''
        self.frame_index += 1
        return self._sync_state()

    def draw_frame(self, width=None, height=None):
'''+textwrap.indent(convert(draw),'        ')+'''
        if width is not None or height is not None:
            img = cv2.resize(img, (int(width or self.W), int(height or self.H)), interpolation=cv2.INTER_AREA)
        return img
'''
Path('engines/circle/simulation.py').write_text(code)
# CLI retains all output/audio operations, delegates frame simulation and drawing.
main=s[s.index('def main(argv'):]
a=main.index('    args.ball_count =');b=main.index('    final_out =',a)
main=main[:a]+main[b:]
a=main.index('    melody =');b=main.index('    writer =',a)
main=main[:a]+'''    engine = CircleSimulation(args, source_samples=source_samples)
    args = engine.config
    W, H, FPS = engine.W, engine.H, engine.FPS
    total_frames = engine.total_frames
    melody = engine.melody
    sound_events = engine.state.audio_events

'''+main[b:]
a=main.index('        for _ in range(substeps):');b=main.index('        writer.write(img)',a)
main=main[:a]+'''        engine.advance_frame()
        img = engine.draw_frame()

'''+main[b:]
imports=s[:s.index('DEFAULT_MELODY_NOTES')]
main=imports+'from engines.circle.physics import *\nfrom engines.circle.drawing import *\nfrom engines.circle.drawing import _draw_ball_number\nfrom core.config import build_arg_parser\nfrom engines.circle.simulation import CircleSimulation\n\n'+s[s.index('def midi_to_hz'):s.index('def draw_rainbow_ring')]+main
Path('main.py').write_text(main)
