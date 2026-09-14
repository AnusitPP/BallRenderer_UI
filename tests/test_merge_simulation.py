import json
from pathlib import Path
import pytest
import numpy as np
from engines.merge_engine import Ball, MergeSimulation, cli, align_events_to_video_frames, trim_audio_onset
from engines.merge.model import load_skins
BASE=json.loads(Path(__file__).with_name('merge_baselines.json').read_text())
@pytest.mark.parametrize('name,level',[('seed11',None),('merge',3)])
def test_legacy_frames(name,level):
 s=MergeSimulation(cli(['--seed','11','--seconds','10' if level is None else '0.1']))
 if level:
  s.balls=[Ball(260,590,12,5,level,100),Ball(280,590,-3,7,level,101)]
  s.spawn_t=.8; s.next_id=2
  s.rng.uniform(-s.pipe_w*.15,s.pipe_w*.15); s.rng.uniform(-18,18)
 for expected in BASE[name]:
  s.advance_frame()
  actual={'balls':[{k:v for k,v in vars(b).items() if k!='percent'} for b in s.balls], 'effects':s.effects,'elapsed_time':s.elapsed_time,'audio_events':s.audio_events,'victory':s.victory}
  assert json.loads(json.dumps(actual))==expected

def test_proxy_and_percent_do_not_change_physics():
 a=MergeSimulation(cli(['--level-size-percent','25']))
 b=MergeSimulation(cli(['--level-size-percent','-10']))
 assert Ball(0,0,0,0,2,1).r==30
 a.advance_frame(); before=[vars(x).copy() for x in a.balls]
 assert a.draw_frame(270,480).shape==(480,270,3)
 assert [vars(x) for x in a.balls]==before
 assert a.balls[0].percent==25
 assert b.config.level_size_percent==-10


def test_render_audio_events_align_to_visible_frame_without_changing_simulation():
 events=[(.0125,2,False),(.029,3,False)]
 assert align_events_to_video_frames(events,60)==[(0.0,2,False),(1/60,3,False)]
 assert events==[(.0125,2,False),(.029,3,False)]


def test_merge_custom_sound_leading_silence_is_trimmed():
 clip=np.r_[np.zeros(500,dtype=np.float32),np.ones(20,dtype=np.float32)]
 assert len(trim_audio_onset(clip,preroll_samples=0))==20


def test_two_level_8_balls_become_persistent_level_9_without_victory_text():
 s=MergeSimulation(cli(['--seconds','.1']))
 s.balls=[Ball(260,590,12,5,8,100),Ball(280,590,-3,7,8,101)]; s.spawn_t=.8; s.next_id=102
 s.advance_frame()
 assert s.victory is True
 assert len(s.balls)==1 and s.balls[0].level==9
 source=Path(__file__).parents[1].joinpath('engines','merge','simulation.py').read_text(encoding='utf-8')
 assert 'VICTORY  LV8 + LV8' not in source


def test_level_9_custom_image_is_loaded(tmp_path):
 import cv2
 image=np.full((8,8,3),127,dtype=np.uint8)
 cv2.imwrite(str(tmp_path/'9.png'),image)
 assert 9 in load_skins(tmp_path)


@pytest.mark.parametrize('pipe_count',[1,2,3])
def test_merge_supports_one_to_three_spawn_pipes(pipe_count):
 s=MergeSimulation(cli(['--pipe-count',str(pipe_count),'--spawn-interval','.01']))
 assert len(s.pipe_centers)==pipe_count
 for _ in range(12): s.step(s.dt)
 assert s.spawn_pipe_history
 assert s.spawn_pipe_history==[s.pipe_centers[i%pipe_count] for i in range(len(s.spawn_pipe_history))]
