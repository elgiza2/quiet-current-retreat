"""Deterministic FFmpeg/Pillow renderer executed only inside the task sandbox."""
import os, json, subprocess, tempfile, pathlib, urllib.request, re, glob
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont, features

ff = imageio_ffmpeg.get_ffmpeg_exe()
work = tempfile.mkdtemp(prefix='montage-', dir='/home/user')
duration = sum(s['duration'] for s in CONFIG['scenes'])
short = 720 if CONFIG['resolution'] == '720p' else 1080
w, h = {'9:16': (short, short * 16 // 9), '16:9': (short * 16 // 9, short), '1:1': (short, short)}[CONFIG['aspect_ratio']]
w, h = w // 2 * 2, h // 2 * 2
fps = 30

def run(args):
    p = subprocess.run([ff, '-hide_banner', '-loglevel', 'error', '-y', *args], capture_output=True, text=True, timeout=240)
    if p.returncode: raise RuntimeError('Media render failed: ' + p.stderr[-1800:])

def asset(source, label):
    if source.startswith('/home/user/'):
        real = pathlib.Path(source).resolve()
        if not str(real).startswith('/home/user/'): raise ValueError('Asset path escapes task directory')
        if not real.is_file(): raise ValueError('Asset file missing')
        return str(real)
    target = os.path.join(work, label)
    req = urllib.request.Request(source, headers={'User-Agent': 'CeyoMedia/1.0'})
    with urllib.request.urlopen(req, timeout=30) as response, open(target, 'wb') as out:
        if not response.url.startswith('https://'): raise ValueError('Insecure asset redirect')
        size = 0
        while True:
            chunk = response.read(65536)
            if not chunk: break
            size += len(chunk)
            if size > 100 * 1024 * 1024: raise ValueError('Asset exceeds 100 MB; trim it first')
            out.write(chunk)
    return target

parts = []
for i, scene in enumerate(CONFIG['scenes']):
    source = asset(scene['source'], 'source-' + str(i))
    d = scene['duration']
    args = ['-loop', '1', '-i', source] if scene['kind'] == 'image' else ['-ss', str(scene['trim_start']), '-i', source]
    vf = f'scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={fps}'
    if scene['kind'] == 'image' and scene['motion'] != 'none':
        frames = max(1, round(d * fps))
        zoom = f'1+0.12*on/{frames}' if scene['motion'] == 'zoom_in' else f'1.12-0.12*on/{frames}'
        vf += f",zoompan=z='{zoom}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={frames}:s={w}x{h}:fps={fps}"
    if scene['kind'] == 'video': vf += f',tpad=stop_mode=clone:stop_duration={d}'
    if CONFIG['transition'] == 'fade':
        fade = min(0.2, d / 4)
        vf += f',fade=t=in:st=0:d={fade},fade=t=out:st={d-fade}:d={fade}'
    path = os.path.join(work, f'scene-{i}.mp4')
    run([*args, '-t', str(d), '-vf', vf, '-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22', '-pix_fmt', 'yuv420p', '-threads', '2', path])
    parts.append(path)
listing = os.path.join(work, 'list.txt')
with open(listing, 'w') as out: out.write(''.join("file '" + p + "'\n" for p in parts))
base = os.path.join(work, 'base.mp4')
run(['-f', 'concat', '-safe', '0', '-i', listing, '-c', 'copy', base])

fonts = glob.glob('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf') + glob.glob('/usr/share/fonts/**/DejaVuSans.ttf', recursive=True)
if CONFIG['captions'] and not fonts: raise ValueError('Caption font missing; install fonts-dejavu-core in the computer')

def caption_image(c, index):
    size = int(short * 0.06)
    text = c['text']
    arabic = bool(re.search('[\u0600-\u06ff]', text))
    raqm = features.check_feature('raqm')
    direction = {'direction': 'rtl'} if arabic and raqm else {}
    if arabic and not raqm:
        import arabic_reshaper
        from bidi.algorithm import get_display
    image = Image.new('RGBA', (w, h))
    draw = ImageDraw.Draw(image)
    while True:
        font = ImageFont.truetype(fonts[0], size)
        lines, line = [], ''
        for word in text.split():
            trial = (line + ' ' + word).strip()
            if draw.textlength(trial, font=font, **direction) > w * 0.85 and line:
                lines.append(line); line = word
            else: line = trial
        if line: lines.append(line)
        if size <= 14 or (len(lines) <= 4 and all(draw.textlength(line, font=font, **direction) <= w * 0.85 for line in lines)): break
        size -= 2
    if arabic and not raqm: lines = [get_display(arabic_reshaper.reshape(line)) for line in lines]
    block = len(lines) * size * 1.5
    y = (h - block) / 2 if c['position'] == 'center' else h * 0.78 - block / 2
    draw.rounded_rectangle((w * 0.04, y - 16, w * 0.96, y + block + 8), radius=8, fill=(0, 0, 0, 160))
    for line in lines:
        draw.text((w / 2, y), line, font=font, anchor='mt', fill='white', stroke_width=1, stroke_fill='black', **direction)
        y += size * 1.5
    target = os.path.join(work, f'caption-{index}.png')
    image.save(target)
    return target

args = ['-i', base]
filters, current = [], '0:v'
index = 1
for i, c in enumerate(CONFIG['captions']):
    args += ['-loop', '1', '-i', caption_image(c, i)]
    nxt = f'cap{i}'
    filters.append(f"[{current}][{index}:v]overlay=enable='gte(t,{c['start']})*lt(t,{c['end']})':shortest=1[{nxt}]")
    current = nxt; index += 1
voice, music = None, None
if CONFIG.get('narration'):
    voice = index; index += 1; args += ['-i', asset(CONFIG['narration'], 'narration')]
if CONFIG.get('music'):
    music = index; args += ['-stream_loop', '-1', '-i', asset(CONFIG['music'], 'music')]
if voice is not None:
    filters.append(f'[{voice}:a]aresample=48000,apad,atrim=duration={duration},asetpts=PTS-STARTPTS[voice]')
if music is not None:
    filters.append(f"[{music}:a]aresample=48000,volume={CONFIG['music_volume']},atrim=duration={duration},asetpts=PTS-STARTPTS[music]")
if voice is not None and music is not None:
    filters += ['[voice]asplit=2[spoken][side]', '[music][side]sidechaincompress=threshold=0.025:ratio=8:attack=20:release=250[ducked]', '[spoken][ducked]amix=inputs=2:normalize=0:duration=longest[audio]']
elif voice is not None: filters.append('[voice]anull[audio]')
elif music is not None: filters.append('[music]anull[audio]')
if filters: args += ['-filter_complex', ';'.join(filters), '-filter_complex_threads', '1']
args += ['-map', f'[{current}]' if current != '0:v' else '0:v']
if voice is not None or music is not None: args += ['-map', '[audio]', '-c:a', 'aac', '-b:a', '128k']
else: args += ['-an']
# Target 18 MB, below the existing private-export ceiling even for long montages.
rate = min(4000000, int(18 * 1024 * 1024 * 8 / duration) - 160000)
output = '/home/user/' + CONFIG['name']
run([*args, '-t', str(duration), '-c:v', 'libx264', '-preset', 'veryfast', '-b:v', str(rate), '-maxrate', str(rate), '-bufsize', str(rate * 2), '-threads', '2', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', output])
if os.path.getsize(output) > 20 * 1024 * 1024: raise ValueError('Video exceeds private export size; reduce duration or resolution')
print(json.dumps({'path': output, 'name': CONFIG['name'], 'mime': 'video/mp4', 'duration': duration, 'width': w, 'height': h, 'has_audio': voice is not None or music is not None, 'source_audio': 'removed; use narration/music inputs to retain supplied audio', 'captions': len(CONFIG['captions']), 'size': os.path.getsize(output)}))