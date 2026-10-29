#!/usr/bin/env python3
"""Build an isolated native-view recorder, without installing or launching TokenMax."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path)
    args = parser.parse_args()
    output = args.build or Path(tempfile.mkdtemp(prefix='tokenmax-media-'))
    output.mkdir(parents=True, exist_ok=True)
    app = (ROOT/'native/App.swift').read_text()
    app = app.replace('@main enum MissionMain', 'enum MissionMain', 1)
    for signature in ('func start() {', 'func startHost() {'):
        app = app.replace(signature, signature + '\n        preconditionFailure("The media recorder cannot start a backend")', 1)
    (output/'App.swift').write_text(app)
    logo = (ROOT/'native/JuicerLogo.swift').read_text()
    logo = logo.replace('    @StateObject private var motion=JuicerMotionSession()',
                        '    @StateObject private var motion=JuicerMotionSession()\n    @ObservedObject private var recordingClock=RecordingClock.shared')
    logo = logo.replace('timeline.date.timeIntervalSinceReferenceDate', 'recordingClock.seconds')
    (output/'JuicerLogo.swift').write_text(logo)
    views = (ROOT/'native/NativeViews.swift').read_text()
    views = views.replace('Date().timeIntervalSince1970 - observed', 'RecordingClock.shared.epoch - observed')
    views = views.replace('initialSection: String = "tasks") {',
                          'initialSection: String = "tasks", initialActivityFilter: MissionActivityFilter = .all) {')
    views = views.replace('_section=State(initialValue:', '_activityFilter=State(initialValue:initialActivityFilter)\n        _section=State(initialValue:', 1)
    views = views.replace('initialSection == "events" ? "events" : "tasks"', '["tasks","events","rules"].contains(initialSection) ? initialSection : "tasks"')
    views = views.replace('@State private var expanded = false', '@State private var expanded = RecordingClock.shared.detailsExpanded')
    (output/'NativeViews.swift').write_text(views)
    sdk = subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip()
    native = ROOT/'native'
    (output/'Shared.swift').write_text((native/'Shared.swift').read_text().replace('__TEAM_ID__', '', 1))
    sources = [output/'Shared.swift', native/'Localization.swift', native/'NativeState.swift',
               native/'JuicerMotionData.swift', native/'JuicerMotion.swift', output/'JuicerLogo.swift',
               output/'NativeViews.swift', native/'NativeSettings.swift', native/'MenuPanel.swift',
               native/'JuicerPreview.swift', output/'App.swift', HERE/'Recorder.swift']
    executable = output/'TokenMaxMediaRecorder'
    subprocess.run(['swiftc', '-swift-version', '5', '-O', '-parse-as-library',
                    '-target', 'arm64-apple-macos14.0', '-sdk', sdk,
                    '-module-cache-path', str(output/'module-cache'), *map(str, sources),
                    '-o', str(executable)], check=True)
    print(json.dumps({'executable': str(executable), 'native_views': True, 'production_app_modified': False}))


if __name__ == '__main__':
    main()
