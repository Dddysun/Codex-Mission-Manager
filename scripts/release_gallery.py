#!/usr/bin/env python3
"""Publish only explicitly selected, validated offline PNGs; stdlib only."""
import argparse
import hashlib
import html
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import sys
from urllib.parse import quote
import zlib

ROOT = Path(__file__).resolve().parents[1]
START = '<!-- release-gallery:start -->'
END = '<!-- release-gallery:end -->'
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


class GalleryError(ValueError):
    pass


def read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise GalleryError('Cannot read JSON: %s' % Path(path).name) from exc
    if not isinstance(value, dict):
        raise GalleryError('JSON object required: %s' % Path(path).name)
    return value


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def contained(root, name):
    if not isinstance(name, str) or '\\' in name or ':' in name:
        raise GalleryError('Unsafe input path')
    relative = PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts or not relative.parts:
        raise GalleryError('Unsafe input path: %s' % name)
    root = Path(root).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise GalleryError('Missing file or path escapes input directory: %s' % name)
    return path


def png_dimensions(path):
    if Path(path).stat().st_size > 50 * 1024 * 1024:
        raise GalleryError('PNG exceeds 50 MiB limit')
    data = Path(path).read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise GalleryError('Invalid PNG signature: %s' % Path(path).name)
    offset, dimensions, idat, ended = 8, None, False, False
    while offset + 12 <= len(data):
        size = struct.unpack_from('>I', data, offset)[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + size
        if end > len(data):
            raise GalleryError('Truncated PNG chunk')
        chunk = data[offset + 8:offset + 8 + size]
        checksum = struct.unpack_from('>I', data, offset + 8 + size)[0]
        if zlib.crc32(kind + chunk) & 0xffffffff != checksum:
            raise GalleryError('PNG CRC mismatch')
        if dimensions is None:
            if kind != b'IHDR' or size != 13:
                raise GalleryError('PNG must start with IHDR')
            dimensions = struct.unpack_from('>II', chunk)
            if not all(1 <= value <= 10000 for value in dimensions):
                raise GalleryError('PNG dimensions out of bounds')
        elif kind == b'IHDR':
            raise GalleryError('Duplicate PNG header')
        if kind == b'IDAT':
            idat = True
        if kind == b'IEND':
            if size or end != len(data):
                raise GalleryError('Invalid PNG ending')
            ended = True
            break
        offset = end
    if not dimensions or not idat or not ended:
        raise GalleryError('Incomplete PNG')
    return dimensions


def validate_manifest(path, platform, version, source):
    manifest = read_json(path)
    if manifest.get('version') != version or manifest.get('source_commit') != source:
        raise GalleryError('%s build version/source mismatch' % platform)
    if manifest.get('private_runtime_data_included') is not False or manifest.get('webview') is not False:
        raise GalleryError('%s build privacy/native contract failed' % platform)
    expected = ('arm64', 'SwiftUI-AppKit') if platform == 'macos' else ('x64', 'WPF')
    if (manifest.get('architecture'), manifest.get('ui')) != expected:
        raise GalleryError('%s build architecture/UI mismatch' % platform)
    return {'file': Path(path).name, 'sha256': sha256(path), 'version': version,
            'source_commit': source, 'architecture': expected[0], 'ui': expected[1]}


def validate_receipt(path, platform, image, dimensions, source, version):
    report = read_json(path)
    if report.get('hostStarted') is not False or type(report.get('messagesSent')) is not int or report['messagesSent'] != 0:
        raise GalleryError('Receipt is not an offline no-message render: %s' % path.name)
    for key in ('privatePreferencesLoaded', 'private_data_loaded', 'private_runtime_data_included',
                'systemPowerChanged', 'liveClientConnected'):
        if key in report and report[key] is not False:
            raise GalleryError('Receipt used private/live state: %s' % key)
    for key in ('version', 'source_commit', 'sourceCommit'):
        if key in report and report[key] != (version if key == 'version' else source):
            raise GalleryError('Receipt version/source mismatch')
    if platform == 'macos':
        if report.get('nativeHosting') is not True or type(report.get('webViewCount')) is not int or report['webViewCount'] != 0:
            raise GalleryError('Mac receipt is not native')
        # Current AppKit receipts predate explicit width/view/privacy fields.
        # Only their existing native/no-host/no-message guarantees are claimed.
    else:
        if (report.get('native') is not True or report.get('webView') is not False
                or report.get('privatePreferencesLoaded') is not False or report.get('ui') != 'WPF'):
            raise GalleryError('Windows receipt privacy/native contract failed')
        if (report.get('width'), report.get('height')) != dimensions:
            raise GalleryError('Windows receipt dimensions do not match PNG')
        if report.get('view') != image['view']:
            raise GalleryError('Receipt view does not match selection')
    for key in ('accent', 'language', 'theme'):
        if key in image and (key in report or platform == 'windows') and report.get(key) != image[key]:
            raise GalleryError('Receipt %s does not match selection' % key)
    return {'file': path.name, 'sha256': sha256(path),
            'validation': 'synthetic-native-render; no host started; no messages sent',
            'private_preferences_explicitly_verified': report.get('privatePreferencesLoaded') is False,
            'metadata': {key: report[key] for key in ('nativeHosting', 'webViewCount', 'native', 'ui', 'webView',
                'hostStarted', 'messagesSent', 'privatePreferencesLoaded', 'width', 'height',
                'view', 'accent', 'language', 'theme') if key in report}}


def update_body(notes, fragment):
    if notes.count(START) != notes.count(END) or notes.count(START) > 1:
        raise GalleryError('Malformed or duplicate release-gallery markers')
    if START in notes and notes.index(START) > notes.index(END):
        raise GalleryError('Reversed release-gallery markers')
    block = START + '\n' + fragment.rstrip() + '\n' + END
    if START in notes:
        before, rest = notes.split(START, 1)
        _, after = rest.split(END, 1)
        return before + block + after
    separator = '' if notes.endswith('\n\n') else '\n' if notes.endswith('\n') else '\n\n'
    return notes + separator + block + '\n'


def caption(image):
    value = image.get('caption')
    if not isinstance(value, dict) or not all(isinstance(value.get(k), str) and 0 < len(value[k]) <= 300 for k in ('en', 'zh')):
        raise GalleryError('Each image requires short English and Chinese captions')
    return value['en'], value['zh']


def render_markdown(images):
    lines = ['## Preview gallery / 界面预览', '',
             '**预览版界面 · 示例数据 / Preview UI · Demo data**', '']
    def item(image):
        en, zh = image['caption']['en'], image['caption']['zh']
        label = '%s — %s / %s' % (image['platform_label'], en, zh)
        return '<p><strong>%s</strong></p>\n<p><img src="%s" alt="%s" width="%s"></p>\n' % (
            html.escape(label), html.escape(image['url'], quote=True), html.escape(label, quote=True), image['display_width'])
    for image in images:
        if image['highlight']:
            lines.extend([item(image), ''])
    lines.extend(['<details>', '<summary>Main pages / 常规页面</summary>', ''])
    for image in images:
        if not image['highlight']:
            lines.extend([item(image), ''])
    lines.extend(['</details>', ''])
    return '\n'.join(lines)


def build_gallery(args):
    if not re.fullmatch(r'\d+\.\d+\.\d+', args.version):
        raise GalleryError('A semantic release version is required')
    if not re.fullmatch(r'v' + re.escape(args.version) + r'-preview\.[1-9]\d*', args.tag):
        raise GalleryError('Tag must name this version and an immutable preview number')
    if not re.fullmatch(r'[0-9a-f]{40}', args.source_sha):
        raise GalleryError('A full lowercase source SHA is required')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repository):
        raise GalleryError('Repository must be owner/name')
    if any(part in ('.', '..') for part in args.repository.split('/')):
        raise GalleryError('Invalid repository')
    if args.run_id is not None and not re.fullmatch(r'\d{1,30}', args.run_id):
        raise GalleryError('Run ID must be numeric')
    configuration = read_json(args.config)
    selection = configuration.get('versions', {}).get(args.version)
    if not isinstance(selection, dict) or not isinstance(selection.get('images'), list):
        raise GalleryError('Explicit gallery configuration is required for version ' + args.version)
    specs = selection['images']
    if {s.get('platform') for s in specs} != {'macos', 'windows'} or len({s.get('kind') for s in specs}) < 4:
        raise GalleryError('Gallery must cover both platforms and at least four page kinds')
    if not any(s.get('kind') == 'home' for s in specs) or not any(s.get('highlight') is True for s in specs):
        raise GalleryError('Gallery needs main pages and explicit release highlights')
    manifests = {p: validate_manifest(getattr(args, p + '_manifest'), p, args.version, args.source_sha)
                 for p in ('macos', 'windows')}
    images, payloads, seen = [], [], set()
    for spec in specs:
        platform = spec.get('platform')
        identity = spec.get('id', '')
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', identity) or (platform, identity) in seen:
            raise GalleryError('Invalid or duplicate gallery image ID')
        if type(spec.get('highlight')) is not bool:
            raise GalleryError('Every image needs an explicit highlight boolean')
        seen.add((platform, identity))
        caption(spec)
        root = getattr(args, platform + '_dir')
        source = contained(root, spec['file'])
        receipt = contained(root, spec['receipt'])
        dimensions = png_dimensions(source)
        if list(dimensions) not in spec.get('dimensions', []):
            raise GalleryError('Unexpected PNG dimensions: %s' % spec['file'])
        checked = validate_receipt(receipt, platform, spec, dimensions, args.source_sha, args.version)
        name = 'gallery-%s-%s-%s.png' % (args.version, platform, identity)
        url = 'https://github.com/%s/releases/download/%s/%s' % (args.repository, quote(args.tag, safe=''), quote(name, safe=''))
        images.append({'id': identity, 'platform': platform, 'platform_label': 'macOS' if platform == 'macos' else 'Windows',
            'kind': spec['kind'], 'highlight': spec['highlight'], 'caption': spec['caption'],
            'source_file': spec['file'], 'file': name, 'url': url, 'width': dimensions[0], 'height': dimensions[1],
            'display_width': min(400 if spec['kind'] in ('menu', 'tray') else 900, dimensions[0]),
            'sha256': sha256(source), 'receipt': checked})
        payloads.append((source, name))
    result = {'schema_version': 1, 'version': args.version, 'tag': args.tag, 'source_commit': args.source_sha,
        'repository': args.repository, 'run_id': args.run_id, 'checksums_file': 'GALLERY_SHA256SUMS',
        'preview': True, 'demo_data': True, 'live_client_acceptance': False,
        'source_binding': 'Build manifests verify version/source; receipts verify offline rendering. '
                          'Legacy receipts do not cryptographically bind individual PNGs to a commit.',
        'artifacts': {p: getattr(args, p + '_artifact') or 'offline-validation-artifact (identifier not supplied)'
                      for p in ('macos', 'windows')}, 'build_manifests': manifests, 'images': images}
    fragment = render_markdown(images)
    notes_path = Path(args.notes) if args.notes else ROOT / 'docs/releases' / (args.version + '.md')
    # read_text() applies universal-newline translation. Release backfills must
    # preserve every byte outside the controlled gallery markers, including CRLF.
    body = update_body(notes_path.read_bytes().decode('utf-8'), fragment)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    generated = {'release-gallery.json': (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode(),
                 'release-gallery.md': fragment.encode(), 'release-body.md': body.encode()}
    sums = {image['file']: image['sha256'] for image in images}
    sums['release-gallery.json'] = hashlib.sha256(generated['release-gallery.json']).hexdigest()
    generated['GALLERY_SHA256SUMS'] = ''.join(sums[name] + '  ' + name + '\n' for name in sorted(sums)).encode()
    # Validate all inputs before writing, and never replace a different PNG.
    for source, name in payloads:
        target = output / name
        if target.is_symlink() or (target.exists() and target.read_bytes() != source.read_bytes()):
            raise GalleryError('Refusing to overwrite a different gallery image: ' + name)
    for name in generated:
        if (output / name).is_symlink():
            raise GalleryError('Refusing output symlink: ' + name)
    for source, name in payloads:
        if not (output / name).exists():
            shutil.copyfile(source, output / name)
    for name, content in generated.items():
        (output / name).write_bytes(content)
    return result


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--version', required=True)
    result.add_argument('--tag', required=True)
    result.add_argument('--source-sha', required=True)
    result.add_argument('--repository', default='Dddysun/Codex-Mission-Manager')
    result.add_argument('--config', type=Path, default=ROOT / 'docs/release-gallery.json')
    result.add_argument('--macos-dir', type=Path, required=True)
    result.add_argument('--windows-dir', type=Path, required=True)
    result.add_argument('--macos-manifest', type=Path, required=True)
    result.add_argument('--windows-manifest', type=Path, required=True)
    result.add_argument('--output-dir', type=Path, required=True)
    result.add_argument('--notes', type=Path)
    result.add_argument('--run-id')
    result.add_argument('--macos-artifact')
    result.add_argument('--windows-artifact')
    return result


def main(argv=None):
    try:
        result = build_gallery(parser().parse_args(argv))
    except (GalleryError, OSError, KeyError, TypeError) as exc:
        print('Release gallery rejected: %s' % exc, file=sys.stderr)
        return 1
    print('Gallery ready: %s, %s validated demo images' % (result['tag'], len(result['images'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
