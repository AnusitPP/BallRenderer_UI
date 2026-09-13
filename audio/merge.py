"""Merge sound synthesis and constant-input audio timeline."""
import wave, subprocess
from pathlib import Path
import numpy as np
from render.ffmpeg import hidden_process_kwargs

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


def audio_mux_plan(events, merge_sound_file="", victory_sound_file=""):
    # All events are rendered into one temporary timeline before the final mux.
    return {"ffmpeg_input_count": 2, "event_count": len(events)}

def _decode_audio_mono(path, ffmpeg, sample_rate=44100):
    """Decode any FFmpeg-supported audio file to mono float32 PCM."""
    if not path or not Path(path).is_file():
        return None
    cmd=[ffmpeg,"-v","error","-i",str(path),"-f","f32le","-ac","1","-ar",str(sample_rate),"pipe:1"]
    result=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE, **hidden_process_kwargs())
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

