import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const targets = [
  "apps/web/app/demo",
  "apps/web/app/legal",
  "apps/web/lib/demo-data.ts",
  "docs/portfolio-handoff",
  "apps/web/.next/static",
];
const textExtensions = new Set([".css", ".html", ".js", ".json", ".md", ".map", ".svg", ".ts", ".tsx", ".txt"]);
const checks = [
  ["Supabase service key", /SUPABASE_SERVICE_ROLE_KEY\s*=|service_role["']?\s*[:=]\s*["'][A-Za-z0-9._-]{20,}/i],
  ["JWT-like secret", /eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}/],
  ["private environment owner", /OWNER_EMAIL\s*=|owner@example\.com/i],
  ["Taiwan national ID", /\b[A-Z][12]\d{8}\b/],
  ["phone number", /\b09\d{2}[- ]?\d{3}[- ]?\d{3}\b/],
  ["vehicle plate", /\b(?!(?:WEB|ERR)-)(?:[A-Z]{2,3}-\d{4}|\d{3}-[A-Z]{3})\b/],
  ["official attachment deep link", /(?:DO_VIEWPDF\.htm|AUID=\d+|readOneAspamDetailOld\?|\/Detail\/Chattel\?NO=)/i],
];

async function filesAt(relative) {
  const absolute = path.join(root, relative);
  try {
    const info = await stat(absolute);
    if (info.isFile()) return [absolute];
    const files = [];
    for (const entry of await readdir(absolute, { withFileTypes: true })) {
      const child = path.join(absolute, entry.name);
      if (entry.isDirectory()) files.push(...await filesAt(path.relative(root, child)));
      else if (textExtensions.has(path.extname(entry.name))) files.push(child);
    }
    return files;
  } catch (error) {
    if (error.code === "ENOENT") return [];
    throw error;
  }
}

const files = (await Promise.all(targets.map(filesAt))).flat();
if (!files.length) throw new Error("No public artifacts were found to audit");
const findings = [];
for (const file of files) {
  const content = await readFile(file, "utf8");
  for (const [label, pattern] of checks) if (pattern.test(content)) findings.push(`${path.relative(root, file)}: ${label}`);
}
if (findings.length) {
  console.error("Public artifact audit failed:\n" + findings.map((finding) => `- ${finding}`).join("\n"));
  process.exitCode = 1;
} else {
  console.log(`Public artifact audit passed: ${files.length} text artifacts, 0 prohibited identifiers or secrets.`);
}
