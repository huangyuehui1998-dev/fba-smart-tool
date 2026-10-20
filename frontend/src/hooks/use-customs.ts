import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { useWorkflow } from "@/context/workflow-context";
import { formatApiError } from "@/lib/format-api-error";
import { rowToApi } from "@/lib/step1-rows";
import {
  exportCustomsBlob,
  previewCustoms,
  triggerDownload,
  type CustomsPackageData,
  type CustomsSource,
} from "@/lib/api/customs";
import { averageUnitPrice, patchCustomsLine, recomputeCustomsTotals } from "@/lib/customs-totals";
import { fetchExporters, type ExporterProfile } from "@/lib/api/exporters";
import { isOfficialExportBlocked, STALE_DOWNLOAD_HINT } from "@/lib/workflow-invalidation";

function buildPreviewSig(
  source: CustomsSource,
  orderNo: string,
  exporterId: string,
  selectedIds: string[],
): string {
  return [source, orderNo.trim(), exporterId, [...selectedIds].sort().join("|")].join("\0");
}

export function useCustoms() {
  const {
    step4Ok,
    shipments,
    invoiceDraft,
    inputRows,
    boxEditorApi,
    forwarder,
    customsSession,
    setCustomsSession,
    staleness,
    clearStageStale,
  } = useWorkflow();

  const [source, setSource] = useState<CustomsSource>(customsSession?.source ?? "invoice");
  const [exporters, setExporters] = useState<ExporterProfile[]>([]);
  const [exporterId, setExporterId] = useState(customsSession?.exporterId ?? "");
  const [orderNo, setOrderNo] = useState(customsSession?.orderNo ?? "");
  const [selectedIds, setSelectedIds] = useState<string[]>(customsSession?.selectedIds ?? []);
  const [data, setData] = useState<CustomsPackageData | null>(customsSession?.data ?? null);
  const [previewSig, setPreviewSig] = useState(customsSession?.previewSig ?? "");
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportFormat, setExportFormat] = useState<"xlsx" | "xls">("xlsx");
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState(customsSession?.activeTab ?? "declaration");

  const buildWorkflowJson = useCallback(
    () => ({
      input_rows: inputRows.filter((r) => r.sku.trim()).map((r) => rowToApi(r)),
      box_editor: boxEditorApi,
      forwarder,
      shipments,
    }),
    [inputRows, boxEditorApi, forwarder, shipments],
  );

  useEffect(() => {
    setCustomsSession({
      source,
      exporterId,
      orderNo,
      selectedIds,
      data,
      previewSig,
      activeTab,
    });
  }, [source, exporterId, orderNo, selectedIds, data, previewSig, activeTab, setCustomsSession]);

  useEffect(() => {
    fetchExporters()
      .then((res) => {
        setExporters(res.profiles);
        if (!exporterId) {
          const active = res.profiles.find((p) => p.is_active) ?? res.profiles[0];
          if (active) setExporterId(active.id);
        }
      })
      .catch(() => {
        /* 侧栏也可管理，此处静默 */
      });
  }, [exporterId]);

  const shipmentOptions = useMemo(
    () => shipments.map((s) => ({ id: s.shipment_id, warehouse: s.warehouse })),
    [shipments],
  );
  const shipmentsKey = useMemo(
    () => shipments.map((s) => s.shipment_id).join("|"),
    [shipments],
  );

  useEffect(() => {
    setSelectedIds((prev) => {
      const allIds = shipments.map((s) => s.shipment_id);
      if (prev.length === 0) return allIds;
      const allSet = new Set(allIds);
      const prevSet = new Set(prev);
      const next = [
        ...prev.filter((id) => allSet.has(id)),
        ...allIds.filter((id) => !prevSet.has(id)),
      ];
      return next.length ? next : allIds;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shipmentsKey]);

  const toggleShipment = useCallback((id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }, []);

  const selectAllShipments = useCallback(() => {
    setSelectedIds(shipments.map((s) => s.shipment_id));
  }, [shipments]);

  const clearShipments = useCallback(() => setSelectedIds([]), []);

  const allSelected = shipments.length > 0 && selectedIds.length === shipments.length;

  const previewInputsSig = useMemo(
    () => buildPreviewSig(source, orderNo, exporterId, selectedIds),
    [source, orderNo, exporterId, selectedIds],
  );
  const isStale = Boolean(data) && previewInputsSig !== previewSig;

  const hasInvoiceDraft = Boolean(invoiceDraft);

  useEffect(() => {
    if (!hasInvoiceDraft && source === "invoice") {
      setSource("shipment");
    }
  }, [hasInvoiceDraft, source]);

  const canPreview =
    step4Ok &&
    shipments.length > 0 &&
    selectedIds.length > 0 &&
    orderNo.trim().length > 0 &&
    (source === "shipment" || Boolean(invoiceDraft));

  const avgUnitPrice = useMemo(
    () => (data ? averageUnitPrice(data.total_amount, data.total_qty) : 0),
    [data],
  );

  const runPreview = useCallback(async () => {
    if (staleness.validation) {
      toast.error("Step 4 校验已过期，请先重新校验后再生成报关预览");
      return;
    }
    if (!canPreview) return;
    setLoading(true);
    setError(null);
    try {
      const res = await previewCustoms({
        source,
        exporter_id: exporterId || undefined,
        order_no: orderNo.trim(),
        workflow_json: buildWorkflowJson(),
        invoice_draft: source === "invoice" ? (invoiceDraft as unknown as Record<string, unknown>) : null,
        selected_shipment_ids: selectedIds,
      });
      setData(recomputeCustomsTotals(res.data));
      setPreviewSig(buildPreviewSig(source, orderNo, exporterId, selectedIds));
      clearStageStale("customs");
      toast.success("报关资料预览已生成");
    } catch (e) {
      const msg = formatApiError(e);
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, [canPreview, source, exporterId, orderNo, buildWorkflowJson, invoiceDraft, selectedIds, staleness.validation, clearStageStale]);

  const patchData = useCallback((patch: Partial<CustomsPackageData>) => {
    setData((prev) => (prev ? recomputeCustomsTotals({ ...prev, ...patch }) : prev));
  }, []);

  const patchLine = useCallback((seq: number, patch: Record<string, unknown>) => {
    setData((prev) => (prev ? patchCustomsLine(prev, seq, patch) : prev));
  }, []);

  const patchDate = useCallback((key: string, value: string) => {
    setData((prev) => (prev ? { ...prev, dates: { ...prev.dates, [key]: value } } : prev));
  }, []);

  const runExport = useCallback(async () => {
    if (isOfficialExportBlocked("customs", staleness) || staleness.validation) {
      toast.error(STALE_DOWNLOAD_HINT);
      return;
    }
    if (!data) {
      toast.error("请先生成预览");
      return;
    }
    if (isStale) {
      toast.error("货件选择已变更，请重新生成预览");
      return;
    }
    setExporting(true);
    setError(null);
    try {
      const { blob, filename } = await exportCustomsBlob({
        source,
        exporter_id: exporterId || undefined,
        order_no: orderNo.trim(),
        workflow_json: buildWorkflowJson(),
        invoice_draft: source === "invoice" ? (invoiceDraft as unknown as Record<string, unknown>) : null,
        selected_shipment_ids: selectedIds,
        data,
        export_format: exportFormat,
      });
      triggerDownload(blob, filename);
      toast.success("报关资料已下载");
    } catch (e) {
      const msg = formatApiError(e);
      setError(msg);
      toast.error(msg);
    } finally {
      setExporting(false);
    }
  }, [data, isStale, source, exporterId, orderNo, buildWorkflowJson, invoiceDraft, selectedIds, staleness, exportFormat]);

  return {
    step4Ok,
    source,
    setSource,
    exporters,
    exporterId,
    setExporterId,
    orderNo,
    setOrderNo,
    shipmentOptions,
    selectedIds,
    toggleShipment,
    selectAllShipments,
    clearShipments,
    allSelected,
    isStale,
    data,
    avgUnitPrice,
    loading,
    exporting,
    exportFormat,
    setExportFormat,
    error,
    setError,
    canPreview,
    runPreview,
    runExport,
    patchData,
    patchLine,
    patchDate,
    activeTab,
    setActiveTab,
    hasInvoiceDraft: Boolean(invoiceDraft),
  };
}
