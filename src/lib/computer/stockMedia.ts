import { z } from "zod";

const input = z.object({ query: z.string().trim().min(2).max(160), kind: z.enum(["image", "video"]).default("video") });
/** Wikimedia returns original assets and their licenses; no scraping or provider key. */
export async function searchStockMedia(raw: unknown) {
  const a = input.parse(raw);
  const query = new URLSearchParams({ action: "query", format: "json", generator: "search", gsrsearch: `${a.query} filetype:${a.kind === "video" ? "video" : "bitmap"}`, gsrnamespace: "6", gsrlimit: "8", prop: "imageinfo", iiprop: "url|mime|extmetadata", origin: "*" });
  const response = await fetch(`https://commons.wikimedia.org/w/api.php?${query}`, { headers: { "User-Agent": "CeyoMedia/1.0 (https://ceyo.si)" }, signal: AbortSignal.timeout(20000) });
  if (!response.ok) throw new Error("Stock media search unavailable; try web_search for licensed assets.");
  const data = await response.json() as { query?: { pages?: Record<string, { title: string; imageinfo?: { url: string; descriptionurl: string; mime: string; extmetadata?: Record<string, { value: string }> }[] }> } };
  const plain = (text = "") => text.replace(/<[^>]*>/g, "").slice(0, 600);
  const results = Object.values(data.query?.pages ?? {}).flatMap((page) => {
    const info = page.imageinfo?.[0];
    if (!info || !info.mime.startsWith(a.kind === "video" ? "video/" : "image/")) return [];
    return [{ title: page.title, source: info.url, page: info.descriptionurl, mime: info.mime, author: plain(info.extmetadata?.Artist?.value), license: plain(info.extmetadata?.LicenseShortName?.value), license_url: info.extmetadata?.LicenseUrl?.value ?? "", attribution: plain(info.extmetadata?.Attribution?.value) }];
  });
  return JSON.stringify({ results, instruction: "Use only appropriate licensed assets. Read the source page and comply with attribution/share-alike; include source/author/license in the final reply. No results is not permission to invent footage." });
}