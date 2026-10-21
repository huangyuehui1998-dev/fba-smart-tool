/**
 * Univer 开源核心。只通过动态 import 进入页面，避免打进首包。
 * 不设置 workerURL，公式在主线程计算，便携版不访问外网。
 */
import { LocaleType, mergeLocales } from "@univerjs/core";
import { UniverSheetsDataValidationPreset } from "@univerjs/preset-sheets-data-validation";
import { UniverSheetsCorePreset } from "@univerjs/preset-sheets-core";
import { createUniver } from "@univerjs/presets";
import { CalculationMode } from "@univerjs/sheets-formula";
// 预设包把 JS 标成无副作用，Facade 的 FWorksheet.extend 会被摇掉。这里显式引入，getDataValidations 才存在。
import "@univerjs/sheets-data-validation/facade";

import "@univerjs/preset-sheets-core/lib/index.css";
import "@univerjs/preset-sheets-data-validation/lib/index.css";

import dataValidationZh from "@univerjs/preset-sheets-data-validation/locales/zh-CN";
import sheetsZh from "@univerjs/preset-sheets-core/locales/zh-CN";

export interface UniverMount {
  univer: { dispose: () => void };
  univerAPI: {
    dispose: () => void;
    Event: { CommandExecuted: string };
    addEvent: (name: string, cb: (event: { id?: string; params?: unknown }) => void) => { dispose: () => void };
    getActiveWorkbook: () => {
      getId?: () => string;
      getActiveSheet: () => UniverSheet | null;
      save: () => unknown;
    } | null;
    createWorkbook: (data: unknown) => unknown;
    disposeUnit: (unitId: string) => boolean;
  };
}

interface UniverSheet {
  getSheetName?: () => string;
  getRange: (a1: string) => {
    getValue: () => unknown;
    setValue: (value: unknown) => void;
    setBackgroundColor: (color: string) => void;
  };
  getDataValidations?: () => Array<{
    getCriteriaType?: () => string;
    getCriteriaValues?: () => unknown[];
    rule?: { type?: string; formula1?: string };
  }>;
}

let locales: Record<string, unknown> | null = null;

function localeBundle(): Record<string, unknown> {
  if (!locales) {
    const sheets = (sheetsZh as { default?: unknown }).default ?? sheetsZh;
    const validation = (dataValidationZh as { default?: unknown }).default ?? dataValidationZh;
    locales = {
      [LocaleType.ZH_CN]: mergeLocales(sheets as never, validation as never),
    };
  }
  return locales;
}

export function preloadUniverEngine(): void {
  localeBundle();
  window.__fbaUniverPreloaded = true;
}

export function mountUniverShell(container: HTMLElement): UniverMount {
  const { univer, univerAPI } = createUniver({
    locale: LocaleType.ZH_CN,
    locales: localeBundle() as never,
    presets: [
      UniverSheetsCorePreset({
        container,
        header: false,
        toolbar: false,
        formulaBar: false,
        disableAutoFocus: true,
        footer: { sheetBar: true, statisticBar: false, menus: false, zoomSlider: false },
        formula: { initialFormulaComputing: CalculationMode.NO_CALCULATION },
        sheets: { autoHeightForMergedCells: false },
      }),
      UniverSheetsDataValidationPreset(),
    ],
  });
  window.__fbaUniverPreloaded = true;
  return { univer, univerAPI: univerAPI as unknown as UniverMount["univerAPI"] };
}

export function replaceWorkbook(api: UniverMount["univerAPI"], snapshot: unknown): void {
  const unitId = api.getActiveWorkbook()?.getId?.();
  if (unitId) api.disposeUnit(unitId);
  // 交给 Univer 的是副本。它会把合并从属格写回原对象，不能污染导出用的快照。
  const copy = typeof structuredClone === "function" ? structuredClone(snapshot) : JSON.parse(JSON.stringify(snapshot));
  api.createWorkbook(copy as never);
}

export function mountUniver(container: HTMLElement, snapshot: unknown): UniverMount {
  const mount = mountUniverShell(container);
  replaceWorkbook(mount.univerAPI, snapshot);
  return mount;
}

export function activeSheet(api: UniverMount["univerAPI"]): UniverSheet | null {
  return api.getActiveWorkbook()?.getActiveSheet() ?? null;
}

export function publishUniverDebug(api: UniverMount["univerAPI"]): void {
  window.__fbaUniver = {
    getDataValidations: () => activeSheet(api)?.getDataValidations?.() ?? [],
    getCell: (a1: string) => activeSheet(api)?.getRange(a1).getValue() ?? null,
    setCell: (a1: string, value: unknown) => {
      // 命令回调可能晚于 setValue 返回，所以记下用户点的格子，延后清掉。
      const cell = String(a1 || "").replace(/\$/g, "").toUpperCase();
      window.__fbaPendingCell = cell;
      try {
        activeSheet(api)?.getRange(a1).setValue(value);
      } finally {
        window.setTimeout(() => {
          if (window.__fbaPendingCell === cell) window.__fbaPendingCell = undefined;
        }, 0);
      }
    },
  };
}

declare global {
  interface Window {
    __fbaUniverPreloaded?: boolean;
    __fbaUniverShell?: boolean;
    __fbaSnapshotReadyAt?: number;
    __fbaPendingCell?: string;
    __fbaUniver?: {
      getDataValidations: () => unknown;
      getCell: (a1: string) => unknown;
      setCell: (a1: string, value: unknown) => void;
    };
    __fbaGridWheel?: {
      target: "sheet" | "page";
      measurable: boolean;
      scrollOffsetY: number;
      contentHeight: number;
      viewportHeight: number;
    };
  }
}
