import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { expect, test, type Page } from "@playwright/test";

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

async function installObservers(page: Page) {
  await page.addInitScript(() => {
    const tasks: { start: number; duration: number }[] = [];
    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        tasks.push({ start: entry.startTime, duration: entry.duration });
      }
    });
    observer.observe({ type: "longtask", buffered: true });
    (window as unknown as { __longtasks: typeof tasks }).__longtasks = tasks;
    window.localStorage.setItem("fba_carton_wizard_seen", "1");
    window.localStorage.setItem("fba_sidebar_layout_v2", "1");
    window.localStorage.setItem("fba_sidebar_open", "1");
    delete (window as unknown as { showSaveFilePicker?: unknown }).showSaveFilePicker;
  });
  const external: string[] = [];
  await page.route("**/*", (route) => {
    const url = route.request().url();
    if (url.startsWith("http://127.0.0.1") || url.startsWith("http://localhost")) {
      void route.continue();
      return;
    }
    external.push(url);
    void route.abort();
  });
  return external;
}

async function openInvoice(page: Page) {
  await page.goto("/");
  await page.waitForFunction(() => (window as unknown as { __fbaFboxDropReady?: boolean }).__fbaFboxDropReady === true);
  await page.evaluate((payload) => {
    const file = new File([JSON.stringify(payload)], "v4.fbox", { type: "application/json" });
    const transfer = new DataTransfer();
    transfer.items.add(file);
    window.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: transfer }));
  }, FBOX);
  await expect(page.getByText("V4 e2e")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("forwarder-select")).toBeVisible({ timeout: 20_000 });
  await page.waitForFunction(() => window.__fbaUniverPreloaded === true, undefined, { timeout: 20_000 });
}

async function chooseForwarder(page: Page, name: string) {
  const readyAt = await page.evaluate(() => window.__fbaSnapshotReadyAt ?? 0);
  const select = page.getByTestId("forwarder-select");
  await expect(select).toBeEnabled();
  await select.click();
  await page.getByRole("option", { name, exact: true }).click();
  await expect
    .poll(async () => page.evaluate(() => window.__fbaSnapshotReadyAt ?? 0), { timeout: 15_000 })
    .toBeGreaterThan(readyAt);
  await expect(page.locator("[data-sheet-ready='1']")).toBeVisible();
}

async function longestTaskAfterSnapshot(page: Page): Promise<number> {
  return page.evaluate(() => {
    const readyAt = window.__fbaSnapshotReadyAt ?? 0;
    const tasks = (window as unknown as { __longtasks?: { start: number; duration: number }[] }).__longtasks ?? [];
    const after = tasks.filter((task) => task.start >= readyAt);
    return after.reduce((max, task) => Math.max(max, task.duration), 0);
  });
}

async function wheelInsideGrid(page: Page) {
  const main = page.getByTestId("app-scroll");
  const grid = page.getByTestId("data-univer-grid");
  await grid.hover();
  const before = await main.evaluate((node) => node.scrollTop);
  await page.mouse.wheel(0, 500);
  const after = await main.evaluate((node) => node.scrollTop);
  expect(after).toBe(before);
}

test("V4-T1 T2 T5 T6 B1 wheel and no external requests", async ({ page }) => {
  const external = await installObservers(page);
  await openInvoice(page);

  const started = Date.now();
  await chooseForwarder(page, "SEND（亚马逊 SEND 渠道）");
  expect(Date.now() - started).toBeLessThan(3000);
  expect(await longestTaskAfterSnapshot(page)).toBeLessThan(200);
  await expect
    .poll(
      async () =>
        page.evaluate(() => {
          const list = window.__fbaUniver?.getDataValidations?.() as { getCriteriaType?: () => string }[] | undefined;
          return (list || []).map((rule) => rule.getCriteriaType?.() || "").join(",");
        }),
      { timeout: 5_000 },
    )
    .toMatch(/list|whole|decimal/i);

  const outside = page.getByTestId("app-scroll");
  await page.mouse.move(700, 300);
  const before = await outside.evaluate((node) => node.scrollTop);
  await page.mouse.wheel(0, 400);
  expect(await outside.evaluate((node) => node.scrollTop)).toBeGreaterThan(before);
  await wheelInsideGrid(page);

  for (const name of [
    "琪珞·FBA专线导入模版（T6）",
    "九方",
    "琪珞·下单模板 单行汇总（T5/T7）",
    "德速·Commercial Invoice 9810（T3）",
    "琪珞国际",
  ]) {
    await chooseForwarder(page, name);
    expect(await longestTaskAfterSnapshot(page)).toBeLessThan(200);
  }
  await wheelInsideGrid(page);

  await page.getByRole("button", { name: "系统设置" }).click();
  await page.getByTestId("nav-carton").click();
  await expect(page.getByTestId("back-to-workflow")).toBeVisible();
  await page.getByTestId("carton-wizard-open").click();
  await page.getByTestId("carton-next").click();
  await page.getByTestId("carton-next").click();
  await page.getByTestId("carton-next").click();
  await expect(page.getByTestId("carton-blocker").first()).toBeVisible();
  await expect(page.getByTestId("carton-save")).toBeDisabled();

  await page.getByTestId("back-to-workflow").click();
  await expect(page.getByTestId("forwarder-select")).toBeVisible();
  await expect(page.locator("[data-sheet-ready='1']")).toBeVisible();
  const selected = await page.getByTestId("forwarder-select").innerText();
  if (!selected.includes("SEND")) {
    await chooseForwarder(page, "SEND（亚马逊 SEND 渠道）");
  }
  expect(await longestTaskAfterSnapshot(page)).toBeLessThan(200);
  await wheelInsideGrid(page);
  expect(external).toEqual([]);
});

function workbookShape(file: string) {
  const python = process.env.FBA_E2E_PYTHON || "/tmp/fba-venv/bin/python";
  const script = `
import json, sys
from openpyxl import load_workbook
wb = load_workbook(sys.argv[1])
sheets = []
for ws in wb.worksheets:
    dvs = list(ws.data_validations.dataValidation) if ws.data_validations else []
    sheets.append({
        "name": ws.title,
        "state": ws.sheet_state,
        "images": len(getattr(ws, "_images", []) or []),
        "dv": len(dvs),
        "merges": sorted(str(item) for item in ws.merged_cells.ranges),
    })
formulas = {}
if "发票" in wb.sheetnames:
    formulas["E4"] = wb["发票"]["E4"].value
print(json.dumps({"sheets": sheets, "formulas": formulas}, ensure_ascii=False))
`;
  return JSON.parse(execFileSync(python, ["-c", script, file], { encoding: "utf-8" }));
}

async function exportWorkbook(page: Page): Promise<{ status: number; body: Buffer }> {
  const captured: { status: number; body: Buffer }[] = [];
  await page.route("**/api/export_invoice", async (route) => {
    const upstream = await route.fetch();
    const body = Buffer.from(await upstream.body());
    captured.push({ status: upstream.status(), body });
    await route.fulfill({ response: upstream, body });
  });
  await page.getByTestId("export-invoice").click();
  await expect.poll(() => captured.length, { timeout: 60_000 }).toBeGreaterThan(0);
  await page.unroute("**/api/export_invoice");
  const result = captured[0];
  if (result.body.length < 32 && result.status === 200) {
    throw new Error(`export body too small: ${result.body.length}`);
  }
  return result;
}

test("V4 UI export keeps sheets and images and rejects merge or formula edits", async ({ page }) => {
  await installObservers(page);
  await openInvoice(page);
  const cases = [
    ["德速·Commercial Invoice 9810（T3）", "deshu_t3.xlsx"],
    ["琪珞·FBA专线导入模版（T6）", "qiluo_t6.xlsx"],
    ["SEND（亚马逊 SEND 渠道）", "send.xlsx"],
  ] as const;
  for (const [label, filename] of cases) {
    await chooseForwarder(page, label);
    await expect(page.getByTestId("export-scope-note")).toBeVisible();
    await expect(page.getByTestId("export-invoice")).toBeEnabled();
    const response = await exportWorkbook(page);
    expect(response.status).toBe(200);
    const dir = mkdtempSync(join(tmpdir(), "fba-ui-export-"));
    const out = join(dir, "out.xlsx");
    writeFileSync(out, response.body);
    const original = join("..", "backend", "templates", "forwarders", filename);
    expect(workbookShape(out)).toEqual(workbookShape(original));
    if (filename === "qiluo_t6.xlsx") {
      expect(String(workbookShape(out).formulas.E4)).toContain("VLOOKUP");
      await page.evaluate(async () => {
        window.__fbaUniver?.setCell("E4", "TEST_PURE_123");
        await new Promise((resolve) => window.setTimeout(resolve, 30));
      });
      const formula = await exportWorkbook(page);
      expect(formula.status).toBe(400);
      expect(JSON.parse(formula.body.toString("utf8")).detail.code).toBe("FORMULA_OVERWRITE");
    }
    if (filename === "send.xlsx") {
      await page.evaluate(async () => {
        window.__fbaUniver?.setCell("B4", "TEST_SLAVE");
        await new Promise((resolve) => window.setTimeout(resolve, 30));
      });
      const slave = await exportWorkbook(page);
      expect(slave.status).toBe(400);
      expect(JSON.parse(slave.body.toString("utf8")).detail.code).toBe("MERGED_SLAVE");
    }
  }
});
