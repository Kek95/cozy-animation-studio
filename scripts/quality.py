"""Read-only planning checks; cannot judge generated pixels or actual motion."""
import math

def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0

def strings(value):
    return isinstance(value, list) and bool(value) and all(isinstance(x, str) and x.strip() for x in value)

def preflight(doc):
    errors = []
    scenes = {s.get('id'): s for s in doc.get('scenes', []) if isinstance(s, dict)}
    bounds = doc.get('duration_range')
    if bounds is not None:
        if not isinstance(bounds, list) or len(bounds) != 2 or not all(positive(x) for x in bounds) or bounds[0] > bounds[1]:
            errors.append('duration_range must contain ordered positive minimum/maximum seconds.')
        elif positive(doc.get('duration')) and not bounds[0] <= doc['duration'] <= bounds[1]:
            errors.append('Project duration is outside its declared duration_range.')
    prior = None
    for shot in doc.get('shots', []):
        sid = shot.get('id', '?')
        for field in ('image_prompt', 'video_prompt'):
            if not isinstance(shot.get(field), str) or not shot[field].strip():
                errors.append(f'{sid}: {field} must contain the actual prompt.')
        motion = shot.get('motion_plan')
        if not isinstance(motion, dict):
            errors.append(f'{sid}: motion_plan is missing.'); motion = {}
        if motion.get('speed_mode') != 'normal' and not str(motion.get('intentional_speed_change') or '').strip():
            errors.append(f'{sid}: use normal speed or document the intentional speed change.')
        if not positive(motion.get('active_seconds')) or (positive(shot.get('duration')) and motion.get('active_seconds', 0) > shot['duration']):
            errors.append(f'{sid}: active_seconds must be positive and fit within the edit duration.')
        inter = shot.get('interaction', {})
        if not isinstance(inter, dict): inter = {}
        for field in ('preconditions', 'ordered_steps', 'contact_rules'):
            if not strings(inter.get(field)):
                errors.append(f'{sid}: interaction.{field} needs concrete nonempty steps/rules.')
        c = shot.get('continuity', {})
        if not isinstance(c, dict): c = {}
        scene = scenes.get(shot.get('scene_id'), {})
        if not c.get('layout_version') or c['layout_version'] != scene.get('layout_version'):
            errors.append(f'{sid}: continuity.layout_version must match its scene reference version.')
        if not strings(c.get('scene_locks')):
            errors.append(f'{sid}: continuity.scene_locks is missing.')
        before, after, allowed = c.get('prop_states_in'), c.get('prop_states_out'), c.get('allowed_state_changes')
        if not isinstance(before, dict) or not isinstance(after, dict) or not before or not after:
            errors.append(f'{sid}: nonempty prop_states_in/out maps are required.')
        else:
            if any(not isinstance(k, str) or not k or not isinstance(v, str) or not v.strip() for states in (before, after) for k, v in states.items()):
                errors.append(f'{sid}: state keys and values must be nonempty strings.')
            changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
            if not isinstance(allowed, list) or any(not isinstance(k, str) for k in allowed) or set(allowed) != changed:
                errors.append(f'{sid}: allowed_state_changes must exactly name changed state keys.')
            if prior is not None:
                mismatches = [k for k in set(prior) & set(before) if prior[k] != before[k]]
                if mismatches and not (c.get('time_ellipsis') is True and str(c.get('transition_reason') or '').strip()):
                    errors.append(f'{sid}: incoming state resets prior output: {", ".join(sorted(mismatches))}.')
            prior = after
        if c.get('time_ellipsis') is True and not str(c.get('transition_reason') or '').strip():
            errors.append(f'{sid}: time ellipsis needs transition_reason.')
    return errors
