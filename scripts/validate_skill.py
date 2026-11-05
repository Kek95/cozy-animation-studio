#!/usr/bin/env python3
"""Validate repository metadata, references, workflow bindings and Python syntax."""
import ast
import json
import re
from pathlib import Path

from studio import validate
from workflow import patch, reject_secrets
from providers import load_provider


def check(root):
    try:
        import yaml
    except ImportError as exc:
        raise ValueError('Install development dependencies: pip install -r requirements-dev.txt') from exc
    text = (root / 'SKILL.md').read_text(encoding='utf-8')
    match = re.match(r'\A---\n(.*?)\n---(?:\n|$)', text, re.S)
    if not match:
        raise ValueError('SKILL.md needs YAML frontmatter.')
    meta = yaml.safe_load(match.group(1))
    if meta.get('name') != 'cozy-animation-studio' or not meta.get('description'):
        raise ValueError('Missing skill name or description.')
    interface = yaml.safe_load((root / 'agents/openai.yaml').read_text(encoding='utf-8'))['interface']
    for field in ('display_name', 'short_description', 'default_prompt'):
        if not interface.get(field):
            raise ValueError(f'Missing interface field: {field}')
    if '$cozy-animation-studio' not in interface['default_prompt']:
        raise ValueError('Default prompt must invoke the skill.')
    count = 0
    for file in [root / 'SKILL.md', root / 'README.md', *sorted((root / 'references').glob('*.md'))]:
        # Validate actual local Markdown links, not code samples or example assets.
        for target in re.findall(r'\[[^\]]+\]\(([^\s)]+)\)', file.read_text(encoding='utf-8')):
            if re.match(r'[a-z]+://|#', target):
                continue
            local = (file.parent / target.split('#')[0]).resolve()
            if not local.is_relative_to(root.resolve()) or not local.exists():
                raise ValueError(f'{file.name}: missing or external local link {target}')
    for file in sorted((root / 'assets').rglob('*.json')):
        if file.parent.name == 'providers':
            load_provider(file)
        else:
            reject_secrets(json.loads(file.read_text(encoding='utf-8')))
        count += 1
    for bindings_file in sorted((root / 'assets/comfyui').glob('*_bindings.json')):
        graph_file = bindings_file.with_name(bindings_file.name.replace('_bindings.json', '_api.json'))
        graph = json.loads(graph_file.read_text(encoding='utf-8'))
        bindings = json.loads(bindings_file.read_text(encoding='utf-8'))
        values = {name: graph[str(b['node'])]['inputs'][b['input']] for name, b in bindings.items()}
        patch(graph, bindings, values)
    errors = validate(json.loads((root / 'assets/project-example.json').read_text(encoding='utf-8')))
    if errors:
        raise ValueError('; '.join(errors))
    scripts = sorted((root / 'scripts').glob('*.py'))
    for file in scripts:
        ast.parse(file.read_text(encoding='utf-8'), filename=file.name, feature_version=(3, 10))
    return {'valid': True, 'json_assets': count, 'python_scripts': len(scripts)}


if __name__ == '__main__':
    print(json.dumps(check(Path(__file__).resolve().parents[1]), ensure_ascii=False, indent=2))
