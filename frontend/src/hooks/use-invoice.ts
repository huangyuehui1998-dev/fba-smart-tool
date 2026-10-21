import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import type { InvoiceSpreadsheetHandle } from "@/components/invoice-spreadsheet";
import { useWorkflow } from "@/context/workflow-context";
import { formatApiError } from "@/lib/format-api-error";
import { fileToBase64 } from "@/lib/box-editor";
import { exportInvoice, fillInvoice } from "@/lib/api/workflow";
import {
  createForwarder,
  fetchForwarderTemplateBlob,
  fetchForwarders,
  type ForwarderProfile,
} from "@/lib/api/forwarders";
import {
  buildExportFieldsForInvoiceExport,
  cellMetaFromFills,
  missingRequiredFromCellMeta,
  type CellMeta,
} from "@/lib/invoice-spreadsheet";
import {
  draftWithLiveSpreadsheetCells,
  mergeSessions,
  skuForCellRow,
  syncDraftCellValue,
  type SheetPhase,
  type ShipmentInvoiceSession,
} from "@/lib/invoice-session";
import { sha256HexFromFile } from "@/lib/file-hash";
import { rowToApi } from "@/lib/step1-rows";
import { isOfficialExportBlocked, STALE_DOWNLOAD_HINT } from "@/lib/workflow-invalidation";

export type { SheetPhase };

const PO_STORAGE_KEY = "fba_invoice_po_by_shipment";

async function waitForSpreadsheet(
  ref: React.RefObject<InvoiceSpreadsheetHandle | null>,
  maxMs = 10000,
) {
  const start = Date.now();
  while (!ref.current && Date.now() - start < maxMs) {
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  if (!ref.current) {
    throw new Error("表格引擎尚未就绪，请稍后重试");
  }
}

function loadPoMap(): Record<string, string> {
  try {
    const raw = localStorage.getItem(PO_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Record<string, string>) : {};
  } catch {
    return {};
  }
}

function savePoForShipment(shipmentId: string, po: string) {
  const map = loadPoMap();
  if (po.trim()) {
    map[shipmentId] = po.trim();
  } else {
    delete map[shipmentId];
  }
  localStorage.setItem(PO_STORAGE_KEY, JSON.stringify(map));
}

/**
 * Step 4.5：货代选择、货件面板、PO 手填、工作流自动填写、跨货件联动编辑、导出。
 */
export function useInvoice() {
  const {
    shipments,
    step4Ok,
    selectedShipmentId,
    setSelectedShipmentId,
    invoiceDraft,
    setInvoiceDraft,
    invoiceTemplateBase64,
    setInvoiceTemplateBase64,
    invoiceSessionsByShipment,
    setInvoiceSessionsByShipment,
    invoiceForwarderId,
    setInvoiceForwarderId,
    invoicePoByShipment,
    setInvoicePoByShipment,
    invoiceSyncLinkedEdits,
    setInvoiceSyncLinkedEdits,
    registerSnapshotFlush,
    taskId,
    inputRows,
    boxEditorApi,
    forwarder,
    staleness,
    clearStageStale,
  } = useWorkflow();

  const spreadsheetRef = useRef<InvoiceSpreadsheetHandle>(null);
  const bootedRef = useRef(false);
  const lastRestoredKeyRef = useRef("");
  const [sheetPhase, setSheetPhase] = useState<SheetPhase>("idle");
  const [cellMeta, setCellMeta] = useState<Record<string, CellMeta>>({});
  const [templateReady, setTemplateReady] = useState(false);
  const [templateSheetName, setTemplateSheetName] = useState("发票");
  const [parsing, setParsing] = useState(false);
  const [filling, setFilling] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [copying, setCopying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [invoiceTemplateHash, setInvoiceTemplateHash] = useState<string | null>(null);
  const [revenueTon, setRevenueTon] = useState<number | null>(null);

  const [forwarders, setForwarders] = useState<ForwarderProfile[]>([]);
  const [forwardersLoading, setForwardersLoading] = useState(true);
  const selectedForwarderId = invoiceForwarderId;
  const setSelectedForwarderId = setInvoiceForwarderId;
  const syncLinkedEdits = invoiceSyncLinkedEdits;
  const setSyncLinkedEdits = setInvoiceSyncLinkedEdits;
  const poNumber = selectedShipmentId ? (invoicePoByShipment[selectedShipmentId] ?? "") : "";
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [savingForwarder, setSavingForwarder] = useState(false);

  const validatedShipments = useMemo(
    () => (step4Ok ? shipments : []),
    [step4Ok, shipments],
  );

  const selected = validatedShipments.find((s) => s.shipment_id === selectedShipmentId);
  const selectedForwarder = forwarders.find((f) => f.id === selectedForwarderId);
  const gridLoading = filling;
  const hasTemplate = templateReady;
  const canAutoFill = Boolean(
    selectedForwarderId && hasTemplate && selected && !gridLoading && !parsing,
  );

  const filledShipmentIds = useMemo(
    () =>
      validatedShipments
        .filter((s) => invoiceSessionsByShipment[s.shipment_id]?.sheetPhase === "filled")
        .map((s) => s.shipment_id),
    [validatedShipments, invoiceSessionsByShipment],
  );

  const getCellValue = useCallback(
    (cell: string) => spreadsheetRef.current?.getCellValue(cell) ?? "",
    [],
  );

  const missingLabels =
    sheetPhase === "filled" ? missingRequiredFromCellMeta(cellMeta, getCellValue, invoiceDraft?.cells) : [];
  const hasMissing = missingLabels.length > 0;

  const buildWorkflowJson = useCallback(() => {
    return {
      input_rows: inputRows.filter((r) => r.sku.trim()).map((r) => rowToApi(r)),
      box_editor: boxEditorApi,
      forwarder,
    };
  }, [inputRows, boxEditorApi, forwarder]);

  const persistCurrentSession = useCallback(
    (shipmentId: string, opts?: { flushSpreadsheet?: boolean }) => {
      if (!shipmentId) return;
      let draft = invoiceDraft;
      let meta = cellMeta;
      let ton = revenueTon;
      let phase = sheetPhase;
      if (shipmentId === selectedShipmentId && opts?.flushSpreadsheet && draft && phase === "filled") {
        const getValue = (cell: string) => spreadsheetRef.current?.getCellValue(cell) ?? "";
        draft = draftWithLiveSpreadsheetCells(draft, cellMeta, getValue);
        meta = cellMeta;
        ton = revenueTon;
        phase = sheetPhase;
        setInvoiceDraft(draft);
      }
      setInvoiceSessionsByShipment((prev) =>
        mergeSessions(prev, shipmentId, {
          draft: shipmentId === selectedShipmentId ? draft : prev[shipmentId]?.draft ?? null,
          cellMeta: shipmentId === selectedShipmentId ? meta : prev[shipmentId]?.cellMeta ?? {},
          revenueTon: shipmentId === selectedShipmentId ? ton : prev[shipmentId]?.revenueTon ?? null,
          sheetPhase: shipmentId === selectedShipmentId ? phase : prev[shipmentId]?.sheetPhase ?? "idle",
        }),
      );
    },
    [
      invoiceDraft,
      cellMeta,
      revenueTon,
      sheetPhase,
      selectedShipmentId,
      setInvoiceSessionsByShipment,
      setInvoiceDraft,
    ],
  );

  const flushForSnapshot = useCallback(() => {
    if (selectedShipmentId) {
      persistCurrentSession(selectedShipmentId, { flushSpreadsheet: true });
    }
  }, [selectedShipmentId, persistCurrentSession]);

  useEffect(() => registerSnapshotFlush(flushForSnapshot), [registerSnapshotFlush, flushForSnapshot]);

  const restoreSession = useCallback(
    async (session: ShipmentInvoiceSession | undefined) => {
      if (!session?.draft || session.sheetPhase !== "filled") {
        spreadsheetRef.current?.resetTemplate();
        setCellMeta({});
        setSheetPhase(templateReady ? "preview" : "idle");
        setInvoiceDraft(null);
        setRevenueTon(null);
        return;
      }
      setInvoiceDraft(session.draft);
      setCellMeta(session.cellMeta);
      setRevenueTon(session.revenueTon);
      setSheetPhase("filled");
      await waitForSpreadsheet(spreadsheetRef);
      const dataCells = session.draft.cells.filter((c) => !c.clear);
      spreadsheetRef.current?.resetAndApplyCells(dataCells);
    },
    [setInvoiceDraft, templateReady],
  );

  const loadForwarderTemplate = useCallback(
    async (forwarderId: string, profile?: ForwarderProfile) => {
      setParsing(true);
      setError(null);
      try {
        const blob = await fetchForwarderTemplateBlob(forwarderId);
        const fileName = profile?.template_file ?? `${forwarderId}.xlsx`;
        const file = new File([blob], fileName, {
          type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        });
        const b64 = await fileToBase64(file);
        const templateHash = await sha256HexFromFile(file);
        await waitForSpreadsheet(spreadsheetRef);
        await spreadsheetRef.current?.loadFile(file);
        setTemplateSheetName(profile?.name ?? "发票");
        setInvoiceTemplateBase64(b64);
        setInvoiceTemplateHash(templateHash);
        const session = selectedShipmentId
          ? invoiceSessionsByShipment[selectedShipmentId]
          : undefined;
        if (session?.sheetPhase === "filled" && session.draft) {
          await restoreSession(session);
        } else {
          setCellMeta({});
          setSheetPhase("preview");
          setInvoiceDraft(null);
          setRevenueTon(null);
        }
      } catch (err) {
        setTemplateReady(false);
        setError(formatApiError(err));
      } finally {
        setParsing(false);
      }
    },
    [
      setInvoiceDraft,
      setInvoiceTemplateBase64,
      selectedShipmentId,
      invoiceSessionsByShipment,
      restoreSession,
    ],
  );

  useEffect(() => {
    if (bootedRef.current) return;
    bootedRef.current = true;
    let cancelled = false;
    const boot = async () => {
      setForwardersLoading(true);
      try {
        const res = await fetchForwarders();
        if (cancelled) return;
        setForwarders(res.forwarders);
        const defaultId =
          invoiceForwarderId ||
          res.forwarders.find((f) => f.id === "qiluo")?.id ||
          res.forwarders[0]?.id ||
          "";
        if (!defaultId) return;
        if (!invoiceForwarderId) setSelectedForwarderId(defaultId);
        const profile = res.forwarders.find((f) => f.id === (invoiceForwarderId || defaultId));
        const loadId = invoiceForwarderId || defaultId;
        const blob = await fetchForwarderTemplateBlob(loadId);
        if (cancelled) return;
        const fileName = profile?.template_file ?? `${defaultId}.xlsx`;
        const file = new File([blob], fileName, {
          type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        });
        const b64 = await fileToBase64(file);
        const templateHash = await sha256HexFromFile(file);
        setParsing(true);
        await waitForSpreadsheet(spreadsheetRef);
        await spreadsheetRef.current?.loadFile(file);
        if (cancelled) return;
        setTemplateSheetName(profile?.name ?? "发票");
        setInvoiceTemplateBase64(b64);
        setInvoiceTemplateHash(templateHash);
        const sid = selectedShipmentId || validatedShipments[0]?.shipment_id || "";
        if (sid && !selectedShipmentId) setSelectedShipmentId(sid);
        const session = sid ? invoiceSessionsByShipment[sid] : undefined;
        if (session?.sheetPhase === "filled" && session.draft) {
          setCellMeta(session.cellMeta);
          setRevenueTon(session.revenueTon);
          setSheetPhase("filled");
          setInvoiceDraft(session.draft);
          const dataCells = session.draft.cells.filter((c) => !c.clear);
          spreadsheetRef.current?.resetAndApplyCells(dataCells);
        } else {
          setCellMeta({});
          setSheetPhase("preview");
        }
      } catch (err) {
        if (!cancelled) setError(formatApiError(err));
      } finally {
        if (!cancelled) {
          setForwardersLoading(false);
          setParsing(false);
        }
      }
    };
    void boot();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!bootedRef.current || !selectedShipmentId) return;
    const restoreKey = `${taskId}:${selectedShipmentId}`;
    if (lastRestoredKeyRef.current === restoreKey) return;
    const session = invoiceSessionsByShipment[selectedShipmentId];
    if (session?.sheetPhase === "filled" && session.draft) {
      lastRestoredKeyRef.current = restoreKey;
      void restoreSession(session);
    }
    // fbox / 历史任务恢复后回填当前货件发票
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId, selectedShipmentId, invoiceSessionsByShipment]);

  useEffect(() => {
    if (!selectedShipmentId && validatedShipments[0]?.shipment_id) {
      setSelectedShipmentId(validatedShipments[0].shipment_id);
    }
  }, [selectedShipmentId, validatedShipments, setSelectedShipmentId]);

  useEffect(() => {
    if (!selectedShipmentId) return;
    const fromContext = invoicePoByShipment[selectedShipmentId];
    if (fromContext != null) return;
    const map = loadPoMap();
    const legacy = map[selectedShipmentId];
    if (legacy) {
      setInvoicePoByShipment((prev) => ({ ...prev, [selectedShipmentId]: legacy }));
    }
  }, [selectedShipmentId, invoicePoByShipment, setInvoicePoByShipment]);

  const handlePoChange = useCallback(
    (value: string) => {
      if (!selectedShipmentId) return;
      setInvoicePoByShipment((prev) => {
        const next = { ...prev };
        if (value.trim()) next[selectedShipmentId] = value;
        else delete next[selectedShipmentId];
        return next;
      });
      savePoForShipment(selectedShipmentId, value);
    },
    [selectedShipmentId, setInvoicePoByShipment],
  );

  const applyFilledResponse = useCallback(
    (res: Awaited<ReturnType<typeof fillInvoice>>, shipmentId: string) => {
      setInvoiceDraft(res);
      if (res.template_hash) {
        setInvoiceTemplateHash(res.template_hash);
      }
      const dataCells = res.cells.filter((c) => !c.clear);
      const meta = cellMetaFromFills(dataCells);
      setCellMeta(meta);
      const sheet = spreadsheetRef.current;
      if (sheet?.isReady()) {
        sheet.applyCellsAndSyncSheets(dataCells);
      } else {
        sheet?.resetAndApplyCells(dataCells);
      }
      setSheetPhase("filled");
      const rt =
        res.revenue_ton ??
        (() => {
          const cell = res.cells.find((c) => c.field_key === "revenue_ton");
          if (!cell?.value) return null;
          const n = Number.parseFloat(String(cell.value));
          return Number.isNaN(n) ? null : n;
        })();
      setRevenueTon(rt);
      setInvoiceSessionsByShipment((prev) =>
        mergeSessions(prev, shipmentId, {
          draft: res,
          cellMeta: meta,
          revenueTon: rt,
          sheetPhase: "filled",
        }),
      );
      if (res.warnings && res.warnings.length > 0) {
        toast.warning("部分 SKU 缺少主数据，请在导出后手动补充", {
          description: res.warnings.slice(0, 3).join("；"),
        });
      }
    },
    [setInvoiceDraft, setInvoiceSessionsByShipment],
  );

  const fillOneShipment = useCallback(
    async (shipment: (typeof validatedShipments)[number]) => {
      savePoForShipment(shipment.shipment_id, poNumber);
      const res = await fillInvoice({
        shipment_id: shipment.shipment_id,
        csv_base64: shipment.parsed_shipment ? undefined : shipment.csv_base64,
        pdf_base64: shipment.pdf_base64,
        parsed_shipment: shipment.parsed_shipment,
        forwarder_id: selectedForwarderId,
        po_number: poNumber.trim(),
        workflow_json: buildWorkflowJson(),
        template_base64: invoiceTemplateBase64 ?? undefined,
      });
      if (shipment.shipment_id === selectedShipmentId) {
        applyFilledResponse(res, shipment.shipment_id);
      } else {
        const dataCells = res.cells.filter((c) => !c.clear);
        const meta = cellMetaFromFills(dataCells);
        const rt =
          res.revenue_ton ??
          (() => {
            const cell = res.cells.find((c) => c.field_key === "revenue_ton");
            if (!cell?.value) return null;
            const n = Number.parseFloat(String(cell.value));
            return Number.isNaN(n) ? null : n;
          })();
        setInvoiceSessionsByShipment((prev) =>
          mergeSessions(prev, shipment.shipment_id, {
            draft: res,
            cellMeta: meta,
            revenueTon: rt,
            sheetPhase: "filled",
          }),
        );
      }
      return res;
    },
    [
      poNumber,
      selectedForwarderId,
      buildWorkflowJson,
      invoiceTemplateBase64,
      selectedShipmentId,
      applyFilledResponse,
      setInvoiceSessionsByShipment,
    ],
  );

  const runFill = useCallback(async () => {
    if (staleness.validation) {
      setError("Step 4 校验已过期，请先重新校验后再填写发票");
      return;
    }
    if (!step4Ok || !selected || !selectedForwarderId || !hasTemplate) {
      setError("请先选择货代与 Step 4 校验通过的货件");
      return;
    }
    setFilling(true);
    setError(null);
    try {
      await fillOneShipment(selected);
      clearStageStale("invoice");
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setFilling(false);
    }
  }, [staleness.validation, step4Ok, selected, selectedForwarderId, hasTemplate, fillOneShipment, clearStageStale]);

  const runFillAllValidated = useCallback(async () => {
    if (staleness.validation) {
      setError("Step 4 校验已过期，请先重新校验后再填写发票");
      return;
    }
    if (!step4Ok || !validatedShipments.length || !selectedForwarderId || !hasTemplate) {
      setError("无可自动填写的校验通过货件");
      return;
    }
    setFilling(true);
    setError(null);
    try {
      let ok = 0;
      for (const shipment of validatedShipments) {
        await fillOneShipment(shipment);
        ok += 1;
      }
      clearStageStale("invoice");
      toast.success(`已自动填写 ${ok} 个校验通过货件`);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setFilling(false);
    }
  }, [staleness.validation, step4Ok, validatedShipments, selectedForwarderId, hasTemplate, fillOneShipment, clearStageStale]);

  const handleExport = useCallback(async () => {
    if (isOfficialExportBlocked("invoice", staleness)) {
      setError(STALE_DOWNLOAD_HINT);
      return;
    }
    if ((!invoiceTemplateHash && !invoiceTemplateBase64) || (sheetPhase !== "filled" && sheetPhase !== "preview")) {
      setError("请先加载货代模板后再导出");
      return;
    }
    const snapshot = spreadsheetRef.current?.getSnapshot();
    if (!snapshot) {
      setError("表格还没准备好，请等模板显示后再导出");
      return;
    }
    setExporting(true);
    setError(null);
    try {
      const getValue = (cell: string) => spreadsheetRef.current?.getCellValue(cell) ?? "";
      await exportInvoice({
        template_hash: invoiceTemplateHash ?? undefined,
        template_base64: invoiceTemplateHash ? undefined : (invoiceTemplateBase64 ?? undefined),
        forwarder_id: selectedForwarderId || undefined,
        shipment_id: invoiceDraft?.shipment_id || selectedShipmentId || "preview",
        warehouse_code: invoiceDraft?.warehouse_code || selected?.warehouse || "",
        template_sheet: invoiceDraft?.template_sheet || templateSheetName,
        fields: invoiceDraft ? buildExportFieldsForInvoiceExport(invoiceDraft.cells, cellMeta, getValue) : [],
        snapshot,
      });
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setExporting(false);
    }
  }, [
    invoiceDraft,
    invoiceTemplateHash,
    invoiceTemplateBase64,
    sheetPhase,
    templateSheetName,
    cellMeta,
    selectedForwarderId,
    selectedShipmentId,
    selected,
    staleness,
  ]);

  const handleCopyToExcel = useCallback(async () => {
    if (!hasTemplate) {
      setError("请先加载货代模板");
      return;
    }
    setCopying(true);
    setError(null);
    try {
      await spreadsheetRef.current?.copyToClipboard();
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setCopying(false);
    }
  }, [hasTemplate]);

  const handleForwarderChange = useCallback(
    async (forwarderId: string) => {
      if (selectedShipmentId) persistCurrentSession(selectedShipmentId);
      setSelectedForwarderId(forwarderId);
      const profile = forwarders.find((f) => f.id === forwarderId);
      await loadForwarderTemplate(forwarderId, profile);
    },
    [forwarders, loadForwarderTemplate, persistCurrentSession, selectedShipmentId],
  );

  const handleAddForwarder = useCallback(
    async (name: string, file: File) => {
      setSavingForwarder(true);
      setError(null);
      try {
        const b64 = await fileToBase64(file);
        const res = await createForwarder(name, b64);
        setForwarders((prev) => [...prev, res.forwarder]);
        setAddDialogOpen(false);
        await handleForwarderChange(res.forwarder.id);
      } catch (err) {
        setError(formatApiError(err));
      } finally {
        setSavingForwarder(false);
      }
    },
    [handleForwarderChange],
  );

  const handleCellEdited = useCallback(
    (cell: string, value: string) => {
      setCellMeta((prev) => {
        const meta = prev[cell];
        if (!meta) return prev;
        if (value.trim() && meta.source === "missing") {
          return { ...prev, [cell]: { ...meta, source: "exact" } };
        }
        return prev;
      });

      if (!syncLinkedEdits || !invoiceDraft) return;
      const fieldKey = cellMeta[cell]?.fieldKey;
      if (!fieldKey) return;
      const rowSku = skuForCellRow(invoiceDraft.cells, cell);

      setInvoiceSessionsByShipment((prev) => {
        const next = { ...prev };
        for (const [sid, session] of Object.entries(next)) {
          if (!session.draft) continue;
          const synced = syncDraftCellValue(session.draft, cell, value, fieldKey, rowSku);
          const syncedMeta = { ...session.cellMeta };
          for (const c of synced.cells) {
            if (c.field_key !== fieldKey) continue;
            const ref = c.cell.toUpperCase();
            if (!syncedMeta[ref]) continue;
            if (rowSku && skuForCellRow(synced.cells, ref) !== rowSku) continue;
            syncedMeta[ref] = {
              ...syncedMeta[ref],
              source: value.trim() ? "exact" : syncedMeta[ref].source,
            };
          }
          next[sid] = { ...session, draft: synced, cellMeta: syncedMeta };
        }
        return next;
      });

      setInvoiceDraft((current) => {
        if (!current) return current;
        return syncDraftCellValue(current, cell, value, fieldKey, rowSku);
      });
    },
    [syncLinkedEdits, invoiceDraft, cellMeta, setInvoiceSessionsByShipment, setInvoiceDraft],
  );

  const handleShipmentChange = useCallback(
    async (id: string) => {
      if (selectedShipmentId) persistCurrentSession(selectedShipmentId, { flushSpreadsheet: true });
      lastRestoredKeyRef.current = `${taskId}:${id}`;
      setSelectedShipmentId(id);
      const session = invoiceSessionsByShipment[id];
      await restoreSession(session);
    },
    [
      taskId,
      selectedShipmentId,
      persistCurrentSession,
      setSelectedShipmentId,
      invoiceSessionsByShipment,
      restoreSession,
    ],
  );

  return {
    shipments: validatedShipments,
    step4Ok,
    selectedShipmentId,
    filledShipmentIds,
    syncLinkedEdits,
    setSyncLinkedEdits,
    spreadsheetRef,
    sheetPhase,
    templateReady,
    setTemplateReady,
    parsing,
    filling,
    exporting,
    copying,
    error,
    setError,
    hasTemplate,
    canAutoFill,
    gridLoading,
    revenueTon,
    missingLabels,
    hasMissing,
    forwarders,
    forwardersLoading,
    selectedForwarderId,
    selectedForwarder,
    poNumber,
    addDialogOpen,
    setAddDialogOpen,
    savingForwarder,
    runFill,
    runFillAllValidated,
    handleExport,
    handleCopyToExcel,
    handleForwarderChange,
    handleAddForwarder,
    handleCellEdited,
    handleShipmentChange,
    handlePoChange,
  };
}
