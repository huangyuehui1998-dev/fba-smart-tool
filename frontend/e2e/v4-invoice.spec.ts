import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { e2ePython } from "./python-bin";

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

async function openInvoice(page: Page, payload: typeof FBOX = FBOX) {
  await page.goto("/");
  await page.waitForFunction(() => (window as unknown as { __fbaFboxDropReady?: boolean }).__fbaFboxDropReady === true);
  await page.evaluate((payload) => {
    const file = new File([JSON.stringify(payload)], "v4.fbox", { type: "application/json" });
    const transfer = new DataTransfer();
    transfer.items.add(file);
    window.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: transfer }));
  }, payload);
  await expect(page.getByText("V4 e2e")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("forwarder-select")).toBeVisible({ timeout: 20_000 });
  await page.waitForFunction(() => window.__fbaUniverPreloaded === true, undefined, { timeout: 20_000 });
}

async function chooseForwarder(page: Page, name: string) {
  const readyAt = await page.evaluate(() => window.__fbaSnapshotReadyAt ?? 0);
  const shell = page.locator("[data-sheet-load]");
  const loadCount = Number((await shell.getAttribute("data-sheet-load")) || 0);
  const select = page.getByTestId("forwarder-select");
  await expect(select).toBeEnabled();
  const current = (await select.innerText()).trim();
  if (current === name || current.includes(name)) {
    await expect
      .poll(async () => shell.getAttribute("data-sheet-ready"), { timeout: 20_000 })
      .toBe("1");
    return;
  }
  await select.click();
  await page.getByRole("option", { name, exact: true }).click();
  await expect
    .poll(async () => page.evaluate(() => window.__fbaSnapshotReadyAt ?? 0), { timeout: 15_000 })
    .toBeGreaterThan(readyAt);
  await expect
    .poll(async () => {
      const count = Number((await shell.getAttribute("data-sheet-load")) || 0);
      const ready = await shell.getAttribute("data-sheet-ready");
      return count > loadCount && ready === "1";
    }, { timeout: 15_000 })
    .toBe(true);
}

async function longestTaskAfterSnapshot(page: Page): Promise<number> {
  return page.evaluate(() => {
    const readyAt = window.__fbaSnapshotReadyAt ?? 0;
    const tasks = (window as unknown as { __longtasks?: { start: number; duration: number }[] }).__longtasks ?? [];
    const after = tasks.filter((task) => task.start >= readyAt);
    return after.reduce((max, task) => Math.max(max, task.duration), 0);
  });
}

async function wheelInsideGrid(page: Page, expected: "page" | "sheet" | "match") {
  const main = page.getByTestId("app-scroll");
  const grid = page.getByTestId("data-univer-grid");
  await main.evaluate((node) => {
    node.scrollTop = 0;
  });
  await grid.hover();
  const before = await main.evaluate((node) => node.scrollTop);
  await page.mouse.wheel(0, 600);
  await page.waitForTimeout(80);
  const after = await main.evaluate((node) => node.scrollTop);
  const target = await page.evaluate(() => window.__fbaGridWheel?.target ?? "");
  const mode = expected === "match" ? target : expected;
  expect(target).toBe(mode);
  if (mode === "page") expect(after).toBeGreaterThan(before);
  else expect(after).toBe(before);
}

async function wheelReachesPageAtGridEdge(page: Page) {
  const grid = page.getByTestId("data-univer-grid");
  const main = page.getByTestId("app-scroll");
  await grid.evaluate((el) => {
    const parent = el.parentElement;
    if (!parent) return;
    parent.style.height = "140px";
    parent.style.minHeight = "140px";
  });
  await page.waitForTimeout(200);
  await main.evaluate((node) => {
    node.scrollTop = 0;
  });
  await grid.hover();
  await page.mouse.wheel(0, 30);
  await page.waitForTimeout(50);
  const first = await page.evaluate(() => window.__fbaGridWheel?.target ?? "");
  const mid = await main.evaluate((node) => node.scrollTop);
  if (first === "sheet") {
    expect(mid).toBe(0);
    let target = first;
    for (let i = 0; i < 16 && target !== "page"; i += 1) {
      await page.mouse.wheel(0, 800);
      await page.waitForTimeout(40);
      target = await page.evaluate(() => window.__fbaGridWheel?.target ?? "");
    }
    expect(target).toBe("page");
    expect(await main.evaluate((node) => node.scrollTop)).toBeGreaterThan(0);
    return;
  }
  expect(first).toBe("page");
  expect(mid).toBeGreaterThan(0);
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
  await wheelInsideGrid(page, "match");

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
  await wheelInsideGrid(page, "page");
  await wheelReachesPageAtGridEdge(page);

  await page.getByRole("button", { name: "系统设置" }).click();
  await page.getByTestId("nav-carton").click();
  await expect(page.getByTestId("back-to-workflow")).toBeVisible();
  await page.getByTestId("carton-wizard-open").click();
  await page.getByTestId("carton-next").click();
  await expect(page.getByTestId("carton-step")).toContainText("SKU");
  await expect(page.getByTestId("carton-blocker").first()).toContainText("SKU");
  await expect(page.getByTestId("carton-save")).toHaveCount(0);

  await page.getByTestId("back-to-workflow").click();
  await expect(page.getByTestId("forwarder-select")).toBeVisible();
  await expect(page.locator("[data-sheet-ready='1']")).toBeVisible();
  const selected = await page.getByTestId("forwarder-select").innerText();
  if (!selected.includes("SEND")) {
    await chooseForwarder(page, "SEND（亚马逊 SEND 渠道）");
  }
  expect(await longestTaskAfterSnapshot(page)).toBeLessThan(200);
  await wheelInsideGrid(page, "match");
  expect(external).toEqual([]);
});

function workbookShape(file: string) {
  const python = e2ePython();
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
      expect(slave.status).toBe(200);
      const dir = mkdtempSync(join(tmpdir(), "fba-send-master-"));
      const out = join(dir, "out.xlsx");
      writeFileSync(out, slave.body);
      const placed = JSON.parse(
        execFileSync(
          e2ePython(),
          [
            "-c",
            "import json,sys; from openpyxl import load_workbook; wb=load_workbook(sys.argv[1]); ws=wb.active; print(json.dumps({'C4': ws['C4'].value, 'A4': str(ws['A4'].value)}))",
            out,
          ],
          { encoding: "utf-8" },
        ),
      ) as { C4: string; A4: string };
      expect(placed.C4).toBe("TEST_SLAVE");
      expect(placed.A4).toContain("FBA Shipment ID");
    }
  }
});

test("carton guide buttons are Chinese", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.removeItem("fba_carton_wizard_seen");
  });
  await page.goto("/carton-compare");
  const next = page.locator(".driver-popover-next-btn");
  await expect(next).toBeVisible({ timeout: 15_000 });
  await expect(next).toHaveText("下一步");
  await next.click();
  await expect(page.locator(".driver-popover-prev-btn")).toHaveText("上一步");
  await expect(page.locator(".driver-popover-next-btn")).toHaveText("完成");
});

test("desensitized batch 13 fills step 4.5 then exports", async ({ page }) => {
  test.setTimeout(180_000);
  const csv = [
    '"货件编号","FBA13DS01"',
    '"货件名称","B13-DESENS"',
    '"配送地址","STEP45VILLE, ZZ"',
    '"箱子数量","1"',
    "",
    '"单件商品（1 箱）"',
    '"SKU","商品名称","ASIN","FNSKU","状况","预处理类型","商品总数","箱子 1 的商品数量"',
    '"B13-SKU","rod","B0B13DS001","X00B13E2E1","新品","无","4","4"',
    "",
    '"","","","","","","箱号","FBA13DS01U000001"',
    '"","","","","","","包装箱重量（磅）：","10"',
    '"","","","","","","包装箱长度（英寸）：","17.70"',
    '"","","","","","","包装箱宽度（英寸）：","17.70"',
    '"","","","","","","包装箱高度（英寸）：","16.10"',
  ].join("\n");
  execFileSync(
    e2ePython(),
    [
      "-c",
      `
import json
from fba_tool.master_db import init_master_db, upsert_product
from fba_tool.product_fields import SOURCE_MANUAL, set_product_fields
init_master_db()
upsert_product({
    "sku": "B13-SKU",
    "fnsku": "X00B13E2E1",
    "asin": "B0B13DS001",
    "english_name": "Fishing rod",
    "chinese_name": "鱼竿",
    "brand": "Acme",
    "material": "塑料",
    "purpose": "户外",
    "hs_code": "9507100090",
    "model_name": "型号乙",
    "extra_data": json.dumps({"invoice": {"unit": "个", "purchase_price": 5, "material_en": "plastic", "purpose_en": "outdoor", "pcs_per_set": 1}}, ensure_ascii=False),
})
set_product_fields("B13-SKU", {"listing_price": 12.5, "listing_price_currency": "USD"}, SOURCE_MANUAL)
`,
    ],
    {
      cwd: join("..", "backend"),
      env: {
        ...process.env,
        FBA_APP_DATA_DIR: "/tmp/fba-e2e-data",
        FBA_DISABLE_SCHEDULER: "1",
      },
    },
  );
  const payload = {
    ...FBOX,
    grid_data: {
      ...FBOX.grid_data,
      react_selected_shipment_id: "FBA13DS01",
      step4_shipment_bundle: [
        {
          shipment_id: "FBA13DS01",
          warehouse: "TST1",
          csv_b64: Buffer.from(csv).toString("base64"),
          pdf_b64: Buffer.from("hello").toString("base64"),
        },
      ],
    },
  };
  await openInvoice(page, payload);

  const readCells = (file: string) =>
    JSON.parse(
      execFileSync(
        e2ePython(),
        [
          "-c",
          "import json,sys; from openpyxl import load_workbook; wb=load_workbook(sys.argv[1]); ws=wb.active; print(json.dumps({c: ws[c].value for c in ('C4','K2','H2','I2','E15','A4')}, default=str))",
          file,
        ],
        { encoding: "utf-8" },
      ),
    ) as Record<string, string>;

  await chooseForwarder(page, "琪珞国际");
  await expect(page.getByTestId("invoice-autofill")).toBeEnabled({ timeout: 20_000 });
  const qiluoGen = page.waitForResponse((response) => response.url().includes("/api/invoice/generate"));
  await page.getByTestId("invoice-autofill").click();
  expect((await qiluoGen).status()).toBe(200);
  await expect(page.getByTestId("invoice-autofill")).toBeEnabled();
  const qiluoFile = join(mkdtempSync(join(tmpdir(), "fba-b13-qiluo-")), "out.xlsx");
  const qiluoExport = await exportWorkbook(page);
  expect(qiluoExport.status).toBe(200);
  writeFileSync(qiluoFile, qiluoExport.body);
  const qiluo = readCells(qiluoFile);
  expect(qiluo.K2).toBe("型号乙");
  expect(qiluo.H2).toBe("塑料");
  expect(qiluo.I2).toBe("户外");

  await chooseForwarder(page, "SEND（亚马逊 SEND 渠道）");
  await expect(page.getByTestId("invoice-autofill")).toBeEnabled({ timeout: 20_000 });
  const sendGen = page.waitForResponse((response) => response.url().includes("/api/invoice/generate"));
  await page.getByTestId("invoice-autofill").click();
  expect((await sendGen).status()).toBe(200);
  await expect(page.getByTestId("invoice-autofill")).toBeEnabled();
  const sendFile = join(mkdtempSync(join(tmpdir(), "fba-b13-send-")), "out.xlsx");
  const sendExport = await exportWorkbook(page);
  expect(sendExport.status).toBe(200);
  writeFileSync(sendFile, sendExport.body);
  const send = readCells(sendFile);
  expect(send.C4).toBe("FBA13DS01");
  expect(String(send.A4)).toContain("FBA Shipment ID");
  expect(send.E15).toBe("X00B13E2E1");
});
