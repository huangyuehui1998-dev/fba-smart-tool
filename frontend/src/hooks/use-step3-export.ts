import { useCallback, useEffect, useMemo, useState } from "react";

import { useWorkflow } from "@/context/workflow-context";
import { formatApiError } from "@/lib/format-api-error";
import { rowsToApi } from "@/lib/step1-rows";
import {
  downloadAmazonExport,
  downloadInternalExport,
  fetchStep3Preview,
} from "@/lib/api/workflow";
import { isOfficialExportBlocked, STALE_DOWNLOAD_HINT } from "@/lib/workflow-invalidation";

/** Step 3 业务逻辑:锁定校验、预览矩阵拉取、内部表/Amazon 模板导出。 */
export function useStep3Export() {
  const {
    boxLocked,
    inputRows,
    boxEditorApi,
    fnskuOverrides,
    step3Matrix,
    setStep3Matrix,
    step3BoxCount,
    setStep3BoxCount,
    step3SkuCount,
    setStep3SkuCount,
    metrics,
    staleness,
    clearStageStale,
  } = useWorkflow();

  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState<"internal" | "amazon" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const payload = useMemo(
    () => ({
      rows: rowsToApi(inputRows),
      box_editor: boxEditorApi,
      fnsku_overrides: fnskuOverrides,
    }),
    [inputRows, boxEditorApi, fnskuOverrides],
  );

  const loadPreview = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchStep3Preview(payload);
      setStep3Matrix(res.matrix);
      setStep3BoxCount(res.box_count);
      setStep3SkuCount(res.sku_count);
      clearStageStale("export");
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoading(false);
    }
  }, [payload, setStep3Matrix, setStep3BoxCount, setStep3SkuCount, clearStageStale]);

  useEffect(() => {
    if (!boxLocked || !boxEditorApi.length) return;
    if (step3Matrix.length > 0 && !staleness.export) return;
    void loadPreview();
  }, [boxLocked, boxEditorApi.length, step3Matrix.length, staleness.export, loadPreview]);

  const downloadInternal = useCallback(async () => {
    if (isOfficialExportBlocked("export", staleness) || !boxLocked) {
      setError(STALE_DOWNLOAD_HINT);
      return;
    }
    setDownloading("internal");
    setError(null);
    try {
      await downloadInternalExport(payload);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setDownloading(null);
    }
  }, [payload, staleness, boxLocked]);

  const downloadAmazon = useCallback(async () => {
    if (isOfficialExportBlocked("export", staleness) || !boxLocked) {
      setError(STALE_DOWNLOAD_HINT);
      return;
    }
    setDownloading("amazon");
    setError(null);
    try {
      await downloadAmazonExport(payload);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setDownloading(null);
    }
  }, [payload, staleness, boxLocked]);

  const totalGross = metrics.reduce((s, m) => s + Number(m["毛重(kg)"] || 0), 0);

  return {
    boxLocked,
    loading,
    downloading,
    error,
    step3Matrix,
    step3BoxCount,
    step3SkuCount,
    totalGross,
    downloadInternal,
    downloadAmazon,
    refreshPreview: loadPreview,
  };
}
