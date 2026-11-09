#!/usr/bin/env python3
"""Inspect media, extract timestamped review frames, and compose accepted shots."""
import argparse
import json
import math
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path
from studio import load, save, validate
from production import sha256

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
        run(['ffmpeg', '-hide_banner', '-v', 'error', '-xerror', '-i', str(path), '-f', 'null', '-'])
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


def loudness(file):
    p = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(file), '-vn', '-af',
                        'loudnorm=I=-18:TP=-2:LRA=11:print_format=json', '-f', 'null', '-'],
                       capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-2000:])
    return json.JSONDecoder().raw_decode(p.stderr[p.stderr.rfind('{'):])[0]


def normalized_gain(file, target, peak_cap, adjustment=0):
    values = loudness(file)
    integrated, peak = float(values['input_i']), float(values['input_tp'])
    if not math.isfinite(integrated) or not math.isfinite(peak):
        return -120.0  # A silent source cannot be made audible by infinite gain.
    return max(-120, min(20, target - integrated + adjustment, peak_cap - peak))


def master_filter(values, target=-18, peak=-2):
    if not math.isfinite(float(values['input_i'])):
        return 'anull'
    return (f'loudnorm=I={target}:TP={peak}:LRA=11:measured_I={values["input_i"]}:'
            f'measured_TP={values["input_tp"]}:measured_LRA={values["input_lra"]}:'
            f'measured_thresh={values["input_thresh"]}:offset={values["target_offset"]}:'
            'linear=true:print_format=json')

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
    ambience = audio_file(getattr(args, 'ambience', None), 'ambience')
    if audio.get('music_required', False) and music is None:
        raise ValueError('Background music is required. Supply --music or audio.music before final composition. Set audio.music_required=false only for an intentionally music-free project.')
    if audio.get('ambience_required', False) and ambience is None:
        raise ValueError('A continuous ambience file is required by this project.')
    for kind, file in [('voice', voice), ('music', music), ('ambience', ambience)]:
        if file is not None and not file.is_file():
            raise ValueError(f'{kind} file does not exist: {file}')
    mute_native = args.mute_native or not audio.get('native_audio', True)
    if args.width <= 0 or args.height <= 0 or args.width % 2 or args.height % 2 or args.fps <= 0:
        raise ValueError('Dimensions must be positive and even; fps must be positive.')
    ambience_db = getattr(args, 'ambience_db', 0)
    normalize = getattr(args, 'normalize_audio', False)
    for value in [args.native_db, args.voice_db, args.music_db, ambience_db]:
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
        if abs(length * args.fps - round(length * args.fps)) > 1e-5:
            raise ValueError(f'{shot["id"]}: edit duration must fit whole output frames; revise the timeline explicitly.')
        requested_offset = offset
        offset = round(offset * args.fps) / args.fps
        source_duration = float(video.get('duration', meta['format']['duration']))
        if not math.isfinite(offset) or offset < 0 or source_duration + 0.02 < offset + length:
            raise ValueError(f'{shot["id"]}: insufficient source duration; choose another cut or remake, do not silently freeze/pad video.')
        cmd += ['-i', str(file)]
        scale = f'scale={args.width}:{args.height}:force_original_aspect_ratio=increase,crop={args.width}:{args.height}' if args.fit == 'crop' else f'scale={args.width}:{args.height}:force_original_aspect_ratio=decrease,pad={args.width}:{args.height}:(ow-iw)/2:(oh-ih)/2'
        crop = shot.get('edit_crop')
        if crop is not None:
            if not isinstance(crop, list) or len(crop) != 4 or any(not isinstance(v, int) or isinstance(v, bool) for v in crop):
                raise ValueError(f'{shot["id"]}: edit_crop must be integer[x,y,width,height].')
            x, y, w, h = crop
            if min(x, y) < 0 or min(w, h) <= 0 or x + w > video['width'] or y + h > video['height']:
                raise ValueError(f'{shot["id"]}: crop is outside source frame.')
        reframe = f'crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]},' if crop else ''
        filters.append(f'[{i}:v]trim=start={offset}:duration={length},setpts=PTS-STARTPTS,{reframe}{scale},setsar=1,fps={args.fps},format=yuv420p[v{i}]')
        native_gain = normalized_gain(file, -29, -10, args.native_db) if normalize and not mute_native and any(s['codec_type'] == 'audio' for s in streams) else args.native_db
        if any(s['codec_type'] == 'audio' for s in streams) and not mute_native:
            filters.append(f'[{i}:a]atrim=start={offset}:duration={length},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,apad,atrim=duration={length},volume={native_gain}dB,afade=t=in:d=0.06,afade=t=out:st={max(0,length-0.06)}:d=0.06[a{i}]')
        else:
            filters.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={length},asetpts=PTS-STARTPTS[a{i}]')
        pairs.append(f'[v{i}][a{i}]')
        source_info.append({'shot': shot['id'], 'file': str(file), 'sha256': sha256(file),
                            'requested_trim_in': requested_offset, 'trim_in': offset, 'duration': length,
                            'edit_crop': crop, 'speed': 1, 'native_gain_db': native_gain})
    filters.append(''.join(pairs) + f'concat=n={len(pairs)}:v=1:a=1[video][native]')
    tracks = ['[native]']
    input_index = len(pairs)
    total = float(doc['duration'])
    audio_sources = []
    for kind, name, gain in [('voice', voice, args.voice_db), ('music', music, args.music_db), ('ambience', ambience, ambience_db)]:
        if not name:
            continue
        file = Path(name).resolve()
        meta = probe(file)
        if not any(s['codec_type'] == 'audio' for s in meta['streams']):
            raise ValueError(f'{kind} file has no audio stream.')
        duration = float(meta['format']['duration'])
        if kind == 'voice' and duration > total + 0.05:
            raise ValueError('Voiceover is longer than film. Edit the script/timing explicitly.')
        offset = float(getattr(args, kind + '_offset', None) if getattr(args, kind + '_offset', None) is not None else audio.get(kind + '_offset', 0))
        if not math.isfinite(offset) or offset < 0 or offset >= duration:
            raise ValueError(kind + ': offset must be inside the actual audio source.')
        loop = args.loop_music if kind == 'music' else getattr(args, 'loop_ambience', False) if kind == 'ambience' else False
        if kind == 'music' and duration - offset < total and not loop:
            raise ValueError('Music is short; pass --loop-music only if looping is intended.')
        if kind == 'ambience' and duration - offset < total and not loop:
            raise ValueError('Ambience is short; supply full coverage or explicitly use --loop-ambience.')
        if loop:
            cmd += ['-stream_loop', '-1']
        cmd += ['-i', str(file)]
        if normalize:
            gain = normalized_gain(file, {'voice': -20, 'music': -23, 'ambience': -35}[kind], {'voice': -5, 'music': -6, 'ambience': -14}[kind], gain)
        fade = f',afade=t=in:d=0.4,afade=t=out:st={max(0,total-0.8)}:d=0.8' if kind in {'music', 'ambience'} else ''
        filters.append(f'[{input_index}:a]atrim=start={offset},aresample=48000,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS,apad,atrim=duration={total},volume={gain}dB{fade}[{kind}]')
        tracks.append(f'[{kind}]'); input_index += 1
        audio_sources.append({'kind': kind, 'file': str(file), 'gain_db': gain,
                              'source_start': offset, 'sha256': sha256(file), 'looped': loop})
    if args.duck_music:
        if not voice or not music:
            raise ValueError('--duck-music requires both voice and music.')
        filters += ['[voice]asplit=2[voice_mix][voice_control]', '[music][voice_control]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=300[music_ducked]']
        tracks = ['[native]', '[voice_mix]', '[music_ducked]'] + (['[ambience]'] if ambience else [])
    filters.append(''.join(tracks) + f'amix=inputs={len(tracks)}:duration=longest:normalize=0,alimiter=limit=0.89:level=0:latency=1,atrim=duration={total}[audio]')
    cmd += ['-filter_complex', ';'.join(filters), '-map', '[video]', '-map', '[audio]', '-map_metadata', '-1',
            '-c:v', 'libx264', '-crf', '18', '-preset', 'medium']
    master = None
    if normalize:
        with tempfile.TemporaryDirectory(prefix='cozy-mix-') as td:
            premix = Path(td) / 'picture-and-premix.mkv'
            run(cmd + ['-c:a', 'pcm_s24le', '-ar', '48000', '-t', str(total), str(premix)])
            master = loudness(premix)
            run(['ffmpeg', '-hide_banner', '-v', 'error', '-nostdin', '-i', str(premix),
                 '-map', '0:v:0', '-map', '0:a:0', '-c:v', 'copy', '-af', master_filter(master),
                 '-c:a', 'aac', '-b:a', '256k', '-ar', '48000', '-movflags', '+faststart', '-t', str(total), str(dest)])
    else:
        run(cmd + ['-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-movflags', '+faststart', '-t', str(total), str(dest)])
    result = inspect(dest, decode=True)
    if abs(result['duration'] - total) > max(0.05, 1 / args.fps):
        raise ValueError('Unexpected final duration; inspect the output before delivery.')
    result['sha256'] = sha256(dest)
    result['sources'] = source_info
    result['audio_mix'] = {'music_required': audio.get('music_required', False),
                           'native_muted': mute_native, 'sources': audio_sources,
                           'music_source': audio.get('music_source') if not args.music else None,
                           'normalized_per_source': normalize, 'master_first_pass': master,
                           'master_target_lufs': -18 if normalize else None,
                           'review': 'pending_listening; technical levels do not prove music quality or audibility'}
    result['visual_review'] = 'Selected candidates were explicitly accepted; final playback still required.'
    save(dest.with_suffix('.report.json'), result)
    save(root / 'edit' / 'timeline.json', source_info)
    doc['final_file'] = str(dest.relative_to(root)) if dest.is_relative_to(root) else str(dest)
    quality = doc.setdefault('quality_review', {})
    quality.update(final_cuts={'state': 'pending'}, final_visual={'state': 'pending'}, final_audio={'state': 'pending'})
    quality.pop('technical_report', None); quality.pop('cut_evidence', None)
    save(root / 'project.json', doc)
    return result


def cuts(args):
    root, doc = load(args.project)
    file = Path(args.file).resolve() if args.file else (root / doc['final_file']).resolve()
    report = json.loads(file.with_suffix('.report.json').read_text())
    if report.get('sha256') != sha256(file):
        raise ValueError('Composition report belongs to another encoded file version.')
    rows = report['sources']
    if [(r['shot'], r['duration']) for r in rows] != [(s['id'], s['duration']) for s in doc['shots']]:
        raise ValueError('Project timeline changed after rendering; review the correct file/project version.')
    meta = probe(file); video = next(s for s in meta['streams'] if s['codec_type'] == 'video')
    fps = float(Fraction(video['avg_frame_rate']))
    count = args.handles
    if not 1 <= count <= 12 or any(round(r['duration'] * fps) < count for r in rows):
        raise ValueError('Use1–12 handles, no more than the shortest shot frame count.')
    out = Path(args.out).resolve() if args.out else root / 'review' / (file.stem + '-cuts')
    if out.exists() and any(out.iterdir()):
        raise ValueError('Cut evidence folder must be new or empty.')
    out.mkdir(parents=True, exist_ok=True)
    elapsed = 0; evidence = []
    for i, (before, after) in enumerate(zip(rows, rows[1:]), 1):
        elapsed += before['duration']; boundary = round(elapsed * fps)
        row_file = out / f'cut-{i:03d}.jpg'
        indices = list(range(boundary - count, boundary + count))
        vf = f"select='between(n,{indices[0]},{indices[-1]})',scale=212:120,tile={count*2}x1"
        run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(file), '-vf', vf,
             '-frames:v', '1', '-q:v', '2', str(row_file)])
        if not row_file.is_file():
            raise ValueError('Could not extract exact decoded cut frames.')
        evidence.append({'cut': before['shot'] + '-' + after['shot'], 'time': elapsed,
                         'outgoing_frames': indices[:count], 'incoming_frames': indices[count:],
                         'image': row_file.name})
    pages = []
    if evidence:
        # FFmpeg makes review contact pages; no Pillow or font dependency is needed.
        run(['ffmpeg', '-v', 'error', '-nostdin', '-framerate', '1', '-i', str(out / 'cut-%03d.jpg'),
             '-vf', 'tile=1x5:padding=8:color=0x161616', '-fps_mode', 'vfr', '-q:v', '2', str(out / 'page-%03d.jpg')])
        for i, page in enumerate(sorted(out.glob('page-*.jpg'))):
            pages.append({'file': page.name, 'rows_top_to_bottom': [r['cut'] for r in evidence[i*5:i*5+5]]})
    result = {'source_file': str(file), 'source_sha256': sha256(file), 'fps': fps,
              'method': 'Exact decoded final-film frame indices; outgoing frames on left, incoming frames on right.',
              'cuts': evidence, 'pages': pages, 'visual_review': 'pending; extraction is not acceptance'}
    save(out / 'evidence.json', result)
    doc.setdefault('quality_review', {})['cut_evidence'] = str((out / 'evidence.json').relative_to(root)) if out.is_relative_to(root) else str(out / 'evidence.json')
    save(root / 'project.json', doc)
    return result


def check_final(args):
    root, doc = load(args.project)
    file = Path(args.file).resolve() if args.file else (root / doc['final_file']).resolve()
    meta = probe(file); video = next(s for s in meta['streams'] if s['codec_type'] == 'video')
    audio = next((s for s in meta['streams'] if s['codec_type'] == 'audio'), None)
    spec = doc.get('delivery', {}); fps = float(Fraction(video['avg_frame_rate']))
    duration = float(video.get('duration', meta['format']['duration'])); errors = []; warnings = []
    if abs(duration - doc['duration']) > 1/fps + .001:
        errors.append('Final duration differs from selected timeline.')
    for key in ['width', 'height']:
        if spec.get(key) and video[key] != spec[key]: errors.append('Unexpected ' + key)
    if spec.get('fps') and abs(fps - spec['fps']) > .001: errors.append('Unexpected frame rate.')
    inspect(file, decode=True)
    levels = loudness(file) if audio else None
    settings = doc.get('audio', {})
    intentionally_silent = (not settings.get('music_required', True) and not settings.get('native_audio', True)
                            and not settings.get('music') and not settings.get('ambience') and not settings.get('voiceover'))
    if not audio:
        errors.append('Missing final audio stream.')
    else:
        if int(audio.get('sample_rate', 0)) != 48000 or audio.get('channels') != 2: errors.append('Expected48kHz stereo audio.')
        if float(audio.get('duration', meta['format']['duration'])) + 1/fps < duration: errors.append('Audio ends before picture.')
        if not intentionally_silent:
            if not math.isfinite(float(levels['input_i'])) or abs(float(levels['input_i']) - spec.get('master_lufs', -18)) > 1:
                errors.append('Master integrated loudness is outside target tolerance1LU.')
            if float(levels['input_tp']) > spec.get('master_true_peak', -2) + .5: errors.append('True peak exceeds target tolerance0.5dB.')
    black = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(file), '-vf', 'blackdetect=d=0.08:pix_th=0.02',
                            '-an', '-f', 'null', '-'], capture_output=True, text=True)
    black_intervals = [line.strip() for line in black.stderr.splitlines() if 'black_start:' in line]
    if black_intervals and not spec.get('allow_black_intervals', False): errors.append('Unexpected black interval(s).')
    md5 = run(['ffmpeg', '-v', 'error', '-i', str(file), '-an', '-f', 'framemd5', '-'])
    last = None; repeat = 0; longest = 0; frames_count = 0
    for line in md5.splitlines():
        if not line.strip() or line.startswith('#'): continue
        current = line.rsplit(',', 1)[1].strip(); repeat = repeat+1 if current == last else 1
        longest = max(longest, repeat); last = current; frames_count += 1
    if frames_count != round(doc['duration'] * fps): errors.append('Decoded frame count differs from planned frame count.')
    if longest/fps > .5: warnings.append('Exact repeated frames over0.5s: inspect actual motion; technical detection does not prove a freeze or its cause.')
    result = {'valid': not errors, 'file': str(file), 'sha256': sha256(file), 'duration': duration,
              'fps': fps, 'width': video['width'], 'height': video['height'], 'decoded_frames': frames_count,
              'full_decode': 'passed', 'loudness': levels, 'black_intervals': black_intervals,
              'maximum_exact_identical_frame_run': longest, 'errors': errors, 'warnings': warnings,
              'subjective_playback': 'pending', 'subjective_listening': 'pending'}
    out = Path(args.out).resolve() if args.out else root / 'review' / (file.stem + '-technical.json')
    if out.exists(): raise ValueError('Technical report exists; use a new --out filename.')
    save(out, result)
    doc.setdefault('quality_review', {})['technical_report'] = str(out.relative_to(root)) if out.is_relative_to(root) else str(out)
    save(root / 'project.json', doc)
    return result

def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('inspect'); a.add_argument('file'); a.add_argument('--decode', action='store_true')
    a = sub.add_parser('frames'); a.add_argument('file'); a.add_argument('--out', required=True); a.add_argument('--count', type=int, default=12)
    a = sub.add_parser('compose'); a.add_argument('project'); a.add_argument('--out'); a.add_argument('--width', type=int, default=1280); a.add_argument('--height', type=int, default=720); a.add_argument('--fps', type=int, default=24); a.add_argument('--fit', choices=['crop','pad'], default='crop'); a.add_argument('--mute-native', action='store_true'); a.add_argument('--native-db', type=float, default=0); a.add_argument('--voice'); a.add_argument('--voice-db', type=float, default=0); a.add_argument('--music'); a.add_argument('--music-db', type=float, default=0); a.add_argument('--loop-music', action='store_true'); a.add_argument('--duck-music', action='store_true')
    a.add_argument('--ambience'); a.add_argument('--ambience-db', type=float, default=0); a.add_argument('--loop-ambience', action='store_true'); a.add_argument('--music-offset', type=float); a.add_argument('--ambience-offset', type=float)
    a.add_argument('--normalize-audio', action='store_true', default=True); a.add_argument('--no-normalize-audio', dest='normalize_audio', action='store_false')
    a = sub.add_parser('cuts'); a.add_argument('project'); a.add_argument('--file'); a.add_argument('--out'); a.add_argument('--handles', type=int, default=3)
    a = sub.add_parser('check'); a.add_argument('project'); a.add_argument('--file'); a.add_argument('--out')
    args = p.parse_args()
    result = inspect(args.file, args.decode) if args.cmd == 'inspect' else frames(args) if args.cmd == 'frames' else compose(args) if args.cmd == 'compose' else cuts(args) if args.cmd == 'cuts' else check_final(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.cmd == 'check' and not result['valid']: raise SystemExit(1)

if __name__ == '__main__':
    main()
