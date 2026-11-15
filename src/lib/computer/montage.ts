import { z } from "zod";
import renderer from "./montage.py?raw";

export const mediaSource = z.string().max(2000).refine((value) => {
  if (value.startsWith("/home/user/")) return !value.split("/").includes("..") && !/[\x00-\x1f]/.test(value);
  try { const u = new URL(value); return u.protocol === "https:" && !u.username && !u.password; } catch { return false; }
}, "Use an HTTPS asset or a file under /home/user/");

const caption = z.object({ text: z.string().min(1).max(240), start: z.number().min(0), end: z.number().positive(), position: z.enum(["center", "bottom"]).default("bottom") }).strict().refine((c) => c.end > c.start, "Caption end must follow its start");
export const montageInput = z.object({
  scenes: z.array(z.object({ source: mediaSource, kind: z.enum(["image", "video"]), duration: z.number().min(0.5).max(30), trim_start: z.number().min(0).default(0), motion: z.enum(["none", "zoom_in", "zoom_out"]).default("none") }).strict()).min(1).max(20),
  captions: z.array(caption).max(200).default([]),
  aspect_ratio: z.enum(["9:16", "16:9", "1:1"]).default("9:16"),
  resolution: z.enum(["720p", "1080p"]).default("720p"),
  transition: z.enum(["cut", "fade"]).default("fade"),
  narration: mediaSource.optional(),
  music: mediaSource.optional(),
  music_volume: z.number().min(0).max(1).default(0.18),
  name: z.string().regex(/^[a-zA-Z0-9_-]{1,80}\.mp4$/).default("montage.mp4"),
}).strict().superRefine((a, ctx) => {
  const duration = a.scenes.reduce((total, s) => total + s.duration, 0);
  if (duration > 120) ctx.addIssue({ code: "custom", message: "Split videos longer than 120 seconds into separate renders" });
  if (a.captions.some((c) => c.end > duration)) ctx.addIssue({ code: "custom", message: "Caption timing exceeds video duration" });
});

export const montageToolProperties = {
  scenes: { type: "array", items: { type: "object", properties: { source: { type: "string" }, kind: { type: "string", enum: ["image", "video"] }, duration: { type: "number" }, trim_start: { type: "number" }, motion: { type: "string", enum: ["none", "zoom_in", "zoom_out"] } }, required: ["source", "kind", "duration"] } },
  captions: { type: "array", items: { type: "object", properties: { text: { type: "string" }, start: { type: "number" }, end: { type: "number" }, position: { type: "string", enum: ["center", "bottom"] } }, required: ["text", "start", "end"] } },
  aspect_ratio: { type: "string", enum: ["9:16", "16:9", "1:1"] }, resolution: { type: "string", enum: ["720p", "1080p"] }, transition: { type: "string", enum: ["cut", "fade"] }, narration: { type: "string" }, music: { type: "string" }, music_volume: { type: "number" }, name: { type: "string" },
};

/** Only serializes data here; all native media work runs in the isolated computer. */
export function montageScript(raw: unknown) {
  const input = montageInput.parse(raw);
  return `import json\nCONFIG = json.loads(${JSON.stringify(JSON.stringify(input))})\n${renderer}`;
}

export function inspectMediaScript(raw: unknown) {
  const source = z.object({ source: mediaSource }).parse(raw).source;
  return `import json, subprocess, re, imageio_ffmpeg\nsource=json.loads(${JSON.stringify(JSON.stringify(source))})\nr=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-i', source],capture_output=True,text=True,timeout=30)\nt=r.stderr\nif 'Video:' not in t and 'Audio:' not in t: raise ValueError('Asset is not readable video/audio: '+t[-400:])\nd=re.search(r'Duration: (\\d+):(\\d+):([\\d.]+)',t)\nv=re.search(r'Video: ([^,]+).*? (\\d{2,5})x(\\d{2,5})',t)\nprint(json.dumps({'duration':int(d[1])*3600+int(d[2])*60+float(d[3]) if d else None,'width':int(v[2]) if v else None,'height':int(v[3]) if v else None,'has_audio':'Audio:' in t,'has_video':'Video:' in t}))`;
}