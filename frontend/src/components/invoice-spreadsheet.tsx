import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { Loader2 } from "lucide-react";

import { SpreadsheetErrorBoundary } from "@/components/spreadsheet-error-boundary";
import {
  SOURCE_BG_HEX,
  buildClipboardHtmlTable,
  cellMetaFromFills,
  formatCellRef,
  parseCellRef,
  type CellMeta,
  type InvoiceCellFill,
  type Sheet,
} from "@/lib/invoice-spreadsheet";
import { metricsFromUniverSheet, verticalWheelTarget, wheelPixelDelta } from "@/lib/grid-wheel";
import type { UniverMount } from "@/lib/univer-engine";
import { cn } from "@/lib/utils";

export interface InvoiceSpreadsheetHandle {
  loadFile: (file: File) => Promise<void>;
  applyCells: (fills: InvoiceCellFill[]) => void;
  applyCellsAndSyncSheets: (fills: InvoiceCellFill[]) => void;
  resetTemplate: () => void;
  resetAndApplyCells: (fills: InvoiceCellFill[]) => void;
  getCellValue: (cell: string) => string;
  getSnapshot: () => unknown;
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

interface JobBody {
  job_id?: string;
  status?: string;
  progress?: number;
  error?: string;
  result?: { snapshot?: unknown };
  snapshot?: unknown;
}

interface WorkbookSnapshot {
  sheets?: Record<string, SnapshotSheet>;
}

interface SnapshotSheet {
  name?: string;
  cellData?: Record<string, Record<string, Record<string, unknown>>>;
}

interface CellEdit {
  sheet: string;
  cell: string;
  value: string;
}

function normFormula(value: string): string {
  const text = value.trim();
  return text.startsWith("=") ? text.slice(1) : text;
}

function activeSheetName(api: UniverMount["univerAPI"] | null | undefined): string {
  return api?.getActiveWorkbook()?.getActiveSheet()?.getSheetName?.() || "";
}

function overlayEdits(snapshot: WorkbookSnapshot, edits: CellEdit[]): WorkbookSnapshot {
  const sheets = Object.values(snapshot.sheets || {});
  for (const edit of edits) {
    const sheet = sheets.find((item) => item.name === edit.sheet) || sheets[0];
    if (!sheet) continue;
    let pos: { row: number; col: number };
    try {
      pos = parseCellRef(edit.cell);
    } catch {
      continue;
    }
    const cellData = (sheet.cellData ||= {});
    const row = (cellData[String(pos.row)] ||= {});
    const prev = { ...(row[String(pos.col)] || {}) };
    const formula = typeof prev.f === "string" ? prev.f : "";
    if (formula && normFormula(formula) === normFormula(edit.value)) continue;
    delete prev.f;
    prev.v = edit.value;
    row[String(pos.col)] = prev;
  }
  return snapshot;
}

function displayValue(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "object" && value && "v" in value) {
    return displayValue((value as { v?: unknown }).v);
  }
  return String(value);
}

async function readError(response: Response): Promise<string> {
  const text = await response.text();
  try {
    const body = JSON.parse(text) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (body.detail) return JSON.stringify(body.detail);
  } catch {
    // 保留原文
  }
  return text || `表格加载失败（${response.status}）`;
}

export const InvoiceSpreadsheet = forwardRef<InvoiceSpreadsheetHandle, InvoiceSpreadsheetProps>(
  function InvoiceSpreadsheet({ loading = false, className, onReadyChange, onCellEdited, onLoadError }, ref) {
    const hostRef = useRef<HTMLDivElement>(null);
    const mountRef = useRef<UniverMount | null>(null);
    const snapshotRef = useRef<unknown>(null);
    const valuesRef = useRef<Record<string, string>>({});
    const editsRef = useRef<Record<string, CellEdit>>({});
    const cellMetaRef = useRef<Record<string, CellMeta>>({});
    const loadSeq = useRef(0);
    const [ready, setReady] = useState(false);
    const [parsing, setParsing] = useState(false);
    const [progress, setProgress] = useState<number | null>(null);
    const [jobId, setJobId] = useState<string | null>(null);
    const [loadCount, setLoadCount] = useState(0);
    const cancelRef = useRef(false);

    const dispose = useCallback(() => {
      const current = mountRef.current;
      mountRef.current = null;
      window.__fbaUniver = undefined;
      try {
        current?.univerAPI.dispose();
      } catch {
        // 卸载时实例可能已经销毁
      }
      try {
        current?.univer.dispose();
      } catch {
        // 同上
      }
    }, []);

    useEffect(() => () => dispose(), [dispose]);

    useEffect(() => {
      const root = hostRef.current;
      if (!root) return;
      const onWheel = (event: WheelEvent) => {
        const deltaY = wheelPixelDelta(event.deltaY, event.deltaMode, window.innerHeight || 800);
        if (!deltaY) {
          event.preventDefault();
          return;
        }
        const sheet = mountRef.current?.univerAPI.getActiveWorkbook()?.getActiveSheet() ?? null;
        const metrics = metricsFromUniverSheet(sheet, root.clientHeight);
        const target = verticalWheelTarget({ ...metrics, deltaY });
        window.__fbaGridWheel = { target, ...metrics };
        root.dataset.gridWheel = target;
        const scroller = document.querySelector("[data-testid=app-scroll]");
        if (target === "page" && scroller instanceof HTMLElement) {
          const max = Math.max(0, scroller.scrollHeight - scroller.clientHeight);
          const next = Math.min(max, Math.max(0, scroller.scrollTop + deltaY));
          event.preventDefault();
          if (next !== scroller.scrollTop) scroller.scrollTop = next;
          return;
        }
        event.preventDefault();
      };
      root.addEventListener("wheel", onWheel, { capture: true, passive: false });
      return () => root.removeEventListener("wheel", onWheel, { capture: true });
    }, [ready, loadCount]);

    const paint = useCallback(
      async (snapshot: unknown) => {
        const host = hostRef.current;
        if (!host) throw new Error("表格容器还没准备好");
        const engine = await import("@/lib/univer-engine");
        dispose();
        host.replaceChildren();
        const mount = engine.mountUniver(host, snapshot);
        mountRef.current = mount;
        engine.publishUniverDebug(mount.univerAPI);
        snapshotRef.current = snapshot;
        mount.univerAPI.addEvent(mount.univerAPI.Event.CommandExecuted, (event) => {
          if (!String(event.id || "").includes("set-range-values")) return;
          const params = event.params as { range?: { startRow?: number; startColumn?: number }; value?: unknown } | undefined;
          const row = params?.range?.startRow;
          const col = params?.range?.startColumn;
          if (row == null || col == null) return;
          const pending = window.__fbaPendingCell;
          const cell = pending || formatCellRef(row, col);
          const text = displayValue(params?.value);
          valuesRef.current[cell] = text;
          const sheet = activeSheetName(mount.univerAPI);
          editsRef.current[`${sheet}!${cell}`] = { sheet, cell, value: text };
          const meta = cellMetaRef.current[cell];
          if (meta?.source === "missing" && text.trim()) {
            cellMetaRef.current = { ...cellMetaRef.current, [cell]: { ...meta, source: "exact" } };
          }
          onCellEdited?.(cell, text);
        });
      },
      [dispose, onCellEdited],
    );

    const markReady = useCallback(() => {
      setReady(true);
      onReadyChange?.(true);
    }, [onReadyChange]);

    const pollJob = useCallback(async (id: string, seq: number): Promise<unknown> => {
      for (;;) {
        if (cancelRef.current || seq !== loadSeq.current) throw new Error("已取消加载");
        const response = await fetch(`/api/jobs/${id}`);
        if (!response.ok) throw new Error(await readError(response));
        const body = (await response.json()) as JobBody;
        setProgress(typeof body.progress === "number" ? body.progress : 0);
        if (body.status === "done") return body.result?.snapshot;
        if (body.status === "failed") throw new Error(body.error || "表格转换失败");
        if (body.status === "cancelled") throw new Error("已取消加载");
        await new Promise((resolve) => window.setTimeout(resolve, 300));
      }
    }, []);

    const loadFile = useCallback(
      async (file: File) => {
        const seq = loadSeq.current + 1;
        loadSeq.current = seq;
        cancelRef.current = false;
        setLoadCount((count) => count + 1);
        setReady(false);
        setParsing(true);
        setProgress(null);
        setJobId(null);
        onReadyChange?.(false);
        valuesRef.current = {};
        editsRef.current = {};
        cellMetaRef.current = {};
        try {
          const body = new FormData();
          body.append("file", file);
          const response = await fetch("/api/univer/snapshot?clamp=true", { method: "POST", body });
          window.__fbaSnapshotReadyAt = performance.now();
          if (seq !== loadSeq.current) return;
          if (response.status === 202) {
            const job = (await response.json()) as JobBody;
            if (!job.job_id) throw new Error("后台任务没有编号");
            setJobId(job.job_id);
            setProgress(job.progress ?? 0);
            const snapshot = await pollJob(job.job_id, seq);
            if (seq !== loadSeq.current) return;
            await paint(snapshot);
          } else if (!response.ok) {
            throw new Error(await readError(response));
          } else {
            const payload = (await response.json()) as JobBody;
            await paint(payload.snapshot);
          }
          if (seq === loadSeq.current) markReady();
        } catch (err) {
          const message = err instanceof Error ? err.message : "模板解析失败";
          onLoadError?.(message);
          throw err;
        } finally {
          if (seq === loadSeq.current) {
            setParsing(false);
            setProgress(null);
            setJobId(null);
          }
        }
      },
      [markReady, onLoadError, onReadyChange, paint, pollJob],
    );

    const readCell = useCallback((cell: string): string => {
      const upper = cell.toUpperCase();
      if (upper in valuesRef.current) return valuesRef.current[upper] ?? "";
      try {
        const api = mountRef.current?.univerAPI;
        if (!api) return "";
        const sheet = api.getActiveWorkbook()?.getActiveSheet();
        return displayValue(sheet?.getRange(upper).getValue());
      } catch {
        return "";
      }
    }, []);

    const writeFill = useCallback((fill: InvoiceCellFill) => {
      if (!fill.cell) return;
      const upper = fill.cell.toUpperCase();
      const text = fill.value == null ? "" : String(fill.value);
      valuesRef.current[upper] = text;
      const api = mountRef.current?.univerAPI;
      const sheetName = activeSheetName(api);
      editsRef.current[`${sheetName}!${upper}`] = { sheet: sheetName, cell: upper, value: text };
      const sheet = api?.getActiveWorkbook()?.getActiveSheet();
      if (!sheet) return;
      const source = cellMetaRef.current[upper]?.source ?? "preview";
      try {
        sheet.getRange(upper).setValue(text);
        if (!fill.clear && text) sheet.getRange(upper).setBackgroundColor(SOURCE_BG_HEX[source]);
      } catch {
        // 非法单元格引用跳过
      }
    }, []);

    const applyCells = useCallback(
      (fills: InvoiceCellFill[]) => {
        cellMetaRef.current = cellMetaFromFills(fills);
        for (const fill of fills) writeFill(fill);
      },
      [writeFill],
    );

    const applyCellsAndSyncSheets = useCallback(
      (fills: InvoiceCellFill[]) => {
        applyCells(fills);
      },
      [applyCells],
    );

    const resetTemplate = useCallback(() => {
      cellMetaRef.current = {};
      valuesRef.current = {};
      editsRef.current = {};
      if (snapshotRef.current) void paint(snapshotRef.current).then(() => markReady());
    }, [markReady, paint]);

    const resetAndApplyCells = useCallback(
      (fills: InvoiceCellFill[]) => {
        cellMetaRef.current = cellMetaFromFills(fills);
        valuesRef.current = {};
        editsRef.current = {};
        const apply = () => applyCells(fills);
        if (snapshotRef.current) {
          void paint(snapshotRef.current).then(() => {
            apply();
            markReady();
          });
          return;
        }
        apply();
      },
      [applyCells, markReady, paint],
    );

    const copyToClipboard = useCallback(async () => {
      const sheet = (Array.isArray((snapshotRef.current as { sheets?: unknown })?.sheets)
        ? null
        : Object.values(((snapshotRef.current as { sheets?: Record<string, Sheet> })?.sheets) || {})[0]) as
        | (Sheet & { mergeData?: { startRow: number; endRow: number; startColumn: number; endColumn: number }[] })
        | undefined;
      const rowCount = Math.min(Number(sheet?.rowCount ?? 40), 80);
      const colCount = Math.min(Number(sheet?.columnCount ?? 16), 30);
      const merges = (sheet?.mergeData ?? []).map((item) => ({
        r: item.startRow,
        c: item.startColumn,
        rs: item.endRow - item.startRow + 1,
        cs: item.endColumn - item.startColumn + 1,
      }));
      const html = buildClipboardHtmlTable((row, col) => readCell(formatCellRef(row, col)), {
        rowCount,
        colCount,
        merges,
      });
      const plain = Array.from({ length: rowCount }, (_, row) =>
        Array.from({ length: colCount }, (_, col) => readCell(formatCellRef(row, col))).join("\t"),
      )
        .filter((line) => line.trim())
        .join("\n");
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
    }, [readCell]);

    const getSnapshot = useCallback(() => {
      const base = snapshotRef.current;
      if (!base || typeof base !== "object") return null;
      const cloned = structuredClone(base) as WorkbookSnapshot;
      return overlayEdits(cloned, Object.values(editsRef.current));
    }, []);

    const cancelJob = useCallback(() => {
      cancelRef.current = true;
      if (jobId) void fetch(`/api/jobs/${jobId}/cancel`, { method: "POST" });
    }, [jobId]);

    useImperativeHandle(
      ref,
      () => ({
        loadFile,
        applyCells,
        applyCellsAndSyncSheets,
        resetTemplate,
        resetAndApplyCells,
        getCellValue: readCell,
        getSnapshot,
        isReady: () => ready,
        copyToClipboard,
      }),
      [applyCells, applyCellsAndSyncSheets, copyToClipboard, getSnapshot, loadFile, readCell, ready, resetAndApplyCells, resetTemplate],
    );

    return (
      <SpreadsheetErrorBoundary onError={(error) => onLoadError?.(error.message)}>
        <div
          className={cn(
            "relative h-[46vh] min-h-[320px] overflow-hidden rounded-lg border border-border bg-card shadow-sm",
            className,
          )}
          data-sheet-ready={ready ? "1" : "0"}
          data-sheet-load={loadCount}
        >
          <div ref={hostRef} data-testid="data-univer-grid" data-univer-grid="" className="h-full w-full overscroll-contain" />
          {(loading || parsing) && (
            <div className="absolute inset-0 z-30 flex items-center justify-center bg-background/70">
              <div className="flex w-64 flex-col items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                <span>{parsing ? "正在加载表格…" : "正在自动填写单元格…"}</span>
                {progress != null && (
                  <div className="w-full" data-testid="snapshot-progress">
                    <div className="h-2 overflow-hidden rounded bg-muted">
                      <div className="h-full bg-primary" style={{ width: `${Math.max(4, progress)}%` }} />
                    </div>
                    <p className="mt-1 text-center text-xs">{progress}%</p>
                    {jobId && (
                      <button type="button" className="mt-1 text-xs underline" data-testid="snapshot-cancel" onClick={cancelJob}>
                        取消
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
          {!ready && !parsing && (
            <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center bg-card/85 text-sm text-muted-foreground">
              选择货代后，将在此预览发票模板
            </div>
          )}
        </div>
      </SpreadsheetErrorBoundary>
    );
  },
);
