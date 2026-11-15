import type { Computer } from "./e2b.server";
import { montageInput, montageScript } from "./montage";

/** Render and export in one tool so the task cannot close before delivery. */
export async function createVideoMontage(computer: Computer, raw: unknown, save: (input: { path: string; name: string; mime: string }) => Promise<string>) {
  const input = montageInput.parse(raw);
  const ready = await computer.prepareMedia();
  if (!ready.ok) throw new Error(ready.output);
  const result = await computer.run(montageScript(input), "python", 300000);
  if (!result.ok) throw new Error(result.output.slice(-1800));
  const lines = result.output.trim().split("\n");
  let metadata: { path: string; name: string; mime: string; duration: number; width: number; height: number; has_audio: boolean } | undefined;
  for (const line of lines) {
    try { const value = JSON.parse(line); if (value.path === `/home/user/${input.name}` && value.mime === "video/mp4") metadata = value; } catch { /* other execution output */ }
  }
  if (!metadata) throw new Error("Renderer did not confirm a video file; nothing was exported.");
  const artifact = JSON.parse(await save({ path: metadata.path, name: input.name, mime: "video/mp4" }));
  return JSON.stringify({ ...artifact, duration: metadata.duration, width: metadata.width, height: metadata.height, has_audio: metadata.has_audio, instruction: `Video saved privately; the chat displays its file card. ${metadata.has_audio ? "Supplied audio mixed." : "This video is silent."} Source-clip audio is removed; narration/music must be supplied explicitly. No image/video generation model used.` });
}