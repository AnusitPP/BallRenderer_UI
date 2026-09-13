from pathlib import Path
import sys,json,copy,contextlib,io
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from engines import merge_engine as m
source=(ROOT/'engines/merge_engine.py').read_text(encoding='utf-8')
(ROOT/'tests/merge_baseline_source.txt').write_text(source,encoding='utf-8')
class Writer:
 def write(self,img): pass
 def release(self): pass
m.cv2.VideoWriter=lambda *a:Writer()
m.mux_merge_audio=lambda *a:None
out={}
for name,lv in [('seed11',None),('merge',3),('victory',8)]:
 args=m.cli(['--seed','11','--seconds','10' if lv is None else '0.1'])
 rows=[]; injected=False
 def trace(frame,event,arg):
  global injected
  if frame.f_code.co_name=='render' and event=='line':
   line=source.splitlines()[frame.f_lineno-1].strip()
   loc=frame.f_locals
   if lv is not None and line=='# integrate': pass
   if lv is not None and not injected and line=='for b in balls:':
    loc['balls'][:]=[m.Ball(260,590,12,5,lv,100),m.Ball(280,590,-3,7,lv,101)]
    injected=True
   if line=='img=np.zeros((H,W,3),np.uint8)':
    rows.append(copy.deepcopy({'balls':[vars(b).copy() for b in loc['balls']], 'effects':loc['effects'],'elapsed_time':loc['t'],'audio_events':loc['sound_events'],'victory':loc['victory']}))
  return trace
 with contextlib.redirect_stdout(io.StringIO()):
  sys.settrace(trace)
  try:m.render(args)
  finally:sys.settrace(None)
 out[name]=rows
(ROOT/'tests/merge_baselines.json').write_text(json.dumps(out),encoding='utf-8')
