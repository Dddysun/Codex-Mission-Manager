"""Versioned desktop compatibility policy shared with every UI surface."""
import plistlib
from pathlib import Path

# A profile is added only after read-only live protocol and framed control
# regressions. This is not a promise about future client builds.
PROFILES = {
    '20770': {'snapshot': 11, 'start_turn': 2, 'interrupt_turn': 4},
    '21828': {'snapshot': 11, 'start_turn': 2, 'interrupt_turn': 4},
}
APP_INFO = Path('/Applications/ChatGPT.app/Contents/Info.plist')

def desktop_compatibility(path=None):
    try:
        info = plistlib.loads(Path(path or APP_INFO).read_bytes())
        build = str(info.get('CFBundleVersion', ''))
        return {'build': build, 'version': info.get('CFBundleShortVersionString'),
                'supported': build in PROFILES, 'status': 'supported' if build in PROFILES else 'update_required',
                'profile': PROFILES.get(build), 'live_control_tested': build == '20770'}
    except (OSError, ValueError, plistlib.InvalidFileException):
        return {'build': None, 'version': None, 'supported': False, 'status': 'client_missing', 'profile': None, 'live_control_tested': False}

def require_supported():
    result = desktop_compatibility()
    if not result['supported']:
        raise RuntimeError('Desktop client compatibility requires an application update (build %s)' % (result['build'] or 'unknown'))
    return result
