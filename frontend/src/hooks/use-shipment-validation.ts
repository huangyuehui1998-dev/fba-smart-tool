import { useCallback, useMemo, useState } from "react";

import { useWorkflow } from "@/context/workflow-context";
import { formatApiError, extractApiErrors } from "@/lib/format-api-error";
import { rowsToApi } from "@/lib/step1-rows";
import { filterStep4Logs } from "@/lib/step4-log-filter";
import { ApiError } from "@/lib/api/client";
import { horizontalWarehouseColumns } from "@/lib/box-editor";
import {
  downloadForwarderExport,
  downloadShippingSheetExport,
  downloadWorkerPackingList,
  validateShipmentsWithProgress,
  type BoxLabelMappingRow,
  type PackingMode,
} from "@/lib/api/workflow";
import { downloadThermalLabels } from "@/lib/api/pdf-tools";
import {
  ensureForwarderSubtotals,
  resolveLogisticsProfile,
  sortForwarderByWarehouseTicket,
  warehouseRankFromTicketLabels,
  type LogisticsProfile,
} from "@/lib/forwarder-table";
import { isOfficialExportBlocked, STALE_DOWNLOAD_HINT } from "@/lib/workflow-invalidation";

type DownloadKind = "worker_packing" | "forwarder" | "shipping_sheet" | "thermal_labels" | null;

/**
 * Step 4 全部业务逻辑:三维交叉校验、工人装箱单导出、费用/货代下载、
 * 校验模式切换、日志过滤与货代/物流派生数据。
 * 文件上传交互态(拖拽/历史选择/闪烁)仍由组件维护。
 */
export function useShipmentValidation() {
  const {
    csvFiles,
    pdfFiles,
    throwRatio,
    setThrowRatio,
    boxEditorApi,
    inputRows,
    actualPlacementFee,
    setActualPlacementFee,
    step4Ok,
    setStep4Ok,
    step4StatusLines,
    setStep4StatusLines,
    step4Errors,
    setStep4Errors,
    workerPackingPreview,
    setWorkerPackingPreview,
    workerPackingWarehouses,
    setWorkerPackingWarehouses,
    forwarder,
    setForwarder,
    shippingSheet,
    setShippingSheet,
    shippingSheetLegend,
    setShippingSheetLegend,
    shipments,
    setShipments,
    setSelectedShipmentId,
    clearStageStale,
    markStale,
    staleness,
  } = useWorkflow();

  const [validating, setValidating] = useState(false);
  const [downloading, setDownloading] = useState<DownloadKind>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [progressMessage, setProgressMessage] = useState("");
  const [progressLog, setProgressLog] = useState<string[]>([]);
  const [logisticsProfile, setLogisticsProfile] = useState<LogisticsProfile | null>(null);
  const [boxLabelMapping, setBoxLabelMapping] = useState<BoxLabelMappingRow[]>([]);
  const [mappingOk, setMappingOk] = useState<boolean | null>(null);
  const [packingMode, setPackingMode] = useState<PackingMode>("amazon_led");
  const isStrictMapping = packingMode === "strict_local";
  const amazonLedMode = !isStrictMapping;
  const [crossCheckModalOpen, setCrossCheckModalOpen] = useState(false);
  const [crossCheckModalErrors, setCrossCheckModalErrors] = useState<string[]>([]);
  const [workerPackingLoading, setWorkerPackingLoading] = useState(false);
  const [workerPackingSuccess, setWorkerPackingSuccess] = useState(false);
  const [crossCheckOk, setCrossCheckOk] = useState(false);

  const warehouses = useMemo(() => {
    if (workerPackingWarehouses.length) return workerPackingWarehouses;
    return horizontalWarehouseColumns(workerPackingPreview);
  }, [workerPackingWarehouses, workerPackingPreview]);

  const displayStatusLines = useMemo(
    () => filterStep4Logs(step4StatusLines, isStrictMapping),
    [step4StatusLines, isStrictMapping],
  );
  const displayErrors = useMemo(
    () => filterStep4Logs(step4Errors, isStrictMapping),
    [step4Errors, isStrictMapping],
  );

  const forwarderDisplay = useMemo(() => {
    if (!forwarder.length) return forwarder;
    if (workerPackingWarehouses.length) {
      return sortForwarderByWarehouseTicket(
        forwarder,
        warehouseRankFromTicketLabels(workerPackingWarehouses),
      );
    }
    return ensureForwarderSubtotals(forwarder);
  }, [forwarder, workerPackingWarehouses]);

  const displayLogisticsProfile = useMemo(
    () =>
      step4Ok && forwarderDisplay.length
        ? resolveLogisticsProfile(logisticsProfile, forwarderDisplay)
        : null,
    [step4Ok, forwarderDisplay, logisticsProfile],
  );

  /** 文件变更时复位校验态,供上传/历史选择回调使用。 */
  const resetValidation = useCallback(() => {
    setStep4Ok(false);
    setLogisticsProfile(null);
    markStale("validation");
  }, [setStep4Ok, markStale]);

  const changePackingMode = useCallback(
    (strict: boolean) => {
      setPackingMode(strict ? "strict_local" : "amazon_led");
      setStep4Ok(false);
      setWorkerPackingSuccess(false);
      markStale("validation");
    },
    [setStep4Ok, markStale],
  );

  const handleValidate = async () => {
    if (!csvFiles.length || !pdfFiles.length) {
      setError("请至少上传一个 CSV 和一个 PDF");
      return;
    }
    setValidating(true);
    setError(null);
    setProgress(0);
    setProgressMessage("准备校验…");
    setProgressLog([]);
    setStep4Ok(false);
    setLogisticsProfile(null);
    setBoxLabelMapping([]);
    setMappingOk(null);
    setActualPlacementFee(null);
    try {
      const res = await validateShipmentsWithProgress(
        csvFiles,
        pdfFiles,
        throwRatio,
        boxEditorApi,
        rowsToApi(inputRows),
        packingMode,
        (pct, message) => {
          setProgress(pct);
          setProgressMessage(message);
          setProgressLog((prev) => {
            if (prev[prev.length - 1] === message) return prev;
            const next = [...prev, message];
            return next.length > 12 ? next.slice(-12) : next;
          });
        },
      );
      setProgress(85);
      setStep4StatusLines(res.status_lines);
      setStep4Errors(res.errors);
      setThrowRatio(res.throw_ratio);
      setBoxLabelMapping(res.box_label_mapping ?? []);
      setMappingOk(res.mapping_ok ?? null);
      setCrossCheckOk(Boolean(res.cross_check_ok));
      setWorkerPackingSuccess(false);
      if (res.actual_placement_fee) {
        setActualPlacementFee(res.actual_placement_fee);
      }

      if (res.ok && res.forwarder && res.shipments) {
        const enrichedForwarder = ensureForwarderSubtotals(res.forwarder);
        setWorkerPackingPreview(res.worker_packing_preview ?? []);
        setWorkerPackingWarehouses(res.worker_packing_warehouses ?? []);
        setShippingSheet(res.shipping_sheet ?? []);
        setShippingSheetLegend(res.shipping_sheet_legend ?? []);
        setForwarder(enrichedForwarder);
        setShipments(res.shipments);
        if (res.shipments[0]) setSelectedShipmentId(res.shipments[0].shipment_id);
        setLogisticsProfile(
          resolveLogisticsProfile(
            {
              wm_ratio: res.wm_ratio,
              stowage_factor: res.stowage_factor,
              cargo_density: res.cargo_density,
              revenue_ton: res.revenue_ton,
              total_gross_kg: res.total_gross_kg,
              total_volumetric_weight_kg: res.total_volumetric_weight_kg,
              total_cbm: res.total_cbm,
            },
            enrichedForwarder,
          ),
        );
        setStep4Ok(true);
        clearStageStale("validation");
        setProgress(100);
      } else {
        setStep4Ok(false);
        setProgress(100);
        if (res.worker_packing_preview?.length) {
          setWorkerPackingPreview(res.worker_packing_preview);
        }
        if (res.worker_packing_warehouses?.length) {
          setWorkerPackingWarehouses(res.worker_packing_warehouses);
        }
        if (res.shipping_sheet?.length) {
          setShippingSheet(res.shipping_sheet);
        }
        if (res.shipping_sheet_legend?.length) {
          setShippingSheetLegend(res.shipping_sheet_legend);
        }
        if (res.actual_placement_fee) {
          setActualPlacementFee(res.actual_placement_fee);
        }
        if (!res.errors.length) setError("校验未通过，请检查上传文件");
      }
    } catch (err) {
      setError(formatApiError(err));
      setProgress(0);
      setProgressMessage("");
    } finally {
      setValidating(false);
    }
  };

  const handleWorkerPackingDownload = async () => {
    if (isOfficialExportBlocked("validation", staleness)) {
      setError(STALE_DOWNLOAD_HINT);
      return;
    }
    if (!workerPackingPreview.length) {
      setError("请先完成校验，生成工人装箱实操单预览");
      return;
    }
    setWorkerPackingLoading(true);
    setWorkerPackingSuccess(false);
    setError(null);
    try {
      await downloadWorkerPackingList(workerPackingPreview, warehouses);
      setWorkerPackingSuccess(true);
      setCrossCheckOk(true);
    } catch (err) {
      const errors = err instanceof ApiError ? extractApiErrors(err) : [formatApiError(err)];
      setCrossCheckModalErrors(errors);
      setCrossCheckModalOpen(true);
    } finally {
      setWorkerPackingLoading(false);
    }
  };

  const downloadShippingSheet = useCallback(async () => {
    if (isOfficialExportBlocked("validation", staleness)) {
      setError(STALE_DOWNLOAD_HINT);
      return;
    }
    setDownloading("shipping_sheet");
    try {
      await downloadShippingSheetExport(
        shippingSheet,
        shippingSheetLegend,
        rowsToApi(inputRows),
      );
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setDownloading(null);
    }
  }, [shippingSheet, shippingSheetLegend, inputRows, staleness]);

  const downloadForwarder = useCallback(async () => {
    if (isOfficialExportBlocked("validation", staleness)) {
      setError(STALE_DOWNLOAD_HINT);
      return;
    }
    setDownloading("forwarder");
    try {
      await downloadForwarderExport(forwarderDisplay);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setDownloading(null);
    }
  }, [forwarderDisplay, staleness]);

  const downloadThermalLabelsPdf = useCallback(async () => {
    if (isOfficialExportBlocked("validation", staleness)) {
      setError(STALE_DOWNLOAD_HINT);
      return;
    }
    if (!shipments.length) {
      setError("请先完成校验，生成箱唛 PDF 数据");
      return;
    }
    setDownloading("thermal_labels");
    try {
      await downloadThermalLabels(shipments);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setDownloading(null);
    }
  }, [shipments, staleness]);

  const downloadWorkerPacking = useCallback(async () => {
    setDownloading("worker_packing");
    try {
      await handleWorkerPackingDownload();
    } finally {
      setDownloading(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workerPackingPreview, warehouses]);

  return {
    // 校验态
    validating,
    downloading,
    error,
    progress,
    progressMessage,
    progressLog,
    step4Ok,
    boxLabelMapping,
    mappingOk,
    packingMode,
    isStrictMapping,
    amazonLedMode,
    crossCheckOk,
    crossCheckModalOpen,
    setCrossCheckModalOpen,
    crossCheckModalErrors,
    workerPackingLoading,
    workerPackingSuccess,
    // 数据
    shipments,
    actualPlacementFee,
    workerPackingPreview,
    shippingSheet,
    shippingSheetLegend,
    warehouses,
    displayStatusLines,
    displayErrors,
    forwarderDisplay,
    displayLogisticsProfile,
    // 操作
    handleValidate,
    handleWorkerPackingDownload,
    downloadShippingSheet,
    downloadForwarder,
    downloadThermalLabelsPdf,
    downloadWorkerPacking,
    changePackingMode,
    resetValidation,
  };
}
