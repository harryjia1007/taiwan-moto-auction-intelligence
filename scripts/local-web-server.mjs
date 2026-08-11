import { execFileSync, spawn } from "node:child_process";
import { closeSync, openSync } from "node:fs";
import { mkdir, readFile, unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(scriptDir, "..");
const webDir = path.join(rootDir, "apps", "web");
const dataDir = path.join(webDir, ".data");
const statePath = path.join(dataDir, "dev-server.json");
const logPath = path.join(dataDir, "dev-server.log");
const nextBin = path.join(webDir, "node_modules", "next", "dist", "bin", "next");
const healthUrl = "http://127.0.0.1:3000/api/health";
const serviceName = "taiwan-moto-auction-intelligence-web";

const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function readState() {
  try {
    return JSON.parse(await readFile(statePath, "utf8"));
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
}

function processExists(pid) {
  if (!Number.isInteger(pid) || pid <= 1) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error?.code === "EPERM";
  }
}

function processMatches(pid) {
  if (!processExists(pid)) return false;
  try {
    const command = execFileSync("ps", ["-p", String(pid), "-o", "command="], { encoding: "utf8" });
    return command.includes(nextBin) && command.includes("dev") && command.includes("3000");
  } catch {
    return false;
  }
}

async function probe() {
  try {
    const response = await fetch(healthUrl, { cache: "no-store", signal: AbortSignal.timeout(2000) });
    const payload = await response.json();
    if (!response.ok || payload?.service !== serviceName || payload?.status !== "ok") return null;
    return payload;
  } catch {
    return null;
  }
}

async function tailLog(lines = 24) {
  try {
    const content = await readFile(logPath, "utf8");
    return content.split(/\r?\n/).slice(-lines).join("\n");
  } catch (error) {
    return error?.code === "ENOENT" ? "尚無伺服器日誌。" : String(error);
  }
}

async function start() {
  await mkdir(dataDir, { recursive: true });
  const state = await readState();
  const currentHealth = await probe();
  if (state && processMatches(state.pid) && currentHealth) {
    console.log(`RUNNING pid=${state.pid} url=http://localhost:3000 mode=${currentHealth.mode}`);
    return;
  }
  if (currentHealth) {
    console.log(`RUNNING url=http://localhost:3000 mode=${currentHealth.mode}`);
    return;
  }
  if (state && processExists(state.pid)) {
    throw new Error(`PID ${state.pid} 仍存在但不是本專案的 Next.js 3000 埠程序；為避免誤殺程序，請先人工確認。`);
  }
  if (state) await unlink(statePath).catch(() => undefined);

  // A new managed run gets a fresh log so an old failed bind does not look like
  // a current server failure when the user checks `logs` later.
  const logFd = openSync(logPath, "w");
  const child = spawn(process.execPath, [nextBin, "dev", "-H", "127.0.0.1", "-p", "3000"], {
    cwd: webDir,
    detached: true,
    env: {
      ...process.env,
      NODE_ENV: "development",
      OWNER_EMAIL: process.env.OWNER_EMAIL || "owner@example.com",
      TM_FIXTURE_MODE: process.env.TM_FIXTURE_MODE || "true",
    },
    stdio: ["ignore", logFd, logFd],
  });
  child.unref();
  closeSync(logFd);
  await writeFile(statePath, JSON.stringify({ pid: child.pid, rootDir, nextBin, startedAt: new Date().toISOString() }, null, 2));

  for (let attempt = 0; attempt < 40; attempt += 1) {
    const health = await probe();
    if (health) {
      console.log(`STARTED pid=${child.pid} url=http://localhost:3000 mode=${health.mode}`);
      return;
    }
    if (!processExists(child.pid)) break;
    await wait(500);
  }
  const log = await tailLog();
  throw new Error(`伺服器未在 20 秒內通過健康檢查。\n${log}`);
}

async function stop() {
  const state = await readState();
  if (!state) {
    console.log("STOPPED（沒有受管理的本機伺服器）");
    return;
  }
  if (!processExists(state.pid)) {
    await unlink(statePath).catch(() => undefined);
    console.log("STOPPED（已清除過期 PID）");
    return;
  }
  if (!processMatches(state.pid)) throw new Error(`拒絕停止 PID ${state.pid}：它不是這個專案啟動的 Next.js 3000 埠程序。`);
  process.kill(state.pid, "SIGTERM");
  for (let attempt = 0; attempt < 20 && processExists(state.pid); attempt += 1) await wait(250);
  if (processExists(state.pid)) throw new Error(`PID ${state.pid} 未在 5 秒內正常結束；未使用強制終止。`);
  await unlink(statePath).catch(() => undefined);
  console.log("STOPPED");
}

async function status() {
  const state = await readState();
  const health = await probe();
  if (state && processMatches(state.pid) && health) {
    console.log(`RUNNING pid=${state.pid} url=http://localhost:3000 mode=${health.mode} checkedAt=${health.checkedAt}`);
    return;
  }
  console.log(`DOWN${state ? ` stalePid=${state.pid}` : ""}`);
  process.exitCode = 1;
}

const command = process.argv[2] || "status";
try {
  if (command === "start") await start();
  else if (command === "stop") await stop();
  else if (command === "restart") { await stop(); await start(); }
  else if (command === "status") await status();
  else if (command === "logs") console.log(await tailLog(80));
  else throw new Error("用法：node scripts/local-web-server.mjs start|stop|restart|status|logs");
} catch (error) {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
}
