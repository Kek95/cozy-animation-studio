#!/usr/bin/env python3
"""Inspect media, extract timestamped review frames, and compose accepted shots."""
import argparse
import json
import math
import subprocess
from pathlib import Path
from studio import load, save, validate

def run(args):
    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-2500:])
    return p.stdout

def probe(path):
    return json.loads(run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)]))

def inspect(path, decode=False):
    data = probe(path)
    result = {'file': str(Path(path).resolve()), 'duration': float(data['format'].get('duration', 0)),
              'streams': [{k: s.get(k) for k in ['codec_type', 'codec_name', 'width', 'height', 'avg_frame_rate', 'sample_rate', 'nb_frames']} for s in data['streams']]}
    if decode:
        run(['ffmpeg', '-hide_banner', '-v', 'error', '-i', str(path), '-f', 'null', '-'])
        result['full_decode'] = 'passed'
    return result

def frames(args):
    out = Path(args.out).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError('Review folder must be empty or new.')
    out.mkdir(parents=True, exist_ok=True)
    duration = float(probe(args.file)['format']['duration'])
    if args.count < 2 or args.count > 120:
        raise ValueError('Use 2–120 review frames.')
    result = []
    for i in range(args.count):
        t = (i + 0.5) * duration / args.count
        dest = out / f'{i+1:03d}_{t:06.2f}s.jpg'
        run(['ffmpeg', '-hide_banner', '-v', 'error', '-ss', f'{t:.6f}', '-i', args.file,
             '-frames:v', '1', '-vf', 'scale=640:-2', '-q:v', '2', str(dest)])
        if not dest.is_file():
            raise ValueError(f'Could not extract frame at {t:g}s.')
        result.append({'time': t, 'file': str(dest)})
    save(out / 'frames.json', result)
    return {'frames': result, 'note': 'View these images; extraction alone does not assess style or motion.'}

def compose(args):
    root, doc = load(args.project)
    errors = validate(doc)
    if errors:
        raise ValueError('; '.join(errors))
    audio = doc.get('audio', {})
    # CLI paths are relative to the caller; saved paths are relative to the project.
    def audio_file(cli_value, field):
        if cli_value:
            return Path(cli_value).resolve()
        value = audio.get(field)
        return (root / value).resolve() if value else None
    voice = audio_file(args.voice, 'voiceover')
    music = audio_file(args.music, 'music')
    if audio.get('music_required', False) and music is None:
        raise ValueError('Background music is required. Supply --music or audio.music before final composition. Set audio.music_required=false only for an intentionally music-free project.')
    for kind, file in [('voice', voice), ('music', music)]:
        if file is not None and not file.is_file():
            raise ValueError(f'{kind} file does not exist: {file}')
    mute_native = args.mute_native or not audio.get('native_audio', True)
    if args.width <= 0 or args.height <= 0 or args.width % 2 or args.height % 2 or args.fps <= 0:
        raise ValueError('Dimensions must be positive and even; fps must be positive.')
    for value in [args.native_db, args.voice_db, args.music_db]:
        if not math.isfinite(value):
            raise ValueError('Audio gain must be finite.')
    dest = Path(args.out).resolve() if args.out else root / 'final' / 'film.mp4'
    if dest.exists():
        raise ValueError('Final output exists. Use a new filename.')
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ['ffmpeg', '-hide_banner', '-v', 'error', '-nostdin']
    filters, pairs, source_info = [], [], []
    for i, shot in enumerate(doc['shots']):
        selected = shot.get('selected_candidate')
        candidate = next((c for c in shot.get('candidates', []) if c.get('id') == selected), None)
        if not candidate or (candidate.get('review') or {}).get('verdict') != 'accept':
            raise ValueError(f'{shot["id"]}: no visually accepted candidate.')
        filename = shot.get('selected_file')
        if not filename or filename not in candidate.get('files', []):
            raise ValueError(f'{shot["id"]}: selected file does not belong to candidate.')
        file = (root / filename).resolve()
        meta = probe(file)
        streams = meta['streams']
        video = next((s for s in streams if s['codec_type'] == 'video'), None)
        if not video:
            raise ValueError(f'{shot["id"]}: selected asset is not a video.')
        offset, length = float(shot.get('trim_in', 0)), float(shot['duration'])
        source_duration = float(video.get('duration', meta['format']['duration']))
        if not math.isfinite(offset) or offset < 0 or source_duration + 0.02 < offset + length:
            raise ValueError(f'{shot["id"]}: insufficient source duration; choose another cut or remake, do not silently freeze/pad video.')
        cmd += ['-i', str(file)]
        scale = f'scale={args.width}:{args.height}:force_original_aspect_ratio=increase,crop={args.width}:{args.height}' if args.fit == 'crop' else f'scale={args.width}:{args.height}:force_original_aspect_ratio=decrease,pad={args.width}:{args.height}:(ow-iw)/2:(oh-ih)/2'
        filters.append(f'[{i}:v]trim=start={offset}:duration={length},setpts=PTS-STARTPTS,{scale},setsar=1,fps={args.fps},format=yuv420p[v{i}]')
        if any(s['codec_type'] == 'audio' for s in streams) and not mute_native:
            filters.append(f'[{i}:a]atrim=start={offset}:duration={length},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,apad,atrim=duration={length},volume={args.native_db}dB,afade=t=in:d=0.06,afade=t=out:st={max(0,length-0.06)}:d=0.06[a{i}]')
        else:
            filters.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={length},asetpts=PTS-STARTPTS[a{i}]')
        pairs.append(f'[v{i}][a{i}]')
        source_info.append({'shot': shot['id'], 'file': str(file), 'trim_in': offset, 'duration': length})
    filters.append(''.join(pairs) + f'concat=n={len(pairs)}:v=1:a=1[video][native]')
    tracks = ['[native]']
    input_index = len(pairs)
    total = float(doc['duration'])
    audio_sources = []
    for kind, name, gain in [('voice', voice, args.voice_db), ('music', music, args.music_db)]:
        if not name:
            continue
        file = Path(name).resolve()
        meta = probe(file)
        if not any(s['codec_type'] == 'audio' for s in meta['streams']):
            raise ValueError(f'{kind} file has no audio stream.')
        duration = float(meta['format']['duration'])
        if kind == 'voice' and duration > total + 0.05:
            raise ValueError('Voiceover is longer than film. Edit the script/timing explicitly.')
        if kind == 'music' and duration < total and not args.loop_music:
            raise ValueError('Music is short; pass --loop-music only if looping is intended.')
        if kind == 'music' and args.loop_music:
            cmd += ['-stream_loop', '-1']
        cmd += ['-i', str(file)]
        fade = f',afade=t=in:d=0.4,afade=t=out:st={max(0,total-0.8)}:d=0.8' if kind == 'music' else ''
        filters.append(f'[{input_index}:a]aresample=48000,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS,apad,atrim=duration={total},volume={gain}dB{fade}[{kind}]')
        tracks.append(f'[{kind}]'); input_index += 1
        audio_sources.append({'kind': kind, 'file': str(file), 'gain_db': gain,
                              'looped': kind == 'music' and args.loop_music})
    if args.duck_music:
        if not voice or not music:
            raise ValueError('--duck-music requires both voice and music.')
        filters += ['[voice]asplit=2[voice_mix][voice_control]', '[music][voice_control]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=300[music_ducked]']
        tracks = ['[native]', '[voice_mix]', '[music_ducked]']
    filters.append(''.join(tracks) + f'amix=inputs={len(tracks)}:duration=longest:normalize=0,alimiter=limit=0.89:level=0:latency=1,atrim=duration={total}[audio]')
    cmd += ['-filter_complex', ';'.join(filters), '-map', '[video]', '-map', '[audio]', '-map_metadata', '-1',
            '-c:v', 'libx264', '-crf', '18', '-preset', 'medium', '-c:a', 'aac', '-b:a', '192k',
            '-movflags', '+faststart', '-t', str(total), str(dest)]
    run(cmd)
    result = inspect(dest, decode=True)
    if abs(result['duration'] - total) > max(0.05, 1 / args.fps):
        raise ValueError('Unexpected final duration; inspect the output before delivery.')
    result['sources'] = source_info
    result['audio_mix'] = {'music_required': audio.get('music_required', False),
                           'native_muted': mute_native, 'sources': audio_sources,
                           'music_source': audio.get('music_source') if not args.music else None,
                           'review': 'pending_listening; an audio stream does not prove music quality or audibility'}
    result['visual_review'] = 'Selected candidates were explicitly accepted; final playback still required.'
    save(dest.with_suffix('.report.json'), result)
    return result

def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('inspect'); a.add_argument('file'); a.add_argument('--decode', action='store_true')
    a = sub.add_parser('frames'); a.add_argument('file'); a.add_argument('--out', required=True); a.add_argument('--count', type=int, default=12)
    a = sub.add_parser('compose'); a.add_argument('project'); a.add_argument('--out'); a.add_argument('--width', type=int, default=1280); a.add_argument('--height', type=int, default=720); a.add_argument('--fps', type=int, default=24); a.add_argument('--fit', choices=['crop','pad'], default='crop'); a.add_argument('--mute-native', action='store_true'); a.add_argument('--native-db', type=float, default=0); a.add_argument('--voice'); a.add_argument('--voice-db', type=float, default=0); a.add_argument('--music'); a.add_argument('--music-db', type=float, default=-14); a.add_argument('--loop-music', action='store_true'); a.add_argument('--duck-music', action='store_true')
    args = p.parse_args()
    result = inspect(args.file, args.decode) if args.cmd == 'inspect' else frames(args) if args.cmd == 'frames' else compose(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
