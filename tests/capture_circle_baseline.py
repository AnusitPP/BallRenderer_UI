from pathlib import Path
import json, hashlib, sys, types
import numpy as np
root=Path('.')
src=Path('tests/circle_baseline_source.txt').read_text(encoding='utf-8')
Path('tests/circle_baseline_source.txt').write_text(src,encoding='utf-8')
# Preserve the actual legacy loop, removing output-only sections.
src=src.replace('    final_out = Path(args.out).expanduser().resolve()','    final_out = Path(args.out).expanduser().resolve()')
a=src.index('    final_out = Path(args.out)'); b=src.index('    melody = {',a)
src=src[:a]+'    source_samples = []\n'+src[b:]
a=src.index('    writer = cv2.VideoWriter('); b=src.index('    for frame in range(total_frames):',a)
src=src[:a]+src[b:]
a=src.index('        img = np.zeros'); b=src.index('        writer.write(img)',a)
drawing=src[a:b]
src=src[:a]+'        if frame in (0, 59, 299, 599):\n'+''.join('    '+line+'\n' for line in drawing.splitlines())+'            raster_hash = hashlib.sha256(img.tobytes()).hexdigest()\n        else:\n            raster_hash = None\n        capture(locals())\n'+src[b+len('        writer.write(img)'):]
a=src.index('        render_ratio ='); src=src[:a]+'\n    return\n'
src=src.replace('    sim_time = 0.0', '    sim_time = 0.0\n    collision_count = 0').replace('                if hit_spike and ball.spike_hit_cooldown <= 0.0:', '                if hit_spike and ball.spike_hit_cooldown <= 0.0:\n                    collision_count += 1').replace('                if wall_hit and ball.wall_hit_cooldown <= 0.0:', '                if wall_hit and ball.wall_hit_cooldown <= 0.0:\n                    collision_count += 1')
m=types.ModuleType('baseline'); sys.modules[m.__name__]=m; exec(compile(src,'legacy-main.py','exec'),m.__dict__); m.hashlib=hashlib
def snap(d):
    return {'balls':[{k:(v.tolist() if isinstance(v,np.ndarray) else v) for k,v in vars(b).items()} for b in d['balls']], 'particles':[{k:(v.tolist() if isinstance(v,np.ndarray) else v) for k,v in vars(b).items()} for b in d['particles']], 'events':d['sound_events'], 'time':d['sim_time'], 'rotation':d['rotation_angle'], 'collision_count':d['collision_count'], 'raster_hash':d['raster_hash']}
Path('tests/circle_snapshot.py').write_text('import numpy as np\n'+__import__('inspect').getsource(snap),encoding='utf-8') if False else None
cases={'normal':['--spike-count','0'], 'spikes':['--spike-count','12','--spike-depth','80','--ball-lives','30'], 'gap':['--spike-count','0','--gap-enabled','1','--gap-position','90','--gap-size','100'], 'trail_pattern':['--ball-count','4','--motion-trail','1','--pattern-file','tests/circle_pattern.json']}
Path('tests/circle_pattern.json').write_text(json.dumps({'name':'baseline','defaults':{'gravity':900},'events':[{'time':2,'gravity':500,'spike_count':8},{'time':5,'gravity':1200,'gap_enabled':True,'gap_size':60}]}))
result={}
for name,extra in cases.items():
    frames=[]; m.capture=lambda d:frames.append(json.loads(json.dumps(snap(d))))
    argv=['--fps','60','--seconds','10','--seed','11','--gravity','900','--initial-speed','600']+extra
    m.main(argv)
    result[name]={'argv':argv,'frames':frames}
Path('tests/circle_baselines.json').write_text(json.dumps(result,separators=(',',':')),encoding='utf-8')

