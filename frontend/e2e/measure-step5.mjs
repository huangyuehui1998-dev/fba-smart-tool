/**
 * 第 5 步（发票，step 4.5）冷启动测量。同时打出 longtask 和墙钟。
 *
 * 每个模式打两段，longtask 和墙钟都有：
 *   shell_*  放下 .fbox 到 window.__fbaUniverShell（引擎挂上。预热要靠这段变短）
 *   ready_*  同一起点到 data-sheet-ready=1（中间会选 SEND。T6 看这里的单个 longtask ≤400ms）
 * 墙钟只作参考，不是门槛。longtask 只统计起点之后开始、且超过 50ms 的任务。
 *
 * 预热：打开首页后等到 window.__fbaUniverWarmed（createUniver 已经在离屏节点里完成）。
 * 裸启动：__fbaSkipUniverWarm，进第 5 步才 createUniver。
 *
 *   cd frontend && npm run build
 *   MEASURE_N=30 node e2e/measure-step5.mjs
 *
 * 需要预览 http://127.0.0.1:4173 和 API http://127.0.0.1:8002。
 * 两个都没开时，脚本会按 playwright.config.ts 拉起来。已经开着就复用，所以改完前端要先重新 build 并重启 preview。
 */
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const here = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(here, "..");
const backendDir = path.resolve(frontendDir, "../backend");
const appURL = process.env.MEASURE_URL || "http://127.0.0.1:4173";
const apiURL = process.env.MEASURE_API || "http://127.0.0.1:8002";
const runs = Math.max(1, Number(process.env.MEASURE_N || "5"));

const FBOX = {
  version: 1,
  task_id: "e2e-v4",
  task_name: "V4 e2e",
  saved_at: "2026-10-21T00:00:00Z",
  settings: { step: 4.5, throw_ratio: 1 },
  grid_data: {
    task_id: "e2e-v4",
    task_name: "V4 e2e",
    step: 4.5,
    step4_validated: true,
    react_step4_ok: true,
    react_highest_reached_step: 5,
    react_selected_shipment_id: "FBAE2E",
    step4_shipment_bundle: [
      {
        shipment_id: "FBAE2E",
        warehouse: "ONT8",
        csv_b64: "aGVsbG8=",
        pdf_b64: "aGVsbG8=",
      },
    ],
    input_df: [],
  },
};

function pythonBin() {
  const fromEnv = process.env.FBA_E2E_PYTHON?.trim();
  if (fromEnv) return fromEnv;
  const preferred = "/tmp/fba-venv/bin/python";
  if (existsSync(preferred)) return preferred;
  return "python3";
}

function portOpen(port, host) {
  return new Promise((resolve) => {
    const socket = net.connect({ port, host }, () => {
      socket.end();
      resolve(true);
    });
    socket.on("error", () => resolve(false));
  });
}

async function waitForHTTP(url, timeoutMs) {
  const started = Date.now();
  let last = "not up";
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok || response.status < 500) return;
      last = `HTTP ${response.status}`;
    } catch (error) {
      last = error instanceof Error ? error.message : String(error);
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(`${url} 没有起来：${last}`);
}

const children = [];

function startServer(command, args, cwd, extraEnv) {
  const child = spawn(command, args, {
    cwd,
    env: { ...process.env, ...extraEnv },
    stdio: "ignore",
    detached: false,
  });
  children.push(child);
  return child;
}

async function ensureServers() {
  const api = new URL(apiURL);
  const app = new URL(appURL);
  if (!(await portOpen(Number(api.port), api.hostname))) {
    startServer(pythonBin(), ["-m", "uvicorn", "main:app", "--host", api.hostname, "--port", String(api.port)], backendDir, {
      FBA_APP_DATA_DIR: process.env.FBA_E2E_DATA_DIR || "/tmp/fba-e2e-data",
      FBA_DISABLE_SCHEDULER: "1",
    });
  }
  if (!(await portOpen(Number(app.port), app.hostname))) {
    startServer("npm", ["run", "preview", "--", "--host", app.hostname, "--port", String(app.port), "--strictPort"], frontendDir, {});
  }
  await waitForHTTP(`${apiURL}/api/health`, 120_000);
  await waitForHTTP(appURL, 120_000);
}

function stopServers() {
  for (const child of children) {
    if (!child.killed) child.kill("SIGTERM");
  }
}

async function install(page, bare) {
  await page.addInitScript((skipWarm) => {
    const tasks = [];
    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) tasks.push({ start: entry.startTime, duration: entry.duration });
    });
    observer.observe({ type: "longtask", buffered: true });
    window.__longtasks = tasks;
    if (skipWarm) window.__fbaSkipUniverWarm = true;
    window.localStorage.setItem("fba_carton_wizard_seen", "1");
    window.localStorage.setItem("fba_sidebar_layout_v2", "1");
    window.localStorage.setItem("fba_sidebar_open", "1");
    delete window.showSaveFilePicker;
  }, bare);
  await page.route("**/*", (route) => {
    const url = route.request().url();
    if (url.startsWith("http://127.0.0.1") || url.startsWith("http://localhost")) {
      void route.continue();
      return;
    }
    void route.abort();
  });
}

function sampleSince(dropAt) {
  const tasks = (window.__longtasks || []).filter((task) => task.start >= dropAt);
  return {
    wall_ms: performance.now() - dropAt,
    longest_longtask_ms: tasks.reduce((max, task) => Math.max(max, task.duration), 0),
    longtask_count: tasks.length,
    longtasks_ms: tasks.map((task) => Math.round(task.duration * 10) / 10),
  };
}

async function enterStep5(page, navigate) {
  if (navigate) await page.goto(appURL, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.__fbaFboxDropReady === true, undefined, { timeout: 20_000 });
  const dropped = await page.evaluate((payload) => {
    const tasks = window.__longtasks || [];
    const started = performance.now();
    const file = new File([JSON.stringify(payload)], "v4.fbox", { type: "application/json" });
    const transfer = new DataTransfer();
    transfer.items.add(file);
    window.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: transfer }));
    const node = document.querySelector("[data-fba-univer-warm]");
    return {
      started,
      warm_node: Boolean(node),
      warm_children: node ? node.childElementCount : 0,
      before_drop_longest_longtask_ms: tasks.reduce((max, task) => Math.max(max, task.duration), 0),
      before_drop_longtask_count: tasks.length,
    };
  }, FBOX);
  const dropAt = dropped.started;
  await page.waitForFunction(() => window.__fbaUniverShell === true, undefined, { timeout: 30_000 });
  const shell = await page.evaluate(sampleSince, dropAt);
  const select = page.getByTestId("forwarder-select");
  await select.click();
  await page.getByRole("option", { name: "SEND（亚马逊 SEND 渠道）", exact: true }).click();
  await page.waitForFunction(() => document.querySelector("[data-sheet-ready='1']") != null, undefined, { timeout: 30_000 });
  const ready = await page.evaluate(sampleSince, dropAt);
  return { shell, ready, before: dropped };
}

function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2) return sorted[mid];
  return (sorted[mid - 1] + sorted[mid]) / 2;
}

function printSample(prefix, sample) {
  return [
    `${prefix}_wall_ms=${sample.wall_ms.toFixed(1)}`,
    `${prefix}_longest_longtask_ms=${sample.longest_longtask_ms.toFixed(1)}`,
    `${prefix}_longtask_count=${sample.longtask_count}`,
    `${prefix}_longtasks_ms=${sample.longtasks_ms.join(",") || "-"}`,
  ].join(" ");
}

function printRun(mode, index, sample) {
  const before = sample.before;
  console.log(
    [
      "run",
      `mode=${mode}`,
      `i=${index}`,
      `before_drop_warm_node=${before.warm_node ? 1 : 0}`,
      `before_drop_warm_children=${before.warm_children}`,
      `before_drop_longest_longtask_ms=${before.before_drop_longest_longtask_ms.toFixed(1)}`,
      `before_drop_longtask_count=${before.before_drop_longtask_count}`,
      printSample("shell", sample.shell),
      printSample("ready", sample.ready),
    ].join(" "),
  );
}

function printSummary(mode, samples) {
  const walls = samples.map((sample) => sample.ready.wall_ms);
  const tasks = samples.map((sample) => sample.ready.longest_longtask_ms);
  const shellTasks = samples.map((sample) => sample.shell.longest_longtask_ms);
  const over = tasks.filter((value) => value > 400).length;
  console.log(
    [
      `summary mode=${mode}`,
      `n=${samples.length}`,
      `ready_wall_median_ms=${median(walls).toFixed(1)}`,
      `ready_wall_max_ms=${Math.max(...walls).toFixed(1)}`,
      `ready_longtask_median_ms=${median(tasks).toFixed(1)}`,
      `ready_longtask_max_ms=${Math.max(...tasks).toFixed(1)}`,
      `ready_longtask_over_400=${over}/${samples.length}`,
      `shell_longtask_median_ms=${median(shellTasks).toFixed(1)}`,
      `shell_longtask_max_ms=${Math.max(...shellTasks).toFixed(1)}`,
      "gate=single_longtask_after_entry_le_400",
      "wall_clock=reference_only",
    ].join(" "),
  );
}

async function openPage(browser, bare) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1800 } });
  const page = await context.newPage();
  page.setDefaultTimeout(45_000);
  const client = await context.newCDPSession(page);
  await client.send("Network.enable");
  await client.send("Network.setCacheDisabled", { cacheDisabled: true });
  await install(page, bare);
  return page;
}

async function measure(browser, mode) {
  const samples = [];
  for (let index = 1; index <= runs; index += 1) {
    const page = await openPage(browser, mode === "bare");
    if (mode === "warmed") {
      await page.goto(appURL, { waitUntil: "domcontentloaded" });
      await page.waitForFunction(() => window.__fbaUniverWarmed === true, undefined, { timeout: 30_000 });
    }
    const sample = await enterStep5(page, mode === "bare");
    samples.push(sample);
    printRun(mode, index, sample);
    await page.context().close();
  }
  printSummary(mode, samples);
}

async function main() {
  await ensureServers();
  console.log(`measure-step5 url=${appURL} api=${apiURL} n=${runs}`);
  console.log("longtask = longest PerformanceObserver longtask starting after the fbox drop, until data-sheet-ready=1");
  console.log("wall_ms = performance.now() from that drop until data-sheet-ready=1 (reference only)");
  // 两个浏览器分开，裸启动不吃预热那次的内存缓存。缓存也关掉，接近测试方的冷机器。
  const bareBrowser = await chromium.launch({ headless: true });
  try {
    await measure(bareBrowser, "bare");
  } finally {
    await bareBrowser.close();
  }
  const warmedBrowser = await chromium.launch({ headless: true });
  try {
    await measure(warmedBrowser, "warmed");
  } finally {
    await warmedBrowser.close();
    stopServers();
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : error);
  stopServers();
  process.exit(1);
});
