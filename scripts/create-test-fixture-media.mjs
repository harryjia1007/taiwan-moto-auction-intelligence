import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const ids = [
  "939528-1", "939528-2", "939611-1", "939611-2", "939611-3", "939179-1", "939179-2", "939179-3",
];

const output = path.join(process.cwd(), "apps", "web", ".data", "fixture-media");
await mkdir(output, { recursive: true });

for (const [index, id] of ids.entries()) {
  const hue = (index * 47 + 142) % 360;
  const svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="960" height="720" viewBox="0 0 960 720" role="img" aria-label="Synthetic test fixture ${id}">
  <rect width="960" height="720" fill="hsl(${hue} 22% 88%)"/>
  <rect x="48" y="48" width="864" height="624" rx="18" fill="none" stroke="hsl(${hue} 35% 35%)" stroke-width="6"/>
  <text x="480" y="340" text-anchor="middle" font-family="sans-serif" font-size="42" fill="hsl(${hue} 35% 25%)">TEST FIXTURE</text>
  <text x="480" y="400" text-anchor="middle" font-family="monospace" font-size="30" fill="hsl(${hue} 35% 25%)">${id}</text>
</svg>`;
  await writeFile(path.join(output, `${id}.svg`), svg);
}

console.log(`Created ${ids.length} synthetic fixture images for browser tests.`);
