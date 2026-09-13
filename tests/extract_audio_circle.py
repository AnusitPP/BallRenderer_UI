from pathlib import Path
import ast
s=Path('main.py').read_text(); p=Path('engines/circle/physics.py').read_text()
Path('audio').mkdir(exist_ok=True); Path('audio/__init__.py').touch()
groups={'melody':['extract_midi_melody','load_melody_file'], 'synthesizer':['midi_to_hz','synth_note','make_audio'], 'onset':['read_wav_mono','detect_audio_onsets','extract_bounce_samples','decode_audio_to_wav','prepare_bounce_samples'], 'mixer':['mix_bounce_sample_events','write_float_audio_wav','make_bounce_sample_audio']}
imports='import json\nimport math\nimport wave\nimport subprocess\nfrom pathlib import Path\nimport numpy as np\nimport mido\n'
for module,names in groups.items():
 source=p if module=='melody' else s
 lines=source.splitlines(True); nodes=[n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name in names]
 extra='from audio.onset import *\n' if module=='mixer' else ''
 if module=='onset':extra='from render.ffmpeg import hidden_process_kwargs\n'
 Path('audio',module+'.py').write_text(imports+extra+'\n'+''.join(''.join(lines[n.lineno-1:n.end_lineno])+'\n\n' for n in nodes))
 for n in reversed(nodes): del lines[n.lineno-1:n.end_lineno]
 source=''.join(lines)
 if module=='melody':p=source+'\nfrom audio.melody import extract_midi_melody, load_melody_file\n'
 else:s=source+'\n'
# Remove duplicated service functions; use imports including private legacy symbol.
names=['hidden_process_kwargs','_append_video_encoder_options','build_original_audio_ffmpeg_cmd','find_ffmpeg','ffmpeg_has_nvenc_from_text','ffmpeg_has_nvenc','build_ffmpeg_cmd','report_progress','run_ffmpeg_with_progress']
lines=s.splitlines(True)
for n in reversed(ast.parse(s).body):
 if isinstance(n,ast.FunctionDef) and n.name in names:del lines[n.lineno-1:n.end_lineno]
s=''.join(lines)
s='from render.ffmpeg import '+', '.join(names)+'\nfrom audio.synthesizer import *\nfrom audio.onset import *\nfrom audio.mixer import *\n'+s
Path('main.py').write_text(s)
Path('engines/circle/physics.py').write_text(p)
