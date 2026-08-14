import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const jsonMode = process.argv.includes("--json");

function command(commandName, args, timeout = 5_000) {
  const result = spawnSync(commandName, args, { cwd: root, encoding: "utf8", timeout });
  return {
    found: result.error?.code !== "ENOENT",
    ok: result.status === 0,
    output: `${result.stdout ?? ""}${result.stderr ?? ""}`.trim(),
  };
}

function runtime(name) {
  const version = command(name, ["--version"]);
  if (!version.found) return { name, state: "missing", detail: "未安裝" };
  const info = command(name, ["info"], 10_000);
  return {
    name,
    state: info.ok ? "ready" : "stopped",
    detail: info.ok ? version.output.split("\n")[0] : "已安裝，但服務尚未啟動或無法連線",
  };
}

const nodeMajor = Number(process.versions.node.split(".")[0]);
const runtimes = [runtime("docker"), runtime("podman")];
const readyRuntime = runtimes.find((candidate) => candidate.state === "ready");
const installedRuntime = runtimes.find((candidate) => candidate.state === "stopped");
const desktopApps = [
  ["Docker Desktop", "/Applications/Docker.app"],
  ["OrbStack", "/Applications/OrbStack.app"],
  ["Podman Desktop", "/Applications/Podman Desktop.app"],
].filter(([, applicationPath]) => existsSync(applicationPath)).map(([name]) => name);

const supabaseCli = existsSync(path.join(root, "node_modules", ".bin", "supabase"));
const checks = [
  {
    id: "node",
    ok: nodeMajor >= 24,
    label: "Node.js 24+",
    detail: `v${process.versions.node}`,
    requiredFor: "網站、工具與測試",
  },
  {
    id: "supabase_cli",
    ok: supabaseCli,
    label: "專案內 Supabase CLI",
    detail: supabaseCli ? "已安裝" : "請先執行 pnpm install",
    requiredFor: "migration、seed、Auth、Storage、pgTAP",
  },
  {
    id: "container_runtime",
    ok: Boolean(readyRuntime),
    label: "Docker 相容容器執行器",
    detail: readyRuntime?.detail
      ?? installedRuntime?.detail
      ?? (desktopApps.length ? `${desktopApps.join("、")} 已存在，但 CLI/服務不可用` : "Docker、OrbStack、Podman、Colima 均未偵測到"),
    requiredFor: "本機 PostgreSQL、Auth、Storage、郵件與 pgTAP",
  },
  {
    id: "supabase_config",
    ok: existsSync(path.join(root, "supabase", "config.toml")),
    label: "Supabase 專案設定",
    detail: "supabase/config.toml",
    requiredFor: "可重現的本機堆疊",
  },
  {
    id: "database_tests",
    ok: existsSync(path.join(root, "supabase", "tests", "database", "schema.test.sql")),
    label: "pgTAP 資料庫測試",
    detail: "supabase/tests/database/schema.test.sql",
    requiredFor: "schema、RLS、限制條件與資料語意",
  },
];

const report = {
  ready: checks.every((check) => check.ok),
  checkedAt: new Date().toISOString(),
  checks,
  nextCommand: readyRuntime ? "pnpm db:verify" : "安裝並啟動 Docker Desktop、OrbStack、Podman 或 Colima 後，再執行 pnpm run doctor",
};

if (jsonMode) {
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
} else {
  console.log("臺灣機車拍賣情報｜本機環境診斷\n");
  for (const check of checks) {
    console.log(`${check.ok ? "✓" : "✗"} ${check.label}：${check.detail}`);
    if (!check.ok) console.log(`  影響：${check.requiredFor}`);
  }
  console.log(`\n下一步：${report.nextCommand}`);
}

if (!report.ready) process.exitCode = 1;
