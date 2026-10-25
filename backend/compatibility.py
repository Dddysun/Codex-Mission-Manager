"""Versioned desktop compatibility policy shared with every UI surface."""
import json
import os
import plistlib
from pathlib import Path
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
WINDOWS_PROFILES = {}
WINDOWS_PUBLISHER = 'CN=50BDFD77-8903-4850-9FFE-6E8522F64D5B'
_windows_cache = None


def windows_client(force=False):
    """Discover a per-user Store package without reading authentication data."""
    global _windows_cache
    if not force and _windows_cache and time.monotonic()-_windows_cache[0] < 15:
        return dict(_windows_cache[1]) if _windows_cache[1] else None
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
                cli = next((p for relative in ('app/resources/codex.exe','resources/codex.exe',
                    'app/resources/bin/codex.exe','app/resources/codex-cli/codex.exe')
                    if (p := root/relative).is_file()), None)
                if cli is None:
                    cli = next((p for p in root.rglob('codex*.exe')
                        if 'resources' in [part.lower() for part in p.relative_to(root).parts[:-1]]), None)
                info = {'name':info['Name'],'version':str(info.get('Version') or ''),
                        'install_location':str(root),'cli':str(cli) if cli else None,
                        'package_family':info.get('PackageFamilyName'),'publisher':info.get('Publisher')}
    except (OSError, ValueError, subprocess.SubprocessError):
        info = None
    _windows_cache = (time.monotonic(), info)
    return dict(info) if info else None


def windows_compatibility(info):
    version = str((info or {}).get('version') or '')
    profile = WINDOWS_PROFILES.get(version)
    return {'platform':'windows','build':version or None,'version':version or None,
            'supported':bool(profile),'status':'supported' if profile else 'update_required' if info else 'client_missing',
            'profile':profile,'live_control_tested':False}

def desktop_compatibility(path=None):
    if os.name == 'nt' and path is None:
        return windows_compatibility(windows_client())
    try:
        info = plistlib.loads(Path(path or APP_INFO).read_bytes())
        build = str(info.get('CFBundleVersion', ''))
        return {'build': build, 'version': info.get('CFBundleShortVersionString'),
                'supported': build in PROFILES, 'status': 'supported' if build in PROFILES else 'update_required',
                'profile': PROFILES.get(build), 'live_control_tested': build == '20770'}
    except (OSError, ValueError, plistlib.InvalidFileException):
        return {'build': None, 'version': None, 'supported': False, 'status': 'client_missing', 'profile': None, 'live_control_tested': False}

def require_supported():
    result = windows_compatibility(windows_client(force=True)) if os.name == 'nt' else desktop_compatibility()
    if not result['supported']:
        raise RuntimeError('Desktop client compatibility requires an application update (build %s)' % (result['build'] or 'unknown'))
    return result
