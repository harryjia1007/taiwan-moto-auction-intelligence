import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const media = {
  "939528-1": "https://shwoo.gov.taipei/shwoo/imageResize?piccode=20260728504721&width=960&height=720&attach=20260728160842.PNG",
  "939528-2": "https://shwoo.gov.taipei/shwoo/imageResize?piccode=20260728504721&width=960&height=720&attach=20260728160923.PNG",
  "939611-1": "https://shwoo.gov.taipei/shwoo/imageResize?piccode=20260729505232&width=960&height=720&attach=20260729084342.PNG",
  "939611-2": "https://shwoo.gov.taipei/shwoo/imageResize?piccode=20260729505232&width=960&height=720&attach=20260729084408.PNG",
  "939611-3": "https://shwoo.gov.taipei/shwoo/imageResize?piccode=20260729505232&width=960&height=720&attach=20260729084438.PNG",
  "939179-1": "https://shwoo.gov.taipei/shwoo/imageResize?piccode=20260727501983&width=960&height=720&attach=20260727141841.PNG",
  "939179-2": "https://shwoo.gov.taipei/shwoo/imageResize?piccode=20260727501983&width=960&height=720&attach=20260727142105.PNG",
  "939179-3": "https://shwoo.gov.taipei/shwoo/imageResize?piccode=20260727501983&width=960&height=720&attach=20260727142205.PNG",
};

const output = path.join(process.cwd(), "apps", "web", ".data", "fixture-media");
await mkdir(output, { recursive: true });
for (const [key, source] of Object.entries(media)) {
  const url = new URL(source);
  if (url.protocol !== "https:" || url.hostname !== "shwoo.gov.taipei") throw new Error(`Blocked fixture media host: ${url.hostname}`);
  const response = await fetch(url, { headers: { "user-agent": "TaiwanMotoAuctionIntelligence/0.3 (+local fixture cache)" } });
  if (!response.ok) throw new Error(`${key}: HTTP ${response.status}`);
  const mime = response.headers.get("content-type")?.split(";", 1)[0].toLowerCase();
  if (!new Set(["image/jpeg", "image/png", "image/webp"]).has(mime)) throw new Error(`${key}: invalid MIME ${mime}`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.byteLength > 25 * 1024 * 1024) throw new Error(`${key}: image exceeds 25 MiB`);
  await writeFile(path.join(output, `${key}.${mime === "image/png" ? "png" : mime === "image/webp" ? "webp" : "jpg"}`), bytes);
  console.log(`${key}: ${bytes.byteLength} bytes`);
}
