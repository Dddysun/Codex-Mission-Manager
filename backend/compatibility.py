"""Versioned desktop compatibility policy shared with every UI surface."""
import json
import hashlib
import os
import plistlib
from pathlib import Path
import re
import subprocess
import time

# A profile is added only after read-only live protocol and framed control
# regressions. This is not a promise about future client builds.
PROFILES = {
    '20770': {'snapshot': 11, 'start_turn': 2, 'interrupt_turn': 4},
    '21828': {'snapshot': 11, 'start_turn': 2, 'interrupt_turn': 4},
}
APP_INFO = Path('/Applications/ChatGPT.app/Contents/Info.plist')
# Windows versions are deliberately separate from the macOS build numbers.
# Entries require a read-only handshake on that exact Windows package first.
WINDOWS_PROFILES = {
    # Exact signed package: live read-only snapshots + Windows framed
    # regressions and matching package schemas verified on 2026-10-26.
    # This is version compatibility, not a live pause/resume acceptance claim.
    '26.1021.3705.0': {'snapshot': 11, 'start_turn': 2, 'interrupt_turn': 4},
}
WINDOWS_PUBLISHER = 'CN=50BDFD77-8903-4850-9FFE-6E8522F64D5B'
_windows_cache = None


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verified_windows_cli(package_root, cache_root=None):
    """Locate only package bytes or an exact same-byte client-extracted copy.

    Appx identity/publisher validation belongs to windows_client. Cache names,
    timestamps, and a previous successful lookup never replace this hash check.
    """
    root = Path(package_root).resolve()
    bundled = None
    for relative in ('app/resources/codex.exe','resources/codex.exe',
                     'app/resources/bin/codex.exe','app/resources/codex-cli/codex.exe'):
        candidate = root/relative
        try:
            actual = candidate.resolve(strict=True)
            if actual.is_relative_to(root) and actual.is_file():
                bundled = actual
                break
        except OSError:
            continue
    if bundled is None:
        return None
    try:
        expected = _sha256_file(bundled)
        expected_size = bundled.stat().st_size
    except OSError:
        return None  # An unreadable package cannot authenticate a user-cache file.
    result = {'cli':str(bundled),'bundled_cli':str(bundled),
              'cli_sha256':expected,'cli_source':'registered-package'}
    if cache_root is None:
        local = Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local')).resolve()
        cache_root = local/'OpenAI/Codex/bin'
    cache = Path(cache_root)
    try:
        if cache.is_symlink() or (hasattr(cache,'is_junction') and cache.is_junction()):
            return result
        actual_cache = cache.resolve(strict=True)
        if actual_cache != Path(os.path.abspath(cache)):
            return result
        cache = actual_cache
        # Only direct version/hash directories are eligible; no recursive PATH
        # search and no cache directory or executable junction escape.
        children = sorted(cache.iterdir(),key=lambda path:path.name,reverse=True)
        if len(children) > 128:
            return result
        for directory in children:
            if not re.fullmatch(r'[0-9a-fA-F]{16,64}',directory.name):
                continue
            try:
                actual_directory = directory.resolve(strict=True)
                if actual_directory.parent != cache or actual_directory != directory:
                    continue
                candidate = directory/'codex.exe'
                actual = candidate.resolve(strict=True)
                if (actual != candidate or actual.parent != actual_directory or not actual.is_file()
                        or actual.stat().st_size != expected_size):
                    continue
                if _sha256_file(actual) == expected:
                    return dict(result,cli=str(actual),cli_source='client-cache-sha256-match')
            except OSError:
                continue
    except OSError:
        pass
    return result


def _windows_client_with_cli(info, verify_cli):
    if not info:
        return None
    result = dict(info)
    if verify_cli:
        selected = verified_windows_cli(result['install_location'])
        result.update(selected or {'cli':None,'bundled_cli':None,'cli_sha256':None,'cli_source':'unavailable'})
    return result


def windows_client(force=False, verify_cli=True):
    """Discover a per-user Store package without reading authentication data."""
    global _windows_cache
    if not force and _windows_cache and time.monotonic()-_windows_cache[0] < 15:
        # The cache is metadata-only. Any caller selecting an executable gets
        # a new package/cache byte comparison, even inside this metadata TTL.
        return _windows_client_with_cli(_windows_cache[1],verify_cli)
    command = ("$ProgressPreference='SilentlyContinue'; [Console]::OutputEncoding="
               "(New-Object System.Text.UTF8Encoding($false)); "
               "Get-AppxPackage -Name OpenAI.Codex | Sort-Object Version -Descending | "
               "Select-Object -First 1 Name,Version,InstallLocation,PackageFamilyName,Publisher | ConvertTo-Json -Compress")
    try:
        run = subprocess.run(['powershell.exe','-NoLogo','-NoProfile','-NonInteractive','-Command',command],
            capture_output=True, timeout=12, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        info = json.loads(run.stdout.decode('utf-8-sig')) if run.returncode == 0 and run.stdout.strip() else None
        if (not isinstance(info, dict) or info.get('Name') != 'OpenAI.Codex'
                or info.get('Publisher') != WINDOWS_PUBLISHER):
            info = None
        if info:
            root = Path(info.get('InstallLocation') or '')
            if not root.is_absolute() or not root.is_dir():
                info = None
            else:
                info = {'name':info['Name'],'version':str(info.get('Version') or ''),
                        'install_location':str(root),
                        'package_family':info.get('PackageFamilyName'),'publisher':info.get('Publisher')}
    except (OSError, ValueError, subprocess.SubprocessError):
        info = None
    _windows_cache = (time.monotonic(), info)
    return _windows_client_with_cli(info,verify_cli)


def windows_compatibility(info):
    version = str((info or {}).get('version') or '')
    profile = WINDOWS_PROFILES.get(version)
    return {'platform':'windows','build':version or None,'version':version or None,
            'supported':bool(profile),'status':'supported' if profile else 'update_required' if info else 'client_missing',
            'profile':profile,'live_control_tested':False}

def desktop_compatibility(path=None):
    if os.name == 'nt' and path is None:
        return windows_compatibility(windows_client(verify_cli=False))
    try:
        info = plistlib.loads(Path(path or APP_INFO).read_bytes())
        build = str(info.get('CFBundleVersion', ''))
        return {'build': build, 'version': info.get('CFBundleShortVersionString'),
                'supported': build in PROFILES, 'status': 'supported' if build in PROFILES else 'update_required',
                'profile': PROFILES.get(build), 'live_control_tested': build == '20770'}
    except (OSError, ValueError, plistlib.InvalidFileException):
        return {'build': None, 'version': None, 'supported': False, 'status': 'client_missing', 'profile': None, 'live_control_tested': False}

def require_supported():
    result = windows_compatibility(windows_client(force=True,verify_cli=False)) if os.name == 'nt' else desktop_compatibility()
    if not result['supported']:
        raise RuntimeError('Desktop client compatibility requires an application update (build %s)' % (result['build'] or 'unknown'))
    return result
