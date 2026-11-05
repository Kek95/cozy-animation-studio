"""Optional generation backends. No dependency on ComfyUI or a vendor SDK."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MEDIA = {'.mp4', '.webm', '.mov', '.png', '.jpg', '.jpeg', '.webp', '.wav', '.mp3', '.flac', '.m4a'}
STATES = {'pending', 'running', 'success', 'error', 'cancelled', 'unknown'}


def url_checked(url):
    parts = urllib.parse.urlsplit(url)
    if parts.username or parts.password or not parts.hostname:
        raise ValueError('URLs must not contain credentials and must have a hostname.')
    if parts.scheme != 'https' and not (parts.scheme == 'http' and parts.hostname in {'localhost', '127.0.0.1', '::1'}):
        raise ValueError('Use HTTPS; plain HTTP is supported only for loopback services.')
    return url


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never replay credentials or a paid POST to a redirect target.
        fp.close()
        raise ValueError('API redirect refused; configure the documented endpoint directly.')


class MediaRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        url_checked(newurl)
        # Media requests never include API headers.
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def request_json(url, headers=None, body=None):
    url_checked(url)
    headers = dict(headers or {})
    headers['Accept'] = 'application/json'
    if body is not None:
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(url, headers=headers, data=None if body is None else json.dumps(body).encode())
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # Do not expose response bodies or signed URLs in error logs.
        code = exc.code
        exc.close()
        raise RuntimeError(f'Provider HTTP {code}; inspect the provider dashboard.') from None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        raise RuntimeError('Provider response unavailable; do not repeat a submission automatically.') from None


def pointer(doc, path):
    if path == '':
        return doc
    if not isinstance(path, str) or not path.startswith('/'):
        raise ValueError('Response fields must use JSON Pointer paths, e.g. /data/id.')
    for part in path[1:].split('/'):
        part = part.replace('~1', '/').replace('~0', '~')
        doc = doc[int(part)] if isinstance(doc, list) else doc[part]
    return doc


def task_id_checked(value):
    if not isinstance(value, (str, int)) or isinstance(value, bool) or not str(value) or len(str(value)) > 512:
        raise ValueError('Provider response did not contain a usable task ID.')
    return str(value)


def download(url, destination):
    """Download public/signed result URL without forwarding API credentials."""
    url_checked(url)
    destination = Path(destination)
    temp = destination.with_suffix(destination.suffix + '.part')
    try:
        with urllib.request.build_opener(MediaRedirect).open(url, timeout=60) as response, temp.open('wb') as stream:
            while chunk := response.read(1024 * 1024):
                stream.write(chunk)
        if temp.stat().st_size == 0:
            raise ValueError('Empty media response.')
        temp.replace(destination)
    except urllib.error.HTTPError as exc:
        exc.close()
        raise RuntimeError('Media download failed; collect the same task again.') from None
    except (OSError, urllib.error.URLError):
        raise RuntimeError('Media download failed; collect the same task again.') from None


class JsonHttpProvider:
    """Configured asynchronous JSON POST + GET API; no vendor-specific assumptions."""
    kind = 'json-http'

    def __init__(self, config):
        self.config = config
        self.name = config['name']
        self.base_url = url_checked(config['base_url']).rstrip('/')
        parts = urllib.parse.urlsplit(self.base_url)
        if parts.query or parts.fragment:
            raise ValueError('base_url must not contain query parameters or a fragment.')
        self.identity = {'name': self.name, 'kind': self.kind, 'endpoint': self.base_url}
        for path in (config['submit']['path'], config['poll']['path']):
            if not path.startswith('/') or path.startswith('//') or '?' in path or '#' in path:
                raise ValueError('Endpoint paths must be relative paths without query parameters.')
        if '{task_id}' not in config['poll']['path']:
            raise ValueError('Poll path must contain {task_id}.')
        if any(value not in STATES for value in config['poll']['states'].values()):
            raise ValueError('Invalid normalized task state.')
        if config['poll']['output_extension'] not in MEDIA:
            raise ValueError('Unsupported output file extension.')
        if not isinstance(self.name, str) or not self.name:
            raise ValueError('Provider name is required.')

    def headers(self):
        # Only environment variable names live in the config; no embedded keys.
        headers = {}
        for header, binding in self.config.get('headers_from_env', {}).items():
            value = os.environ.get(binding['env'])
            if not value:
                raise ValueError(f'Missing environment variable: {binding["env"]}')
            headers[header] = binding.get('prefix', '') + value
        return headers

    def submit(self, payload):
        response = request_json(self.base_url + self.config['submit']['path'], self.headers(), payload)
        return task_id_checked(pointer(response, self.config['submit']['task_id_pointer']))

    def preflight(self, payload):
        """Check local credentials without creating a task."""
        self.headers()

    def poll(self, task_id, output_node=None):
        spec = self.config['poll']
        path = spec['path'].replace('{task_id}', urllib.parse.quote(task_id_checked(task_id), safe=''))
        response = request_json(self.base_url + path, self.headers())
        try:
            state = spec['states'].get(str(pointer(response, spec['state_pointer'])), 'unknown')
        except (KeyError, IndexError, TypeError):
            state = 'unknown'
        assets = []
        if state == 'success':
            try:
                urls = pointer(response, spec['output_urls_pointer'])
            except (KeyError, IndexError, TypeError):
                urls = []
            if isinstance(urls, str):
                urls = [urls]
            if not isinstance(urls, list) or not all(isinstance(url, str) for url in urls):
                raise ValueError('Output mapping must resolve to a URL string or a list of URL strings.')
            assets = [{'url': url_checked(url), 'extension': spec['output_extension']} for url in urls]
        return {'state': state, 'assets': assets}


class ComfyUIProvider:
    """Optional read-only ComfyUI collector; submission stays in the configured UI/API."""
    kind = 'comfyui'

    def __init__(self, server, name='comfyui'):
        self.name, self.base_url = name, url_checked(server).rstrip('/')
        if urllib.parse.urlsplit(self.base_url).query or urllib.parse.urlsplit(self.base_url).fragment:
            raise ValueError('ComfyUI server URL cannot contain query parameters or fragment.')
        self.identity = {'name': name, 'kind': self.kind, 'endpoint': self.base_url}

    def poll(self, task_id, output_node=None):
        if output_node is None:
            raise ValueError('ComfyUI needs the actual output node ID.')
        history = request_json(self.base_url + '/history/' + urllib.parse.quote(task_id, safe='')).get(task_id)
        if not history:
            queue = request_json(self.base_url + '/queue')
            running = {item[1] for item in queue.get('queue_running', [])}
            pending = {item[1] for item in queue.get('queue_pending', [])}
            return {'state': 'running' if task_id in running else 'pending' if task_id in pending else 'unknown', 'assets': []}
        status = history.get('status', {})
        if status.get('status_str') == 'error':
            return {'state': 'error', 'assets': []}
        assets = []
        if status.get('status_str') == 'success' and status.get('completed'):
            output = history.get('outputs', {}).get(str(output_node), {})
            for kind in ['images', 'videos', 'gifs', 'audio']:
                for asset in output.get(kind, []):
                    if not isinstance(asset, dict):
                        continue
                    suffix = Path(asset.get('filename', '')).suffix.lower()
                    if suffix in MEDIA:
                        query = urllib.parse.urlencode({key: asset.get(key, '') for key in ['filename', 'subfolder', 'type']})
                        item = {'url': self.base_url + '/view?' + query, 'extension': suffix}
                        if item not in assets:
                            assets.append(item)
            return {'state': 'success', 'assets': assets}
        return {'state': 'running', 'assets': []}


def load_provider(config_path=None, server=None):
    if config_path and server:
        raise ValueError('Choose --provider or --server, not both.')
    if server:
        return ComfyUIProvider(server)
    if not config_path:
        raise ValueError('Choose a provider config; --server is available for optional ComfyUI collection.')
    config = json.loads(Path(config_path).read_text(encoding='utf-8'))
    if config['kind'] == 'json-http':
        return JsonHttpProvider(config)
    if config['kind'] == 'comfyui':
        return ComfyUIProvider(config['base_url'], config['name'])
    raise ValueError('Unknown provider kind; use a documented adapter or import generated files.')
