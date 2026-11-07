#!/usr/bin/env python3
"""Provider-independent project records, API submission, collection and review."""
import argparse
import json
import math
import re
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path
from providers import MEDIA, download, load_provider, task_id_checked
from quality import preflight

def now():
    return datetime.now(timezone.utc).isoformat()

def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)

def load(project):
    root = Path(project).resolve()
    return root, json.loads((root / 'project.json').read_text(encoding='utf-8'))

def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', value):
        raise ValueError('IDs must be 1–80 letters, digits, underscores or hyphens.')
    return value

def shot_by_id(doc, shot_id):
    return next(s for s in doc['shots'] if s['id'] == shot_id)

def finite_positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0

def validate(doc):
    errors = []
    audio = doc.get('audio', {})
    if not isinstance(audio, dict):
        errors.append('audio must be an object.')
    else:
        for flag in ['music_required', 'native_audio']:
            if flag in audio and not isinstance(audio[flag], bool):
                errors.append(f'audio.{flag} must be a boolean.')
        for field in ['music', 'voiceover']:
            if audio.get(field) is not None and (not isinstance(audio[field], str) or not audio[field].strip()):
                errors.append(f'audio.{field} must be a nonempty path or null.')
    if not finite_positive(doc.get('duration')):
        errors.append('Project duration must be positive.')
    shots = doc.get('shots', [])
    if not shots:
        errors.append('No storyboard shots have been written.')
    ids = set()
    for s in shots:
        sid = s.get('id', '')
        try:
            safe_id(sid)
        except ValueError:
            errors.append(f'Invalid shot ID: {sid!r}')
        if sid in ids:
            errors.append(f'Duplicate shot ID: {sid}')
        ids.add(sid)
        if not finite_positive(s.get('duration')):
            errors.append(f'{sid}: positive edit duration required.')
        if not finite_positive(s.get('generation_duration')):
            errors.append(f'{sid}: positive generation_duration required.')
        elif finite_positive(s.get('duration')) and s['generation_duration'] < s['duration']:
            errors.append(f'{sid}: planned generated clip is shorter than its edit.')
        if not s.get('action'):
            errors.append(f'{sid}: action/story purpose is missing.')
        candidates = s.get('candidates', [])
        cids = [c.get('id') for c in candidates]
        if len(cids) != len(set(cids)):
            errors.append(f'{sid}: duplicate candidate IDs.')
        if s.get('selected_candidate') and s['selected_candidate'] not in cids:
            errors.append(f'{sid}: selected candidate does not exist.')
    total = sum(s.get('duration', 0) for s in shots if finite_positive(s.get('duration')))
    if finite_positive(doc.get('duration')) and abs(total - doc['duration']) > 0.025:
        errors.append(f'Shot edits total {total:g}s; requested {doc["duration"]:g}s.')
    return errors

def init(args):
    root = Path(args.project).resolve()
    if (root / 'project.json').exists():
        raise ValueError('Project already exists; refusing to overwrite.')
    duration = 105 if args.duration is None else args.duration
    if not finite_positive(duration):
        raise ValueError('Duration must be positive.')
    for name in ['references', 'images', 'clips', 'requests', 'review', 'audio', 'final']:
        (root / name).mkdir(parents=True, exist_ok=True)
    doc = {'version': 2, 'title': args.title, 'idea': args.idea, 'duration': duration,
           'duration_range': [90, 120] if args.duration is None else [duration, duration],
           'aspect_ratio': args.ratio, 'style': '宫崎骏／吉卜力式二维手绘治愈动画',
           'creative_mode': 'cozy_relaxation',
           'style_version': 1, 'style_anchor': None, 'style_review': None,
           'themes': [], 'script': '', 'characters': [], 'scenes': [], 'shots': [],
           'generation': {'image': None, 'video': None, 'speech': None, 'music': None},
           'limits': {'max_candidates_per_shot': 2, 'budget': None},
           'audio': {'voiceover': None, 'music': None, 'music_required': True,
                     'music_brief': '', 'music_source': None, 'native_audio': True},
           'quality_review': {'motion': 'pending', 'final_audio': 'pending'}, 'created_at': now()}
    save(root / 'project.json', doc)
    return {'project': str(root), 'state': 'ready_for_script_and_storyboard'}

def backend(args):
    return load_provider(getattr(args, 'provider', None), getattr(args, 'server', None))

def provider_matches(candidate, provider):
    identity = candidate.get('provider')
    if identity is None:
        # Read old version-1 ComfyUI projects without rewriting their history.
        return provider.kind == 'comfyui' and 'prompt_id' in candidate
    return identity == provider.identity

def new_candidate(doc, shot_id, candidate_id, provider, seconds=None):
    safe_id(candidate_id)
    s = shot_by_id(doc, shot_id)
    if any(c['id'] == candidate_id for c in s.get('candidates', [])):
        raise ValueError('Candidate exists. Use a new version; never overwrite a generation.')
    return s, {'id': candidate_id, 'task_id': None, 'provider': provider.identity,
               'state': 'submitted', 'files': [], 'created_at': now(), 'review': None,
               'generated_seconds': seconds if seconds is not None else s.get('generation_duration')}

def register(args):
    root, doc = load(args.project)
    provider = backend(args)
    task_id = task_id_checked(getattr(args, 'task_id', None) or getattr(args, 'prompt_id', None))
    output_node = getattr(args, 'output_node', None)
    if provider.kind == 'comfyui' and output_node is None:
        raise ValueError('ComfyUI requires --output-node.')
    for other in doc['shots']:
        for c in other.get('candidates', []):
            if provider_matches(c, provider) and (c.get('task_id') or c.get('prompt_id')) == task_id:
                if other['id'] == args.shot and c['id'] == args.candidate:
                    return {'state': 'already_registered', 'candidate': c['id']}
                raise ValueError('Task ID is already registered to another candidate.')
    if getattr(args, 'recover', False):
        s = shot_by_id(doc, args.shot)
        c = next(c for c in s.get('candidates', []) if c['id'] == args.candidate)
        if not provider_matches(c, provider) or c.get('task_id') or c['state'] not in {'submitting', 'submission_unknown'}:
            raise ValueError('Recovery only binds a verified task ID to an uncertain submission.')
    else:
        s, c = new_candidate(doc, args.shot, args.candidate, provider, args.seconds)
        s.setdefault('candidates', []).append(c)
    c.update(task_id=task_id, output_node=str(output_node) if output_node is not None else None,
             state='submitted', request_file=getattr(args, 'request', None) or getattr(args, 'workflow', None))
    save(root / 'project.json', doc)
    return {'shot': s['id'], 'candidate': c['id'], 'state': c['state'],
            'limit_exceeded': len(s['candidates']) > doc.get('limits', {}).get('max_candidates_per_shot', 2)}

def submit(args):
    root, doc = load(args.project)
    provider = backend(args)
    if not callable(getattr(provider, 'submit', None)):
        raise ValueError('This adapter only collects tasks; submit through its configured client and register the task ID.')
    payload_bytes = Path(args.request).read_bytes()
    payload = json.loads(payload_bytes)
    if not isinstance(payload, dict):
        raise ValueError('Request body must be a JSON object matching the provider documentation.')
    # Credentials belong in environment-backed headers, not in saved generation requests.
    def check_credentials(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key.lower() in {'api_key', 'apikey', 'access_token', 'authorization', 'secret', 'api_token'}:
                    raise ValueError('Keep credentials in environment variables, not request JSON.')
                check_credentials(item)
        elif isinstance(value, list):
            for item in value:
                check_credentials(item)
    check_credentials(payload)
    s, c = new_candidate(doc, args.shot, args.candidate, provider, args.seconds)
    if any(item.get('state') in {'submitting', 'submission_unknown'} for item in s.get('candidates', [])):
        raise ValueError('An earlier submission is uncertain. Recover its task ID before creating another.')
    if len(s.get('candidates', [])) >= doc.get('limits', {}).get('max_candidates_per_shot', 2):
        raise ValueError('Candidate limit reached; review the existing attempts before changing the limit.')
    summary = {'provider': provider.name, 'shot': s['id'], 'candidate': c['id'],
               'request_sha256': hashlib.sha256(payload_bytes).hexdigest(), 'dry_run': not args.execute}
    if not args.execute:
        return summary
    provider.preflight(payload)  # Check local prerequisites before reserving a paid attempt.
    c.update(state='submitting', request_file=str(Path(args.request).resolve()), request_sha256=summary['request_sha256'])
    s.setdefault('candidates', []).append(c)
    save(root / 'project.json', doc)  # Reserve before POST; a process crash must not invite a duplicate.
    try:
        c['task_id'] = provider.submit(payload)
    except Exception:
        c['state'] = 'submission_unknown'
        save(root / 'project.json', doc)
        raise RuntimeError('Submission outcome is uncertain; inspect the provider dashboard and recover the task ID. No automatic retry.') from None
    c['state'] = 'submitted'
    save(root / 'project.json', doc)
    return {**summary, 'task_id': c['task_id'], 'state': c['state']}

def collect(args):
    root, doc = load(args.project)
    provider = backend(args)
    report = []
    for shot in doc['shots']:
        for candidate in shot.get('candidates', []):
            if not provider_matches(candidate, provider):
                continue
            entry = {'shot': shot['id'], 'candidate': candidate['id']}
            if candidate.get('state') == 'success' and candidate.get('files') and all((root / f).is_file() for f in candidate['files']):
                report.append({**entry, 'state': 'success_cached'})
                continue
            task_id = candidate.get('task_id') or candidate.get('prompt_id')
            if not task_id:
                report.append({**entry, 'state': candidate['state']})
                continue
            result = provider.poll(task_id, candidate.get('output_node'))
            candidate['state'] = result['state']
            if result['state'] == 'success':
                assets = result['assets']
                candidate['state'] = 'success' if assets else 'completed_without_expected_output'
                destdir = root / 'clips' / safe_id(shot['id'])
                destdir.mkdir(parents=True, exist_ok=True)
                files = []
                for index, asset in enumerate(assets):
                    suffix = asset['extension']
                    if suffix not in MEDIA:
                        raise ValueError('Unsupported media extension.')
                    dest = destdir / f'{safe_id(candidate["id"])}-{index:02d}{suffix}'
                    if not dest.exists():
                        download(asset['url'], dest)
                    files.append(str(dest.relative_to(root)))
                candidate['files'] = files
            candidate['checked_at'] = now()
            # Save only normalized metadata, never temporary signed URLs or API responses.
            save(root / 'project.json', doc)
            report.append({**entry, 'state': candidate['state'], 'files': candidate.get('files', [])})
    return report


def import_asset(args):
    root, doc = load(args.project)
    file = Path(args.file).resolve()
    if not file.is_file() or file.suffix.lower() not in MEDIA or not file.stat().st_size:
        raise ValueError('Import requires an existing, nonempty media file.')
    safe_id(args.candidate)
    shot = shot_by_id(doc, args.shot)
    if any(c['id'] == args.candidate for c in shot.get('candidates', [])):
        raise ValueError('Candidate already exists; use a new version.')
    folder = root / 'clips' / safe_id(args.shot)
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / (args.candidate + '-00' + file.suffix.lower())
    if dest.exists():
        raise ValueError('Destination exists; refusing to overwrite media.')
    shutil.copy2(file, dest)
    candidate = {'id': args.candidate, 'task_id': args.task_id,
                 'provider': {'kind': 'import', 'name': args.source_label},
                 'state': 'success', 'files': [str(dest.relative_to(root))],
                 'created_at': now(), 'review': None, 'generated_seconds': args.seconds}
    shot.setdefault('candidates', []).append(candidate)
    save(root / 'project.json', doc)
    return {'shot': shot['id'], 'candidate': candidate['id'], 'state': 'success', 'review': 'required'}


def select(args):
    root, doc = load(args.project)
    s = shot_by_id(doc, args.shot)
    c = next(c for c in s.get('candidates', []) if c['id'] == args.candidate)
    if args.verdict == 'accept':
        if c.get('state') != 'success':
            raise ValueError('Only successful collected candidates can be selected.')
        files = c.get('files', [])
        if not 0 <= args.asset < len(files) or not (root / files[args.asset]).is_file():
            raise ValueError('Selected asset is missing.')
        if not math.isfinite(args.trim_in) or args.trim_in < 0:
            raise ValueError('trim_in cannot be negative.')
        s['selected_candidate'] = c['id']
        s['selected_file'] = files[args.asset]
        s['trim_in'] = args.trim_in
    elif s.get('selected_candidate') == c['id']:
        s['selected_candidate'] = None
        s.pop('selected_file', None)
    c['review'] = {'verdict': args.verdict, 'note': args.note, 'time': now()}
    save(root / 'project.json', doc)
    return {'shot': s['id'], 'candidate': c['id'], 'review': c['review']}

def status(args):
    _, doc = load(args.project)
    return {'title': doc['title'], 'errors': validate(doc), 'shots': [
        {'id': s['id'], 'selected': s.get('selected_candidate'), 'attempts': len(s.get('candidates', [])),
         'states': [c.get('state') for c in s.get('candidates', [])]} for s in doc['shots']],
        'recorded_generated_seconds': sum(c.get('generated_seconds') or 0 for s in doc['shots'] for c in s.get('candidates', []))}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    a = sub.add_parser('init'); a.add_argument('project'); a.add_argument('--idea', required=True); a.add_argument('--title', default='治愈短片'); a.add_argument('--duration', type=float, default=None); a.add_argument('--ratio', default='16:9')
    a = sub.add_parser('validate'); a.add_argument('project')
    a = sub.add_parser('preflight'); a.add_argument('project')
    a = sub.add_parser('status'); a.add_argument('project')
    a = sub.add_parser('register'); a.add_argument('project'); a.add_argument('--shot', required=True); a.add_argument('--candidate', required=True); a.add_argument('--task-id', '--prompt-id', dest='task_id', required=True); a.add_argument('--output-node'); a.add_argument('--request', '--workflow', dest='request'); a.add_argument('--seconds', type=float); a.add_argument('--provider'); a.add_argument('--server'); a.add_argument('--recover', action='store_true')
    a = sub.add_parser('collect'); a.add_argument('project'); a.add_argument('--provider'); a.add_argument('--server')
    a = sub.add_parser('submit'); a.add_argument('project'); a.add_argument('--shot', required=True); a.add_argument('--candidate', required=True); a.add_argument('--provider', required=True); a.add_argument('--request', required=True); a.add_argument('--seconds', type=float); a.add_argument('--execute', action='store_true')
    a = sub.add_parser('import'); a.add_argument('project'); a.add_argument('--shot', required=True); a.add_argument('--candidate', required=True); a.add_argument('--file', required=True); a.add_argument('--source-label', default='external'); a.add_argument('--task-id'); a.add_argument('--seconds', type=float)
    a = sub.add_parser('review'); a.add_argument('project'); a.add_argument('--shot', required=True); a.add_argument('--candidate', required=True); a.add_argument('--verdict', choices=['accept', 'reject'], required=True); a.add_argument('--note', required=True); a.add_argument('--asset', type=int, default=0); a.add_argument('--trim-in', type=float, default=0)
    args = p.parse_args()
    try:
        if args.command in {'validate', 'preflight'}:
            doc = load(args.project)[1]
            errors = validate(doc)
            if args.command == 'preflight': errors += preflight(doc)
            result = {'valid': not errors, 'errors': errors}
        else:
            result = {'init': init, 'register': register, 'submit': submit, 'collect': collect, 'import': import_asset, 'review': select, 'status': status}[args.command](args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command in {'validate', 'preflight'} and errors:
            raise SystemExit(1)
    except (ValueError, KeyError, StopIteration, OSError, RuntimeError) as exc:
        print(json.dumps({'error': type(exc).__name__, 'message': str(exc)}, ensure_ascii=False))
        raise SystemExit(1)

if __name__ == '__main__':
    main()
