#!/usr/bin/env python3
"""Finalize and verify the synthetic native-UI recordings with FFmpeg."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def run(*args, capture=False):
    return subprocess.run(list(map(str, args)), check=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def inspect(path, width, height, duration, ffmpeg, ffprobe):
    info = json.loads(run(ffprobe, '-v', 'error', '-show_streams', '-show_format',
                          '-of', 'json', path, capture=True))
    streams = info['streams']
    assert len(streams) == 1 and streams[0]['codec_type'] == 'video', path
    video = streams[0]
    assert (video['width'], video['height']) == (width, height), path
    assert video['codec_name'] == 'h264' and video['pix_fmt'] == 'yuv420p', path
    assert video['avg_frame_rate'] == '30/1', path
    assert abs(float(info['format']['duration']) - duration) < 0.04, path
    assert int(video['nb_frames']) == round(duration * 30), path
    # Decode every frame, rather than accepting only container metadata.
    run(ffmpeg, '-nostdin', '-v', 'error', '-xerror', '-i', path, '-map', '0:v:0',
        '-f', 'null', '-')
    return {'file': path.name, 'width': width, 'height': height, 'fps': 30,
            'duration_seconds': duration, 'codec': 'h264', 'pixel_format': 'yuv420p',
            'audio_tracks': 0, 'frames': int(video['nb_frames']),
            'full_decode_passed': True, 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--ffmpeg', default=shutil.which('ffmpeg'))
    parser.add_argument('--ffprobe', default=shutil.which('ffprobe'))
    args = parser.parse_args()
    if not args.ffmpeg or not args.ffprobe:
        parser.error('FFmpeg and ffprobe must be installed or supplied explicitly')
    plan = json.loads(args.plan.read_text())
    assert plan['simulation'] and plan['schema'] == 1
    output = args.output.resolve()
    scenes = plan['scenes']
    assert scenes and all(s['key'].startswith('%02d_' % (i+1)) for i,s in enumerate(scenes))
    preview_seconds = len(scenes)*4
    preview = output/('00_按台本顺序预览_%d秒.mp4' % preview_seconds)
    full = output/'00_按台本顺序完整串联.mp4'
    if preview.exists():
        parser.error('Preview already exists; use a new output folder')
    if full.exists():
        parser.error('Full sequence already exists; use a new output folder')
    jobs = []
    for folder, width, height in [('01_竖屏_1080x1920', 1080, 1920),
                                  ('02_横屏原始_2560x1600', 2560, 1600)]:
        for scene in scenes:
            key = scene['key']
            assert Path(key).name == key and '/' not in key and '\\' not in key
            path = output/folder/(key+'.mp4')
            assert path.is_file(), path
            jobs.append((path, width, height, scene['duration']))
    with tempfile.TemporaryDirectory(prefix='.finalizing-', dir=output) as temp:
        temporary = Path(temp)
        for path, _, _, _ in jobs:
            ready = temporary/path.name
            run(args.ffmpeg, '-nostdin', '-v', 'error', '-i', path, '-map', '0:v:0',
                '-c', 'copy', '-movflags', '+faststart', ready)
            ready.replace(path)
        # Four seconds per shot. The chosen in-points retain each key transition.
        starts = [1,1,3,3,1,3,3,4,6,8,2,2,3,1,7,3,3,4,4]
        assert len(starts) == len(scenes)
        parts = []
        for index, (scene, start) in enumerate(zip(scenes, starts)):
            source = output/'01_竖屏_1080x1920'/(scene['key']+'.mp4')
            part = temporary/('%02d.mp4' % index)
            run(args.ffmpeg, '-nostdin', '-v', 'error', '-ss', start, '-i', source,
                '-t', 4, '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', 18,
                '-pix_fmt', 'yuv420p', '-r', 30, '-threads', 2, part)
            parts.append(part.name)
        concat = temporary/'concat.txt'
        concat.write_text(''.join("file '%s'\n" % name for name in parts))
        run(args.ffmpeg, '-nostdin', '-v', 'error', '-f', 'concat', '-safe', 1,
            '-i', concat, '-c', 'copy', '-movflags', '+faststart', preview)
        complete = []
        for index, scene in enumerate(scenes):
            link = temporary/('full-%02d.mp4' % index)
            link.symlink_to(output/'01_竖屏_1080x1920'/(scene['key']+'.mp4'))
            complete.append(link.name)
        concat.write_text(''.join("file '%s'\n" % name for name in complete))
        run(args.ffmpeg, '-nostdin', '-v', 'error', '-f', 'concat', '-safe', 1,
            '-i', concat, '-c', 'copy', '-movflags', '+faststart', full)
    jobs.extend([(preview, 1080, 1920, preview_seconds),
                 (full, 1080, 1920, sum(s['duration'] for s in scenes))])
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(lambda job: inspect(*job, args.ffmpeg, args.ffprobe), jobs))
    for record, job in zip(records, jobs):
        record['file'] = str(job[0].relative_to(output))
    # The native logo close-up must contain actual motion, even before zooming.
    logo = output/'02_横屏原始_2560x1600'/(scenes[-1]['key']+'.mp4')
    hashes = run(args.ffmpeg, '-nostdin', '-v', 'error', '-i', logo, '-vf',
                 'fps=4,crop=800:800:880:100', '-f', 'framemd5', '-', capture=True).decode()
    frame_hashes = [line.rsplit(',', 1)[-1].strip() for line in hashes.splitlines()
                    if line and not line.startswith('#')]
    distinct = len(set(frame_hashes))
    assert distinct >= 20, 'Native logo animation did not update'
    manifest = {'schema': 1, 'product': plan['product'], 'version': plan['version'],
                'brand': plan['brand'], 'branding':plan['branding'],
                'recording_mode': 'isolated_native_ui_and_credited_official_public_screenshots',
                'time_compressed': True, 'scene_count': len(scenes),
                'script_order':[{'scene':s['key'],'narration':s['script_cue'],
                                 'source':s.get('source_url','synthetic_native_ui')} for s in scenes],
                'unique_scene_seconds': sum(s['duration'] for s in scenes),
                'native_logo_motion_check': {'sampled_frames': len(frame_hashes),
                                             'distinct_frames': distinct},
                'files': records}
    (output/'素材清单与检查结果.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    (output/'SHA256SUMS.txt').write_text(''.join(r['sha256']+'  '+r['file']+'\n' for r in records))
    print(json.dumps({'verified_videos': len(records), 'unique_scene_seconds': manifest['unique_scene_seconds'],
                      'total_video_bytes': sum(r['bytes'] for r in records),
                      'native_logo_distinct_frames': distinct, 'full_decode': 'passed'}))


if __name__ == '__main__':
    main()
