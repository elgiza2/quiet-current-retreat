"""Run the actual sandbox renderer locally with generated test fixtures; no model calls.
Usage: python3 scripts/test-montage.py (requires ffmpeg, ffprobe and Pillow).
All test assets and results stay temporary under /home/user, as in E2B.
"""
import pathlib, tempfile, subprocess, json, sys, shutil
from PIL import Image

root = pathlib.Path('/home/user')
root.mkdir(parents=True, exist_ok=True)
work = pathlib.Path(tempfile.mkdtemp(prefix='montage-test-', dir=root))
renderer = pathlib.Path(__file__).resolve().parents[1] / 'src/lib/computer/montage.py'
# A local adapter uses the installed ffmpeg; E2B uses imageio-ffmpeg's binary.
(work / 'imageio_ffmpeg.py').write_text("import shutil\ndef get_ffmpeg_exe(): return shutil.which('ffmpeg')\n")
Image.new('RGB', (900, 1400), (24, 140, 120)).save(work / 'photo.png')
subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=30', '-t', '2', '-c:v', 'libx264', str(work / 'clip.mp4')], check=True)
subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', str(work / 'audio.wav')], check=True)
for aspect, resolution, dims, audio in [('9:16', '720p', (720, 1280), True), ('16:9', '720p', (1280, 720), False), ('1:1', '1080p', (1080, 1080), True)]:
    config = {'scenes': [{'source': str(work / 'photo.png'), 'kind': 'image', 'duration': 1, 'trim_start': 0, 'motion': 'zoom_in'}, {'source': str(work / 'clip.mp4'), 'kind': 'video', 'duration': 1, 'trim_start': 0.5, 'motion': 'none'}], 'captions': [{'text': 'أهلاً من Ceyo — مونتاج بدون توليد', 'start': 0, 'end': 0.9, 'position': 'center'}, {'text': 'Existing footage', 'start': 1, 'end': 2, 'position': 'bottom'}], 'aspect_ratio': aspect, 'resolution': resolution, 'transition': 'fade', 'music_volume': 0.18, 'name': 'montage-render-test.mp4'}
    if audio: config.update(narration=str(work / 'audio.wav'), music=str(work / 'audio.wav'))
    script = work / 'render.py'
    script.write_text('CONFIG = ' + repr(config) + '\n' + renderer.read_text())
    run = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=180)
    if run.returncode: raise RuntimeError(run.stderr)
    metadata = json.loads(run.stdout.strip().splitlines()[-1])
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', metadata['path']]))
    video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    assert (video['width'], video['height']) == dims
    assert video['codec_name'] == 'h264'
    assert abs(float(probe['format']['duration']) - 2) < 0.1
    assert any(s['codec_type'] == 'audio' for s in probe['streams']) == audio
    assert metadata['size'] < 20 * 1024 * 1024
    frame = work / ('frame-' + aspect.replace(':', '-') + '.png')
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-ss', '0.5', '-i', metadata['path'], '-frames:v', '1', str(frame)], check=True)
    print('PASS', aspect, resolution, 'AAC audio' if audio else 'silent', 'H264, 2 seconds, captions, trimmed clip, fades')
# Preserve temporary frames for visual inspection, not as a user deliverable.
print('Frames:', work)
pathlib.Path('/home/user/montage-render-test.mp4').unlink(missing_ok=True)