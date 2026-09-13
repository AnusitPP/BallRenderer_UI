from pathlib import Path
import textwrap
root=Path(__file__).resolve().parents[1]
s=(root/'tests/merge_baseline_source.txt').read_text(encoding='utf-8')
(root/'engines/merge').mkdir(exist_ok=True)
(root/'audio').mkdir(exist_ok=True)
audio=s[s.index('def _write_event_wav'):s.index('@dataclass')]
a=audio.index('def find_ffmpeg():'); b=audio.index('def audio_mux_plan')
audio=audio[:a]+audio[b:]
audio=audio[:audio.index('def mux_merge_audio')]
audio=audio.replace('stderr=subprocess.PIPE)','stderr=subprocess.PIPE, **hidden_process_kwargs())')
(root/'audio/merge.py').write_text('"""Merge sound synthesis and constant-input audio timeline."""\nimport wave, subprocess\nfrom pathlib import Path\nimport numpy as np\nfrom render.ffmpeg import hidden_process_kwargs\n\n'+audio,encoding='utf-8')
helpers=s[:s.index('def _write_event_wav')]+s[s.index('@dataclass'):s.index('def render(args):')]
helpers=helpers.replace('LEVEL_SIZE_PERCENT = 0.0\n','').replace('pending:bool=False','pending:bool=False\n    percent:float=0.0').replace('level_radius(self.level, LEVEL_SIZE_PERCENT)','level_radius(self.level, self.percent)')
(root/'engines/merge/model.py').write_text(helpers,encoding='utf-8')
init=s[s.index('    W,H=args.width,args.height'):s.index('    writer=cv2.VideoWriter')]
init=init.replace('sound_events','audio_events')
fields=['W','H','cx','cy','R','pipe_w','pipe_top','opening_y','skins','balls','effects','next_id','t','spawn_t','victory','victory_t','dt','rng','sound_events']
alias='\n'.join('        '+name+'=self.'+name for name in fields)
loop=s[s.index('            if not victory and t>=spawn_t:'):s.index('        img=np.zeros')]
loop=textwrap.indent(textwrap.dedent(loop),'        ')
loop=loop.replace('1,next_id))','1,next_id,percent=args.level_size_percent))').replace('lv,next_id))','lv,next_id,percent=args.level_size_percent))')
loop=loop.replace('if dist < min_d:\n','if dist < min_d:\n                        self.collision_count += 1\n')
# Correct the inserted indentation to match the dedented substep.
loop=loop.replace('                        self.collision_count += 1','                    self.collision_count += 1')
persist='\n'.join('        self.'+name+'='+name for name in fields if name!='dt')
draw=s[s.index('        img=np.zeros'):s.index('        writer.write(img)')]
cls='''"""Legacy Merge integration shared by live preview and final rendering."""
from .model import *

class MergeSimulation:
    def __init__(self, config):
        self.config=config
        args=config
'''+init+'''        rng=random.Random(args.seed)
        sound_events=[]
'''+persist+'''
        self.dt=dt
        self.frame_index=0
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
'''+alias.replace('        dt=self.dt\n','')+'\n'+loop+persist+'''
        return self.state

    def draw_frame(self, width=None, height=None):
        args=self.config
'''+alias+'\n'+draw+'''
        if width is not None or height is not None:
            width=int(width or round(W*height/H))
            height=int(height or round(H*width/W))
            if (width,height)!=(W,H):
                img=cv2.resize(img,(width,height),interpolation=cv2.INTER_AREA)
        return img
'''
# init original four-space body needs nested constructor indentation
start=cls.index('    W,H='); end=cls.index('        rng=random.Random')
cls=cls[:start]+textwrap.indent(cls[start:end],'    ')+cls[end:]
(root/'engines/merge/simulation.py').write_text(cls,encoding='utf-8')
(root/'engines/merge/__init__.py').write_text('from .model import *\nfrom .simulation import MergeSimulation\n',encoding='utf-8')
facade='''"""Compatibility entry point for the shared Merge engine."""
import argparse
import tempfile
from pathlib import Path
import cv2
from engines.merge import *
from audio.merge import _write_event_wav, _decode_audio_mono, _mix_audio_timeline, audio_mux_plan
from render.ffmpeg import find_ffmpeg, encode_video, report_progress


def mux_merge_audio(video_path, events, args):
    """Compatibility helper; failures propagate and retain intermediate evidence."""
    ffmpeg=find_ffmpeg()
    if not ffmpeg: raise RuntimeError('FFmpeg not found')
    video=Path(video_path)
    silent=video.with_name(video.stem+'_silent.mp4')
    timeline=video.with_name(video.stem+'_audio_timeline.wav')
    video.replace(silent)
    audio=None
    if args.merge_sound and events:
        merge_clip=_decode_audio_mono(args.merge_sound_file,ffmpeg)
        victory_clip=_decode_audio_mono(args.victory_sound_file,ffmpeg)
        _mix_audio_timeline(timeline,events,args.seconds,args.merge_volume,merge_clip,victory_clip)
        audio=timeline
    encode_video(ffmpeg,silent,audio,video,args.seconds)
    silent.unlink(missing_ok=True)
    timeline.unlink(missing_ok=True)


def render(args):
    ffmpeg=find_ffmpeg()
    if not ffmpeg: raise RuntimeError('FFmpeg not found; configure FFMPEG_EXE or install FFmpeg')
    output=Path(args.out)
    output.parent.mkdir(parents=True,exist_ok=True)
    temp=Path(tempfile.mkdtemp(prefix='merge_',dir=output.parent))
    silent=temp/'silent.mp4'
    timeline=temp/'audio.wav'
    sim=MergeSimulation(args)
    writer=cv2.VideoWriter(str(silent),cv2.VideoWriter_fourcc(*'mp4v'),args.fps,(args.width,args.height))
    if not writer.isOpened(): raise RuntimeError('Could not open Merge video writer')
    frames=int(args.seconds*args.fps)
    success=False
    cancelled=False
    try:
        try:
            for fi in range(frames):
                sim.advance_frame()
                writer.write(sim.draw_frame())
                if fi % max(1,frames//100)==0:
                    report_progress(90*(fi+1)/max(1,frames),'Merge Ball LV1-8')
        finally:
            writer.release()
        audio=None
        if args.merge_sound and sim.audio_events:
            merge_clip=_decode_audio_mono(args.merge_sound_file,ffmpeg)
            victory_clip=_decode_audio_mono(args.victory_sound_file,ffmpeg)
            _mix_audio_timeline(timeline,sim.audio_events,args.seconds,args.merge_volume,merge_clip,victory_clip)
            audio=timeline
        encode_video(ffmpeg,silent,audio,output,args.seconds)
        success=True
        report_progress(100,'Complete')
    except KeyboardInterrupt:
        cancelled=True
        raise
    finally:
        if success or cancelled:
            silent.unlink(missing_ok=True)
            timeline.unlink(missing_ok=True)
            temp.rmdir()

'''+s[s.index('def cli(argv=None):'):]
(root/'engines/merge_engine.py').write_text(facade,encoding='utf-8')
