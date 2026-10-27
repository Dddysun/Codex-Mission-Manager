"""Run isolated platform regressions with an explicit machine-readable result."""
import argparse
import io
import json
from pathlib import Path
import shutil
import sys
import unittest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--scope', choices=('smoke', 'full'), default='full',
                        help='Smoke runs packaging-host and Windows platform checks only.')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root/'backend'))
    # These tests require a disposable source-tree sample, never a user's file.
    config = root/'backend/config.json'
    created = not config.exists()
    if created:
        shutil.copyfile(root/'backend/config.example.json', config)
    results = {}
    try:
        selections = [('backend', root/'backend/tests',
                       'test_windows_platform.py' if args.scope == 'smoke' else 'test_*.py'),
                      ('host', root/'tests', 'test_*.py')]
        for name, directory, pattern in selections:
            stream = io.StringIO()
            suite = unittest.TestLoader().discover(str(directory), pattern=pattern)
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
            (output/(name+'-tests.log')).write_text(stream.getvalue(), encoding='utf-8')
            results[name] = {
                'tests_run': result.testsRun, 'failures': len(result.failures),
                'errors': len(result.errors), 'skipped': len(result.skipped),
                'successful': result.wasSuccessful(),
                'selection': pattern,
                'skipped_cases': [{'test': str(test), 'reason': reason} for test, reason in result.skipped],
                'failure_details': [{'test': str(test), 'traceback': detail}
                                    for test, detail in result.failures+result.errors],
            }
        public = {'platform': sys.platform, 'python': sys.version.split()[0],
                  'environment': 'isolated test fixtures', 'live_chat_messages_sent': 0,
                  'scope': args.scope, 'full_backend_suite_run': args.scope == 'full',
                  'results': results}
        (output/'windows-test-results.json').write_text(
            json.dumps(public, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps({name: {key:value for key,value in result.items()
                                 if key not in ('skipped_cases','failure_details')}
                          for name,result in results.items()}, ensure_ascii=False, indent=2))
        return 0 if all(result['successful'] for result in results.values()) else 1
    finally:
        if created:
            config.unlink()


if __name__ == '__main__':
    raise SystemExit(main())
