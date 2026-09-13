"""Compatibility entry point for the shared Merge engine."""
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
