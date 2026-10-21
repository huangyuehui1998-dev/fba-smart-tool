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
