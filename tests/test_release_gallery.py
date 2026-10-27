"""Gallery publishing uses generated PNGs and public offline receipt fixtures."""
import copy
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import urlsplit
import zlib

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release_gallery', ROOT / 'scripts/release_gallery.py')
gallery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gallery)


def write_png(path, width=20, height=30):
    def chunk(kind, content):
        return struct.pack('>I', len(content)) + kind + content + struct.pack('>I', zlib.crc32(kind + content) & 0xffffffff)
    header = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    path.write_bytes(gallery.PNG_SIGNATURE + chunk(b'IHDR', header) +
        chunk(b'IDAT', zlib.compress((b'\0' + b'\0' * width * 3) * height)) + chunk(b'IEND', b''))


class ReleaseGalleryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = gallery.read_json(ROOT / 'docs/release-gallery.json')
        self.images = self.config['versions']['0.3.1']['images']
        self.source = 'a' * 40
        self.dirs = {}
        for platform in ('macos', 'windows'):
            directory = self.root / platform
            directory.mkdir()
            self.dirs[platform] = directory
            manifest = {'version': '0.3.1', 'source_commit': self.source,
                'architecture': 'arm64' if platform == 'macos' else 'x64',
                'ui': 'SwiftUI-AppKit' if platform == 'macos' else 'WPF',
                'webview': False, 'private_runtime_data_included': False}
            (self.root / (platform + '-manifest.json')).write_text(json.dumps(manifest))
        for image in self.images:
            image['dimensions'] = [[20, 30]]
            directory = self.dirs[image['platform']]
            write_png(directory / image['file'])
            receipt = {'hostStarted': False, 'messagesSent': 0, 'accent': image['accent']}
            if image['platform'] == 'macos':
                receipt.update(nativeHosting=True, webViewCount=0)
            else:
                receipt.update(native=True, ui='WPF', webView=False, privatePreferencesLoaded=False,
                    width=20, height=30, view=image['view'], language=image['language'], theme=image['theme'])
            (directory / image['receipt']).write_text(json.dumps(receipt))
        self.config_path = self.root / 'gallery-config.json'
        self.notes = self.root / 'notes.md'
        self.notes.write_text('# Existing public release\n\nKeep this paragraph.  \n\n')
        self.output = self.root / 'release-assets'
        self.output.mkdir()
        (self.output / 'installer.exe').write_bytes(b'preserve existing installer')
        (self.output / 'SHA256SUMS').write_bytes(b'preserve original checksum list')
        self.arguments = ['--version', '0.3.1', '--tag', 'v0.3.1-preview.2', '--source-sha', self.source,
            '--config', str(self.config_path), '--macos-dir', str(self.dirs['macos']),
            '--windows-dir', str(self.dirs['windows']), '--macos-manifest', str(self.root / 'macos-manifest.json'),
            '--windows-manifest', str(self.root / 'windows-manifest.json'), '--output-dir', str(self.output),
            '--notes', str(self.notes), '--run-id', '40467782526', '--macos-artifact', 'macos-ui',
            '--windows-artifact', 'windows-ui']

    def run_gallery(self):
        self.config_path.write_text(json.dumps(self.config))
        return gallery.build_gallery(gallery.parser().parse_args(self.arguments))

    def receipt(self, image):
        path = self.dirs[image['platform']] / image['receipt']
        return path, gallery.read_json(path)

    def test_six_images_four_kinds_highlights_and_absolute_asset_urls(self):
        result = self.run_gallery()
        self.assertEqual(len(result['images']), 6)
        self.assertEqual({image['platform'] for image in result['images']}, {'macos', 'windows'})
        self.assertEqual(len({image['kind'] for image in result['images']}), 4)
        self.assertEqual([image['id'] for image in result['images'] if image['highlight']], ['quit-menu', 'quit-tray'])
        fragment = (self.output / 'release-gallery.md').read_text()
        self.assertIn('预览版界面 · 示例数据 / Preview UI · Demo data', fragment)
        self.assertEqual(fragment.count('<img '), 6)
        self.assertEqual(fragment.split('<details>')[0].count('<img '), 2)
        for image in result['images']:
            parsed = urlsplit(image['url'])
            self.assertEqual((parsed.scheme, parsed.netloc), ('https', 'github.com'))
            self.assertIn('/releases/download/v0.3.1-preview.2/', parsed.path)
            self.assertLessEqual(image['display_width'], image['width'])
            self.assertLessEqual(image['display_width'], 400 if image['kind'] == 'menu' else 900)
            self.assertEqual((self.output / image['file']).read_bytes(),
                             (self.dirs[image['platform']] / image['source_file']).read_bytes())
        self.assertEqual(result['run_id'], '40467782526')
        self.assertFalse(result['live_client_acceptance'])

    def test_display_width_caps_menu_at_400_and_main_page_at_900(self):
        for kind, width in (('menu', 500), ('home', 1000)):
            image = next(image for image in self.images if image['kind'] == kind)
            image['dimensions'] = [[width, 30]]
            write_png(self.dirs[image['platform']] / image['file'], width, 30)
        result = self.run_gallery()
        self.assertEqual(next(i for i in result['images'] if i['kind'] == 'menu')['display_width'], 400)
        self.assertEqual(next(i for i in result['images'] if i['kind'] == 'home')['display_width'], 900)
        fragment = (self.output / 'release-gallery.md').read_text()
        self.assertIn('width="400"', fragment)
        self.assertIn('width="900"', fragment)

    def test_body_update_is_idempotent_and_preserves_unrelated_text_and_assets(self):
        original = self.notes.read_text()
        self.run_gallery()
        first = (self.output / 'release-body.md').read_text()
        self.assertTrue(first.startswith(original))
        self.assertEqual(first.count(gallery.START), 1)
        self.notes.write_text(first)
        self.run_gallery()
        self.assertEqual(first, (self.output / 'release-body.md').read_text())
        self.assertEqual((self.output / 'SHA256SUMS').read_bytes(), b'preserve original checksum list')
        self.assertEqual((self.output / 'installer.exe').read_bytes(), b'preserve existing installer')
        for line in (self.output / 'GALLERY_SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ')
            self.assertEqual(gallery.sha256(self.output / name), digest)

    def test_crlf_body_and_marker_surroundings_remain_byte_exact(self):
        original = b'# Existing release\r\n\r\nKeep trailing spaces.  \r\n\r\n'
        self.notes.write_bytes(original)
        self.run_gallery()
        body = (self.output / 'release-body.md').read_bytes()
        self.assertTrue(body.startswith(original))
        self.notes.write_bytes(body)
        self.run_gallery()
        self.assertEqual((self.output / 'release-body.md').read_bytes(), body)
        before = b'# Existing release\r\n\r\nBefore marker.  \r\n'
        after = b'\r\n\r\nAfter marker.  \r\n\r\n'
        self.notes.write_bytes(before + gallery.START.encode() + b'\r\nOld gallery\r\n' + gallery.END.encode() + after)
        self.run_gallery()
        replaced = (self.output / 'release-body.md').read_bytes()
        self.assertEqual(replaced.split(gallery.START.encode(), 1)[0], before)
        self.assertEqual(replaced.split(gallery.END.encode(), 1)[1], after)
        self.notes.write_bytes(replaced)
        self.run_gallery()
        self.assertEqual((self.output / 'release-body.md').read_bytes(), replaced)

    def test_missing_image_or_receipt_fails_before_any_gallery_write(self):
        for key in ('file', 'receipt'):
            with self.subTest(key=key):
                image = self.images[0]
                path = self.dirs[image['platform']] / image[key]
                contents = path.read_bytes(); path.unlink()
                try:
                    with self.assertRaises(gallery.GalleryError): self.run_gallery()
                    self.assertEqual(list(self.output.glob('gallery-*')), [])
                finally:
                    path.write_bytes(contents)

    def test_private_or_live_receipts_are_rejected_and_secrets_not_exported(self):
        for platform in ('macos', 'windows'):
            image = next(image for image in self.images if image['platform'] == platform)
            path, original = self.receipt(image)
            for field, value in (('hostStarted', True), ('messagesSent', 1), ('privatePreferencesLoaded', True)):
                path.write_text(json.dumps(dict(original, **{field: value})))
                with self.subTest(platform=platform, field=field), self.assertRaises(gallery.GalleryError):
                    self.run_gallery()
            path.write_text(json.dumps(dict(original, accessToken='must not appear')))
        self.run_gallery()
        self.assertNotIn('accessToken', (self.output / 'release-gallery.json').read_text())

    def test_paths_cannot_escape_roots_and_output_symlinks_are_rejected(self):
        image = self.images[0]; original = image['file']
        for value in ('../outside.png', '/absolute.png', 'C:\\private.png'):
            image['file'] = value
            with self.subTest(value=value), self.assertRaises(gallery.GalleryError): self.run_gallery()
        image['file'] = original
        outside = self.root / 'outside.png'; write_png(outside)
        escaped = self.dirs['macos'] / 'escape.png'
        try:
            escaped.symlink_to(outside)
        except OSError:
            self.skipTest('Symlinks require platform permission')
        image['file'] = escaped.name
        with self.assertRaises(gallery.GalleryError): self.run_gallery()
        image['file'] = original
        target = self.output / 'release-gallery.json'; target.symlink_to(self.notes)
        with self.assertRaises(gallery.GalleryError): self.run_gallery()

    def test_version_source_manifest_and_unconfigured_future_version_fail(self):
        for field, value in (('version', '0.3.0'), ('source_commit', 'b' * 40), ('private_runtime_data_included', True)):
            path = self.root / 'windows-manifest.json'; original = gallery.read_json(path)
            path.write_text(json.dumps(dict(original, **{field: value})))
            with self.subTest(field=field), self.assertRaises(gallery.GalleryError): self.run_gallery()
            path.write_text(json.dumps(original))
        self.arguments[self.arguments.index('--version') + 1] = '0.3.2'
        self.arguments[self.arguments.index('--tag') + 1] = 'v0.3.2-preview.1'
        self.config['versions'].pop('0.3.2', None)
        with self.assertRaisesRegex(gallery.GalleryError, 'Explicit gallery configuration'): self.run_gallery()

    def test_png_signature_crc_dimensions_and_receipt_dimensions_are_checked(self):
        image = self.images[0]; path = self.dirs[image['platform']] / image['file']
        original = path.read_bytes()
        for invalid in (b'not PNG', original[:-1], original[:28] + bytes([original[28] ^ 1]) + original[29:]):
            path.write_bytes(invalid)
            with self.assertRaises(gallery.GalleryError): self.run_gallery()
        write_png(path, 21, 30)
        with self.assertRaisesRegex(gallery.GalleryError, 'dimensions'): self.run_gallery()
        path.write_bytes(original)
        image = next(image for image in self.images if image['platform'] == 'windows')
        receipt, value = self.receipt(image); value['width'] = 21; receipt.write_text(json.dumps(value))
        with self.assertRaisesRegex(gallery.GalleryError, 'dimensions'): self.run_gallery()

    def test_different_png_cannot_overwrite_a_gallery_asset(self):
        result = self.run_gallery()
        image = result['images'][0]
        write_png(self.dirs[image['platform']] / image['source_file'])
        # A different valid PNG with the same dimensions must not replace it.
        (self.output / image['file']).write_bytes(b'already published different bytes')
        with self.assertRaisesRegex(gallery.GalleryError, 'overwrite'): self.run_gallery()

    def test_malformed_markers_and_wrong_release_tag_are_rejected(self):
        for body in (gallery.START, gallery.END + gallery.START,
                     gallery.START + gallery.END + gallery.START + gallery.END):
            with self.subTest(body=body), self.assertRaises(gallery.GalleryError): gallery.update_body(body, 'new')
        self.arguments[self.arguments.index('--tag') + 1] = 'v0.3.0-preview.2'
        with self.assertRaises(gallery.GalleryError): self.run_gallery()

    def test_isolated_cli_succeeds_and_missing_inputs_return_failure(self):
        self.config_path.write_text(json.dumps(self.config))
        command = [sys.executable, '-I', str(ROOT / 'scripts/release_gallery.py')] + self.arguments
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('6 validated demo images', result.stdout)
        image = self.images[0]
        (self.dirs[image['platform']] / image['receipt']).unlink()
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Release gallery rejected', result.stderr)


if __name__ == '__main__':
    unittest.main()
