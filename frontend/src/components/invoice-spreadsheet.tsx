import {

  forwardRef,

  useCallback,

  useEffect,

  useImperativeHandle,

  useRef,

  useState,

} from "react";

import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

import type { InvoiceCellFill } from "@/lib/invoice-spreadsheet";

import {

  SOURCE_BG_HEX,

  applyFillsToSheets,

  buildClipboardHtmlTable,

  cellMetaFromFills,

  cloneSheets,

  formatCellRef,

  parseCellRef,

  type CellMeta,

  type CellSourceKind,

} from "@/lib/invoice-spreadsheet";

import {

  createEmptyFortuneSheet,

  isBrowser,

  normalizeFortuneSheets,

} from "@/lib/fortune-sheet-normalize";

import { SpreadsheetErrorBoundary } from "@/components/spreadsheet-error-boundary";

import "@fortune-sheet/react/dist/index.css";

import "@/styles/invoice-fortune-sheet.css";



import type { WorkbookInstance } from "@fortune-sheet/react";

import type { Sheet } from "@fortune-sheet/core";



const AUDIT_WORKBOOK_SETTINGS = {

  showToolbar: false,

  showFormulaBar: false,

  showSheetTabs: false,

  allowEdit: true,

} as const;



export interface InvoiceSpreadsheetHandle {

  loadFile: (file: File) => Promise<void>;

  applyCells: (fills: InvoiceCellFill[]) => void;

  /** 在已加载模板上直接写入单元格，并同步内部 sheet 快照（不重挂载） */
  applyCellsAndSyncSheets: (fills: InvoiceCellFill[]) => void;

  resetTemplate: () => void;

  /** 重置为模板快照并合并填充数据，单次重挂载避免竞态丢值 */
  resetAndApplyCells: (fills: InvoiceCellFill[]) => void;

  getCellValue: (cell: string) => string;

  isReady: () => boolean;

  copyToClipboard: () => Promise<void>;

}



interface InvoiceSpreadsheetProps {

  loading?: boolean;

  className?: string;

  onReadyChange?: (ready: boolean) => void;

  onCellEdited?: (cell: string, value: string) => void;

  onLoadError?: (message: string) => void;

}



type WorkbookComponent = typeof import("@fortune-sheet/react").Workbook;



function applySheetDimensions(api: WorkbookInstance | null, sheetList: Sheet[]) {

  if (!api) return;

  for (const sheet of sheetList) {

    const config = sheet.config;

    api.setColumnWidth?.((config?.columnlen as Record<string, number>) || {}, { id: sheet.id });

    api.setRowHeight?.((config?.rowlen as Record<string, number>) || {}, { id: sheet.id });

  }

}



function FortuneWorkbookHost({

  Workbook,

  sheets,

  workbookKey,

  sheetRef,

  onCellEdited,

  onWorkbookChange,

}: {

  Workbook: WorkbookComponent;

  sheets: Sheet[];

  workbookKey: number;

  sheetRef: React.RefObject<WorkbookInstance | null>;

  onCellEdited?: (row: number, col: number, oldValue: unknown, newValue: unknown) => void;

  onWorkbookChange?: () => void;

}) {

  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {

    const root = hostRef.current;

    if (!root) return;

    const onWheel = (e: WheelEvent) => {

      const xBar = root.querySelector<HTMLElement>(".luckysheet-scrollbar-x");

      if (!xBar) return;

      if (e.shiftKey && e.deltaY !== 0) {

        xBar.scrollLeft += e.deltaY;

        e.preventDefault();

        e.stopPropagation();

      }

    };

    root.addEventListener("wheel", onWheel, { passive: false, capture: true });

    return () => root.removeEventListener("wheel", onWheel, { capture: true });

  }, [workbookKey]);

  return (

    <div ref={hostRef} className="invoice-fortune-sheet-host h-full w-full min-h-0 min-w-0">

      <Workbook

        key={workbookKey}

        ref={sheetRef}

        data={sheets}

        {...AUDIT_WORKBOOK_SETTINGS}

        hooks={{ afterUpdateCell: onCellEdited }}

        onChange={onWorkbookChange}

      />

    </div>

  );

}



export const InvoiceSpreadsheet = forwardRef<InvoiceSpreadsheetHandle, InvoiceSpreadsheetProps>(

  function InvoiceSpreadsheet(

    { loading = false, className, onReadyChange, onCellEdited, onLoadError },

    ref,

  ) {

    const sheetRef = useRef<WorkbookInstance>(null);

    const snapshotRef = useRef<Sheet[]>([]);

    const latestSheetsRef = useRef<Sheet[]>(createEmptyFortuneSheet());

    const cellMetaRef = useRef<Record<string, CellMeta>>({});

    const [mounted, setMounted] = useState(false);

    const [Workbook, setWorkbook] = useState<WorkbookComponent | null>(null);

    const [sheets, setSheets] = useState<Sheet[]>(() => createEmptyFortuneSheet());

    const [workbookKey, setWorkbookKey] = useState(0);

    const [ready, setReady] = useState(false);

    const [hasTemplateData, setHasTemplateData] = useState(false);

    const [parsing, setParsing] = useState(false);



    useEffect(() => {

      setMounted(true);

    }, []);



    useEffect(() => {

      if (!mounted || !isBrowser()) return;

      let cancelled = false;

      void import("@fortune-sheet/react").then((mod) => {

        if (!cancelled) setWorkbook(() => mod.Workbook);

      });

      return () => {

        cancelled = true;

      };

    }, [mounted]);



    const markReady = useCallback(

      (next: Sheet[]) => {

        snapshotRef.current = cloneSheets(next);

        latestSheetsRef.current = next;

        setHasTemplateData(true);

        setReady(true);

        onReadyChange?.(true);

      },

      [onReadyChange],

    );



    const loadFile = useCallback(

      async (file: File) => {

        if (!isBrowser()) {

          throw new Error("表格引擎仅支持在浏览器中运行");

        }

        if (!Workbook) {

          throw new Error("表格引擎尚未就绪，请稍后重试");

        }



        setReady(false);

        setHasTemplateData(false);

        setParsing(true);

        onReadyChange?.(false);

        cellMetaRef.current = {};



        try {

          const { transformExcelToFortune } = await import("@corbe30/fortune-excel");

          let parsedSheets: Sheet[] = [];



          await transformExcelToFortune(

            file,

            (next: Parameters<typeof normalizeFortuneSheets>[0]) => {

              parsedSheets = normalizeFortuneSheets(next);

              latestSheetsRef.current = parsedSheets;

              setSheets(parsedSheets);

            },

            () => {

              setWorkbookKey((k) => k + 1);

            },

            sheetRef,

          );



          markReady(parsedSheets);

        } catch (err) {

          const message = err instanceof Error ? err.message : "模板解析失败";

          onLoadError?.(message);

          throw err;

        } finally {

          setParsing(false);

        }

      },

      [Workbook, markReady, onLoadError, onReadyChange],

    );



    useEffect(() => {

      if (!hasTemplateData || !sheets.length) return;

      const timer = window.setTimeout(() => {

        applySheetDimensions(sheetRef.current, sheets);

      }, 0);

      return () => window.clearTimeout(timer);

    }, [hasTemplateData, sheets, workbookKey]);



    const getCellValue = useCallback((cell: string): string => {

      const api = sheetRef.current;

      if (!api) return "";

      try {

        const { row, col } = parseCellRef(cell);

        const val = api.getCellValue(row, col, { type: "m" });

        if (val == null) return "";

        return String(val);

      } catch {

        return "";

      }

    }, []);



    const applyCells = useCallback((fills: InvoiceCellFill[]) => {

      const api = sheetRef.current;

      if (!api) return;



      cellMetaRef.current = cellMetaFromFills(fills);



      for (const fill of fills) {

        if (!fill.cell) continue;

        try {

          const { row, col } = parseCellRef(fill.cell);

          const source = cellMetaRef.current[fill.cell.toUpperCase()]?.source ?? "preview";

          if (fill.value === "" || fill.value == null) {
            api.setCellValue(row, col, "");
          } else {
            api.setCellValue(row, col, fill.value);
          }

          if (!fill.clear) {
            api.setCellFormat(row, col, "bg", SOURCE_BG_HEX[source]);
          }

        } catch {

          // skip invalid refs

        }

      }

    }, []);



    const resetTemplate = useCallback(() => {

      cellMetaRef.current = {};

      if (!snapshotRef.current.length) return;

      setSheets(cloneSheets(snapshotRef.current));

      setWorkbookKey((k) => k + 1);

    }, []);



    const applyCellsAndSyncSheets = useCallback(
      (fills: InvoiceCellFill[]) => {
        cellMetaRef.current = cellMetaFromFills(fills);
        if (snapshotRef.current.length) {
          latestSheetsRef.current = applyFillsToSheets(snapshotRef.current, fills);
        }
        applyCells(fills);
      },
      [applyCells],
    );



    const resetAndApplyCells = useCallback((fills: InvoiceCellFill[]) => {

      cellMetaRef.current = cellMetaFromFills(fills);

      if (!snapshotRef.current.length) return;

      const merged = applyFillsToSheets(snapshotRef.current, fills);

      latestSheetsRef.current = merged;

      setSheets(merged);

      setWorkbookKey((k) => k + 1);

    }, []);



    const copyToClipboard = useCallback(async () => {

      const api = sheetRef.current;

      const sheet = latestSheetsRef.current[0];

      if (!api || !sheet) {

        throw new Error("表格尚未加载");

      }

      const rowCount = Math.min(Number(sheet.row ?? 60), 200);

      const colCount = Math.min(Number(sheet.column ?? 20), 40);

      const merges = (sheet.config?.merge ?? []) as {

        r: number;

        c: number;

        rs: number;

        cs: number;

      }[];

      const columnWidths = (sheet.config?.columnlen ?? {}) as Record<string, number>;

      const read = (r: number, c: number) => {

        const val = api.getCellValue(r, c, { type: "m" });

        return val == null ? "" : String(val);

      };

      const html = buildClipboardHtmlTable(read, {

        rowCount,

        colCount,

        merges,

        columnWidths,

      });

      const plainRows: string[] = [];

      for (let r = 0; r < rowCount; r += 1) {

        const cols: string[] = [];

        for (let c = 0; c < colCount; c += 1) {

          cols.push(read(r, c));

        }

        if (cols.some((v) => v.trim())) plainRows.push(cols.join("\t"));

      }

      const plain = plainRows.join("\n");

      if (navigator.clipboard?.write && typeof ClipboardItem !== "undefined") {

        await navigator.clipboard.write([

          new ClipboardItem({

            "text/html": new Blob([html], { type: "text/html" }),

            "text/plain": new Blob([plain], { type: "text/plain" }),

          }),

        ]);

      } else {

        await navigator.clipboard.writeText(plain);

      }

    }, []);



    const handleCellEdited = useCallback(

      (row: number, col: number, _oldValue: unknown, newValue: unknown) => {

        const cell = formatCellRef(row, col);

        const meta = cellMetaRef.current[cell];

        if (meta && String(newValue ?? "").trim() && meta.source === "missing") {

          cellMetaRef.current = {

            ...cellMetaRef.current,

            [cell]: { ...meta, source: "exact" as CellSourceKind },

          };

          sheetRef.current?.setCellFormat(row, col, "bg", SOURCE_BG_HEX.exact);

        }

        onCellEdited?.(cell, String(newValue ?? ""));

      },

      [onCellEdited],

    );



    useImperativeHandle(

      ref,

      () => ({

        loadFile,

        applyCells,

        applyCellsAndSyncSheets,

        resetTemplate,

        resetAndApplyCells,

        getCellValue,

        isReady: () => ready,

        copyToClipboard,

      }),

      [
        applyCells,
        applyCellsAndSyncSheets,
        copyToClipboard,
        getCellValue,
        loadFile,
        ready,
        resetAndApplyCells,
        resetTemplate,
      ],

    );



    if (!mounted) {

      return (

        <div className="flex h-[min(72vh,720px)] min-h-[480px] items-center justify-center rounded-lg border border-border bg-card">

          <Loader2 className="h-6 w-6 animate-spin text-primary" />

        </div>

      );

    }



    return (

      <SpreadsheetErrorBoundary
        resetKey={workbookKey}

        onError={(error) => {

          onLoadError?.(error.message);

          setHasTemplateData(false);

          setReady(false);

          onReadyChange?.(false);

        }}

      >

        <div

          className={cn(

            "invoice-fortune-sheet relative h-[min(72vh,720px)] min-h-[480px] overflow-auto rounded-lg border border-border bg-card shadow-sm",

            className,

          )}

        >

          {(loading || parsing) && (

            <div className="absolute inset-0 z-30 flex items-center justify-center bg-background/70 backdrop-blur-[1px]">

              <div className="flex flex-col items-center gap-2 text-sm text-muted-foreground">

                <Loader2 className="h-8 w-8 animate-spin text-primary" />

                <span>{parsing ? "正在解析 Excel 格式…" : "正在自动填写单元格…"}</span>

              </div>

            </div>

          )}



          {!Workbook ? (

            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">

              <Loader2 className="mr-2 h-5 w-5 animate-spin text-primary" />

              正在加载表格引擎…

            </div>

          ) : (

            <FortuneWorkbookHost

              Workbook={Workbook}

              sheets={sheets}

              workbookKey={workbookKey}

              sheetRef={sheetRef}

              onCellEdited={handleCellEdited}

              onWorkbookChange={() =>

                applySheetDimensions(sheetRef.current, latestSheetsRef.current)

              }

            />

          )}



          {!hasTemplateData && !parsing && Workbook && (

            <div className="pointer-events-none absolute inset-0 z-20 flex flex-col items-center justify-center gap-2 bg-card/85 px-6 text-center text-sm text-muted-foreground">

              <p>选择货代后，将在此以 Excel 原样排版预览</p>

              <p className="text-[11px]">支持合并单元格、边框与列宽</p>

            </div>

          )}

        </div>

      </SpreadsheetErrorBoundary>

    );

  },

);


