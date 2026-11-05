#!/usr/bin/env python3
"""Inspect installed ComfyUI nodes and patch exported API graphs without submitting."""
import argparse
import copy
import hashlib
import json
import re
import urllib.request
from pathlib import Path

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def reject_secrets(value):
    if isinstance(value, dict):
        for k, v in value.items():
            if any(s in k.lower() for s in ['api_key', 'access_token', 'auth_token', 'authorization', 'secret']):
                raise ValueError('Workflow contains credential fields. Export a clean graph; keep authentication in the app.')
            reject_secrets(v)
    elif isinstance(value, list):
        for v in value:
            reject_secrets(v)

def patch(graph, bindings, values):
    if 'nodes' in graph or not graph or any(not isinstance(v, dict) or 'class_type' not in v for v in graph.values()):
        raise ValueError('Expected API node graph, not ComfyUI canvas/layout JSON.')
    reject_secrets(graph)
    if not isinstance(bindings, dict) or not isinstance(values, dict):
        raise ValueError('Bindings and values must be objects.')
    unknown = set(values) - set(bindings)
    if unknown:
        raise ValueError('Unmapped parameters: ' + ', '.join(sorted(unknown)))
    result = copy.deepcopy(graph)
    for name, value in values.items():
        binding = bindings[name]
        if isinstance(value, (dict, list)):
            raise ValueError(f'{name}: scalar widget values only; links must remain in the exported graph.')
        if 'choices' in binding and value not in binding['choices']:
            raise ValueError(f'{name}: value is not among the verified node choices.')
        if 'min' in binding or 'max' in binding:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f'{name}: numeric value required.')
            if ('min' in binding and not value >= binding['min']) or ('max' in binding and not value <= binding['max']):
                raise ValueError(f'{name}: value is outside the verified node range.')
        nid, field = str(binding['node']), binding['input']
        if nid not in result or field not in result[nid].get('inputs', {}):
            raise ValueError(f'{name}: binding does not match exported graph.')
        if binding.get('class_type') and result[nid]['class_type'] != binding['class_type']:
            raise ValueError(f'{name}: node class changed.')
        old = result[nid]['inputs'][field]
        if isinstance(old, list) and len(old) == 2 and str(old[0]) in result and isinstance(old[1], int):
            raise ValueError(f'{name}: input is a node link; patch the upstream widget instead.')
        result[nid]['inputs'][field] = value
    reject_secrets(result)
    return result

def doctor(server, pattern):
    with urllib.request.urlopen(server.rstrip('/') + '/system_stats', timeout=15) as r:
        stats = json.load(r)
    with urllib.request.urlopen(server.rstrip('/') + '/object_info', timeout=30) as r:
        info = json.load(r)
    nodes = []
    for name, node in info.items():
        if not re.search(pattern, name, re.I):
            continue
        inp = node.get('input', {})
        fields = []
        for group in ['required', 'optional']:
            for key, spec in inp.get(group, {}).items():
                # Report field names/types, not user filenames, secret values or hidden authentication.
                typ = spec[0] if spec and isinstance(spec[0], str) else 'COMBO'
                fields.append({'name': key, 'type': typ, 'required': group == 'required'})
        models = inp.get('required', {}).get('model', [])
        options = models[1].get('options', []) if len(models) > 1 and isinstance(models[1], dict) else []
        nodes.append({'class_type': name, 'display_name': node.get('display_name'), 'fields': fields,
                      'model_options': [o.get('key') for o in options if isinstance(o, dict)]})
    return {'comfyui_version': stats.get('system', {}).get('comfyui_version'), 'nodes': nodes}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('doctor'); a.add_argument('--server', default='http://127.0.0.1:8188'); a.add_argument('--pattern', default='ByteDance2|OpenAIGPTImage|LoadImage|SaveVideo|SaveImage'); a.add_argument('--out')
    a = sub.add_parser('patch'); a.add_argument('--graph', required=True); a.add_argument('--bindings', required=True); a.add_argument('--values', required=True); a.add_argument('--out', required=True)
    args = p.parse_args()
    if args.cmd == 'doctor':
        result = doctor(args.server, args.pattern)
    else:
        result = patch(read(args.graph), read(args.bindings), read(args.values))
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.out:
        dest = Path(args.out)
        if dest.exists():
            raise ValueError('Output exists. Use a new version filename.')
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding='utf-8')
        print(json.dumps({'file': str(dest.resolve()), 'sha256': hashlib.sha256(text.encode()).hexdigest()}, ensure_ascii=False))
    else:
        print(text)

if __name__ == '__main__':
    main()
