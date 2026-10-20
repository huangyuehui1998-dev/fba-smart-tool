import { useCallback, useEffect, useRef, useState } from "react";

import { BOX_EDITOR_SYNC_DEBOUNCE_MS } from "@/constants";
import { useWorkflow } from "@/context/workflow-context";
import { formatApiError } from "@/lib/format-api-error";
import { rowsToApi } from "@/lib/step1-rows";
import { apiToBoxEditor, boxEditorToApi, newBoxRowId, type BoxEditorRow } from "@/lib/box-editor";
import {
  assignTail,
  calculateBoxes,
  fetchBoxMetrics,
  fetchTailPool,
  type FbaCompliance,
} from "@/lib/api/workflow";

/**
 * Step 2 全部业务逻辑:初始排箱、可编辑同步、尾数分配、FBA 合规判定、锁定。
 * 组件只消费返回值进行渲染。
 */
export function useBoxValidation() {
  const {
    inputRows,
    fnskuOverrides,
    boxEditorApi,
    setBoxEditorApi,
    metrics,
    setMetrics,
    tailPool,
    setTailPool,
    hasOverweight,
    setHasOverweight,
    setBoxLocked,
    weightLimitKg,
    setStep3Matrix,
    setStep3BoxCount,
    setStep3SkuCount,
    step,
    markStale,
    clearStageStale,
  } = useWorkflow();

  const [detail, setDetail] = useState<BoxEditorRow[]>([]);
  const [initLoading, setInitLoading] = useState(false);
  const [syncLoading, setSyncLoading] = useState(false);
  const [assignLoading, setAssignLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fbaCompliance, setFbaCompliance] = useState<FbaCompliance | null>(null);
  const [hasFbaBlock, setHasFbaBlock] = useState(false);

  const [pickSku, setPickSku] = useState("");
  const [pickQty, setPickQty] = useState(1);
  const [pickBox, setPickBox] = useState(1);

  const syncSeq = useRef(0);

  const workflowPayload = useCallback(
    () => ({
      rows: rowsToApi(inputRows),
      box_editor: boxEditorToApi(detail),
      fnsku_overrides: fnskuOverrides,
    }),
    [inputRows, detail, fnskuOverrides],
  );

  const applyBoxResult = useCallback(
    (
      boxEditor: ReturnType<typeof boxEditorToApi>,
      nextMetrics: typeof metrics,
      overweight: boolean,
      compliance?: FbaCompliance,
      fbaBlock?: boolean,
    ) => {
      setBoxEditorApi(boxEditor);
      setDetail(apiToBoxEditor(boxEditor));
      setMetrics(nextMetrics);
      setHasOverweight(overweight);
      if (compliance) setFbaCompliance(compliance);
      if (fbaBlock !== undefined) setHasFbaBlock(fbaBlock);
    },
    [setBoxEditorApi, setMetrics, setHasOverweight],
  );

  const runCalculate = useCallback(async () => {
    setInitLoading(true);
    setError(null);
    try {
      const res = await calculateBoxes(rowsToApi(inputRows), fnskuOverrides);
      applyBoxResult(
        res.box_editor,
        res.metrics,
        res.has_overweight,
        res.fba_compliance,
        res.has_fba_block,
      );
      setTailPool(res.tail_pool);
      setBoxLocked(false);
      clearStageStale("boxing");
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setInitLoading(false);
    }
  }, [inputRows, fnskuOverrides, applyBoxResult, setTailPool, setBoxLocked, clearStageStale]);

  useEffect(() => {
    if (step !== 2) return;
    if (boxEditorApi.length > 0) {
      setDetail(apiToBoxEditor(boxEditorApi));
      return;
    }
    void runCalculate();
    // 仅在进入 Step 2 且尚无方案时自动排箱；过期时保留上一版供对照
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, boxEditorApi.length]);

  const refreshFromEditor = useCallback(
    async (nextDetail: BoxEditorRow[]) => {
      const seq = ++syncSeq.current;
      setSyncLoading(true);
      try {
        const body = {
          rows: rowsToApi(inputRows),
          box_editor: boxEditorToApi(nextDetail),
          fnsku_overrides: fnskuOverrides,
        };
        const [metricsRes, tailRes] = await Promise.all([
          fetchBoxMetrics(body),
          fetchTailPool(body),
        ]);
        if (seq !== syncSeq.current) return;
        setBoxEditorApi(body.box_editor);
        setMetrics(metricsRes.metrics);
        setHasOverweight(metricsRes.has_overweight);
        setFbaCompliance(metricsRes.fba_compliance);
        setHasFbaBlock(metricsRes.has_fba_block);
        setTailPool(tailRes.tail_pool);
      } catch (err) {
        if (seq !== syncSeq.current) return;
        setError(formatApiError(err));
      } finally {
        if (seq === syncSeq.current) setSyncLoading(false);
      }
    },
    [inputRows, fnskuOverrides, setBoxEditorApi, setMetrics, setHasOverweight, setTailPool],
  );

  useEffect(() => {
    if (!detail.length || initLoading) return;
    const timer = window.setTimeout(() => void refreshFromEditor(detail), BOX_EDITOR_SYNC_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [detail, initLoading, refreshFromEditor]);

  const addDetailRow = useCallback(() => {
    setDetail((d) => [...d, { id: newBoxRowId(), box: 1, source: "混装", sku: "", qty: 0 }]);
  }, []);

  const removeDetailRow = useCallback((id: string) => {
    setDetail((d) => d.filter((r) => r.id !== id));
  }, []);

  const updateDetail = useCallback((id: string, key: keyof BoxEditorRow, value: string) => {
    setDetail((d) =>
      d.map((r) =>
        r.id === id
          ? {
              ...r,
              [key]:
                key === "qty" || key === "box"
                  ? Number(value) || 0
                  : key === "source"
                    ? (value as "整箱" | "混装")
                    : value,
            }
          : r,
      ),
    );
  }, []);

  const handleAssignTail = useCallback(async () => {
    if (!pickSku) {
      setError("请选择要分配的 SKU");
      return;
    }
    // S8 D1：前端先挡一次（后端也会校验）
    const left = Number(tailPool.find((p) => p.SKU简称 === pickSku)?.待排尾数 ?? 0);
    if (!Number.isInteger(pickQty) || pickQty < 1 || pickQty > left) {
      setError(`SKU ${pickSku} 尾数只剩 ${left} 件，分配数量须在 1–${left} 之间`);
      return;
    }
    setAssignLoading(true);
    setError(null);
    try {
      const res = await assignTail({
        ...workflowPayload(),
        sku: pickSku,
        qty: pickQty,
        box_no: pickBox,
      });
      applyBoxResult(
        res.box_editor,
        res.metrics,
        res.has_overweight,
        res.fba_compliance,
        res.has_fba_block,
      );
      const tailRes = await fetchTailPool({
        rows: rowsToApi(inputRows),
        box_editor: res.box_editor,
        fnsku_overrides: fnskuOverrides,
      });
      setTailPool(tailRes.tail_pool);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setAssignLoading(false);
    }
  }, [pickSku, pickQty, pickBox, tailPool, workflowPayload, applyBoxResult, inputRows, fnskuOverrides, setTailPool]);

  const lockPlan = useCallback(() => {
    setBoxLocked(true);
    setStep3Matrix([]);
    setStep3BoxCount(0);
    setStep3SkuCount(0);
    markStale("boxing");
  }, [setBoxLocked, setStep3Matrix, setStep3BoxCount, setStep3SkuCount, markStale]);

  const overweightCount = metrics.filter((m) => m.超重).length;
  const fbaGrossCount = metrics.filter((m) => m.FBA毛重违规).length;
  const sideWarningCount = fbaCompliance?.side_warning_count ?? 0;
  const cannotProceed =
    hasFbaBlock ||
    hasOverweight ||
    overweightCount > 0 ||
    fbaGrossCount > 0 ||
    !detail.length ||
    syncLoading ||
    initLoading;
  const fullCount = detail.filter((r) => r.source === "整箱").length;
  const mixCount = detail.filter((r) => r.source === "混装").length;
  const boxCount = metrics.length;

  return {
    detail,
    metrics,
    tailPool,
    hasOverweight,
    weightLimitKg,
    initLoading,
    syncLoading,
    assignLoading,
    error,
    fbaCompliance,
    hasFbaBlock,
    pickSku,
    setPickSku,
    pickQty,
    setPickQty,
    pickBox,
    setPickBox,
    overweightCount,
    fbaGrossCount,
    sideWarningCount,
    cannotProceed,
    fullCount,
    mixCount,
    boxCount,
    addDetailRow,
    removeDetailRow,
    updateDetail,
    handleAssignTail,
    lockPlan,
    recalculateBoxes: runCalculate,
  };
}
