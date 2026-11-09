#!/usr/bin/env python3
"""Read-only production gates. Evidence records never substitute for seeing/hearing media."""
import argparse
import hashlib
import json
from pathlib import Path
from quality import preflight


def sha256(file):
    h = hashlib.sha256()
    with Path(file).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def plan_errors(doc):
    # Imported only when called: studio also uses the video gate before POST.
    from studio import validate
    return validate(doc) + preflight(doc)


def local_file(root, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('a project-local file is required')
    root = Path(root).resolve()
    file = (root / value).resolve()
    if not file.is_relative_to(root) or not file.is_file() or not file.stat().st_size:
        raise ValueError('file is missing, empty, or outside the project: ' + value)
    return file


def evidence_errors(root, review, label):
    errors = []
    if not isinstance(review, dict) or not str(review.get('observations') or '').strip():
        return [label + ': actual observations are required.']
    evidence = review.get('evidence', [])
    if not isinstance(evidence, list) or not evidence:
        return [label + ': evidence files are required.']
    for value in evidence:
        try:
            local_file(root, value)
        except ValueError as exc:
            errors.append(label + ': ' + str(exc))
    return errors


def accepted_asset(root, asset, label):
    errors = []
    try:
        file = local_file(root, asset.get('file'))
        if asset.get('sha256') != sha256(file):
            errors.append(label + ': recorded hash does not match actual file.')
    except ValueError as exc:
        errors.append(label + ': ' + str(exc))
    review = asset.get('review') or {}
    if review.get('verdict') != 'accept':
        errors.append(label + ': actual asset has not been accepted.')
    return errors + evidence_errors(root, review, label)


def keyframe_errors(doc, root, shot):
    sid = shot['id']; errors = []
    refs = {x['id']: x for x in doc.get('reference_assets', [])}
    required = shot.get('required_reference_ids', [])
    if not isinstance(required, list) or not required:
        errors.append(sid + ': required_reference_ids must name the approved visual references.')
        required = []
    bindings = shot.get('image_conditioning', [])
    for rid in required:
        if rid not in refs:
            errors.append(sid + ': missing reference asset ' + str(rid)); continue
        ref = refs[rid]
        errors += accepted_asset(root, ref, str(rid))
        found = next((b for b in bindings if b.get('reference_id') == rid), None)
        if not found:
            errors.append(sid + ': no actual image conditioning for ' + rid); continue
        if found.get('source_sha256') != ref.get('sha256'):
            errors.append(sid + ': stale image conditioning hash for ' + rid)
        errors += binding_errors(root, found, sid + '/' + rid)
    image = {'file': shot.get('image_file'), 'sha256': shot.get('image_sha256'),
             'review': shot.get('image_review')}
    errors += accepted_asset(root, image, sid + ' keyframe')
    return errors


def binding_errors(root, binding, label):
    errors = []
    if not str(binding.get('method') or '').strip() or not str(binding.get('input_field') or '').strip():
        errors.append(label + ': actual attachment method and input_field are required.')
    try:
        local_file(root, binding.get('evidence_file'))
    except ValueError as exc:
        errors.append(label + ': conditioning evidence ' + str(exc))
    return errors


def request_models(payload, pointer=None):
    """Read a documented JSON pointer, or the actual model widgets in an API node graph."""
    if pointer:
        value = payload
        if not pointer.startswith('/'):
            raise ValueError('model pointer must be a JSON pointer beginning with /.')
        for token in pointer[1:].split('/'):
            token = token.replace('~1', '/').replace('~0', '~')
            value = value[int(token)] if isinstance(value, list) else value[token]
        if not isinstance(value, str):
            raise ValueError('model pointer must resolve to a model string.')
        return [value]
    if isinstance(payload.get('model'), str):
        return [payload['model']]
    graph = payload.get('prompt') if isinstance(payload.get('prompt'), dict) else payload
    return [n['inputs']['model'] for n in graph.values()
            if isinstance(n, dict) and str(n.get('class_type', '')).startswith('ByteDance')
            and isinstance(n.get('inputs', {}).get('model'), str)]


def pilot_passed(doc, root):
    pilot = doc.get('quality_review', {}).get('pilot') or {}
    if pilot.get('verdict') != 'accept' or evidence_errors(root, pilot, 'pilot'):
        return False
    shot = next((s for s in doc['shots'] if s['id'] == pilot.get('shot')), None)
    candidate = next((c for c in (shot or {}).get('candidates', []) if c['id'] == pilot.get('candidate')), None)
    if not candidate or candidate.get('state') != 'success' or (candidate.get('review') or {}).get('verdict') != 'accept':
        return False
    try:
        return any(sha256(local_file(root, f)) == pilot.get('source_sha256') for f in candidate.get('files', []))
    except ValueError:
        return False


def generation_errors(doc, root, shot_id, payload=None, model_pointer=None):
    policy = doc.get('production_policy', {})
    if not policy.get('enabled', False):
        return []  # Older task-record projects remain readable/importable.
    errors = plan_errors(doc)
    shot = next(s for s in doc['shots'] if s['id'] == shot_id)
    if policy.get('require_reference_conditioning', True):
        errors += keyframe_errors(doc, root, shot)
        binding = shot.get('video_conditioning') or {}
        errors += binding_errors(root, binding, shot_id + ' video')
        if binding.get('source_sha256') != shot.get('image_sha256'):
            errors.append(shot_id + ': video conditioning does not match accepted keyframe hash.')
    allowed = (doc.get('generation', {}).get('video') or {}).get('allowed_models', [])
    if allowed:
        try:
            models = request_models(payload or {}, model_pointer)
            if not models or any(m not in allowed for m in models):
                errors.append(shot_id + ': request model is missing or outside allowed_models; use the real field/pointer, never an automatic fallback.')
        except (ValueError, KeyError, IndexError, TypeError):
            errors.append(shot_id + ': cannot resolve model from the actual request using the documented pointer.')
    if policy.get('require_pilot', True) and shot_id not in policy.get('pilot_shots', []) and not pilot_passed(doc, root):
        errors.append(shot_id + ': approve an actual representative pilot before expanding; or name this shot in production_policy.pilot_shots to test it first.')
    return errors


def check(doc, root, stage, shot_id=None, payload=None, model_pointer=None):
    errors = plan_errors(doc); pending = []
    if stage == 'keyframes':
        for shot in doc['shots']:
            errors += keyframe_errors(doc, root, shot)
    elif stage == 'video':
        if not shot_id:
            errors.append('--shot is required for the video gate.')
        else:
            errors += generation_errors(doc, root, shot_id, payload, model_pointer)
    elif stage == 'final':
        final_hash = None
        try:
            final = local_file(root, doc.get('final_file'))
            final_hash = sha256(final)
            tech = json.loads(local_file(root, doc.get('quality_review', {}).get('technical_report')).read_text())
            if not tech.get('valid') or tech.get('sha256') != sha256(final):
                errors.append('Final technical report is invalid or belongs to another file version.')
            cuts = json.loads(local_file(root, doc.get('quality_review', {}).get('cut_evidence')).read_text())
            if cuts.get('source_sha256') != sha256(final):
                errors.append('Cut evidence belongs to another final file version.')
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            errors.append('Final evidence: ' + str(exc))
        for key, method in [('final_cuts', 'encoded_cut_frames'), ('final_visual', 'continuous_playback'), ('final_audio', 'subjective_listening')]:
            review = doc.get('quality_review', {}).get(key) or {}
            if not isinstance(review, dict) or review.get('state') != 'passed' or review.get('method') != method:
                pending.append(key + ': actual ' + method + ' is pending; label delivery as a test/render, not fully listened/viewed.')
            else:
                errors += evidence_errors(root, review, key)
                if not final_hash or review.get('source_sha256') != final_hash:
                    errors.append(key + ': review belongs to another file version.')
    return {'stage': stage, 'ready': not errors and not pending, 'blockers': sorted(set(errors)),
            'pending_reviews': pending, 'can_deliver_test': stage == 'final' and not errors,
            'scope': 'Checks recorded files/hashes/contracts only; agent must actually inspect visuals and listen.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project'); parser.add_argument('--stage', choices=['plan', 'keyframes', 'video', 'final'], required=True)
    parser.add_argument('--shot'); parser.add_argument('--request'); parser.add_argument('--model-pointer')
    args = parser.parse_args(); root = Path(args.project).resolve()
    try:
        doc = json.loads((root / 'project.json').read_text())
        payload = json.loads(Path(args.request).read_text()) if args.request else None
        result = check(doc, root, args.stage, args.shot, payload, args.model_pointer)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(1 if result['blockers'] else 0)
    except (OSError, ValueError, KeyError, StopIteration) as exc:
        parser.exit(1, json.dumps({'error': str(exc)}, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
