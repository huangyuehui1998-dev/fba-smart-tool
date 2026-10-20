import { useCallback, useEffect, useId, useRef, useState } from "react";

import { PREVIEW_DEBOUNCE_MS } from "@/constants";
import { formatApiError } from "@/lib/format-api-error";
import { useWorkflow } from "@/context/workflow-context";
import {
  computePreview,
  downloadInputTemplate,
  parseExcelFile,
  parseTextDeepseek,
  parseTextLocal,
  validateInput,
  type ApiSkuRow,
  type CostDashboard,
  type GrossWeightWarning,
  type ValidationErrorItem,
} from "@/lib/api/step1";
import {
  EMPTY_ROW,
  aggregateTotals,
  apiRowsToRows,
  computedFromApi,
  emptyComputed,
  getDeepseekOptions,
  rowsEquivalent,
  rowsToApi,
  type ComputedDisplay,
  type Row,
} from "@/lib/step1-rows";
import { shouldPromptWeightConfirm, weightRowsHash } from "@/lib/weight-confirm";
import type { MasterDataGap } from "@/lib/master-data-gap";
import {
  stageInvalidatedByInputField,
  shouldUnlockBoxingOnInputField,
} from "@/lib/workflow-input-change";

export type ParseAction = "local" | "deepseek" | "excel" | "template" | null;

/**
 * Step 1 全部业务逻辑:文本/Excel 解析、实时预览+校验、入库费计算。
 * 组件只消费返回值进行渲染。
 */
export function useStep1Logic() {
  const {
    inputRows: rows,
    setInputRows: setRows,
    setFnskuOverrides,
    throwRatio,
    actualPlacementFee,
    markStale,
    resetDownstreamFromInput,
    setBoxLocked,
  } = useWorkflow();

  const [text, setText] = useState("");
  const [computed, setComputed] = useState<ComputedDisplay[]>([emptyComputed()]);
  const [totalCbm, setTotalCbm] = useState(0);
  const [totalVolWeight, setTotalVolWeight] = useState(0);
  const [cargoDensity, setCargoDensity] = useState(0);
  const [costDashboard, setCostDashboard] = useState<CostDashboard | null>(null);
  const [validationErrors, setValidationErrors] = useState<ValidationErrorItem[]>([]);
  const [weightWarnings, setWeightWarnings] = useState<GrossWeightWarning[]>([]);
  const [masterGaps, setMasterGaps] = useState<MasterDataGap[]>([]);
  const [acknowledgedWeightHash, setAcknowledgedWeightHash] = useState<string | null>(null);
  const [parseAction, setParseAction] = useState<ParseAction>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const excelInputId = useId();
  const previewSeq = useRef(0);

  const refreshPreview = useCallback(
    async (nextRows: Row[]) => {
      const hasSku = nextRows.some((r) => r.sku.trim());
      if (!hasSku) {
        setComputed(nextRows.map(() => emptyComputed()));
        setValidationErrors([]);
        setWeightWarnings([]);
        setMasterGaps([]);
        setTotalCbm(0);
        setTotalVolWeight(0);
        setCargoDensity(0);
        setCostDashboard(null);
        return;
      }

      const seq = ++previewSeq.current;
      setPreviewLoading(true);
      try {
        const payload = rowsToApi(nextRows);
        const [previewRes, validateRes] = await Promise.all([
          computePreview(payload, throwRatio),
          validateInput(payload),
        ]);
        if (seq !== previewSeq.current) return;

        if (previewRes.merged_rows?.length) {
          const merged = apiRowsToRows(previewRes.merged_rows).map((r, i) => ({
            ...r,
            dataSource:
              previewRes.data_sources?.[i] === "official"
                ? ("official" as const)
                : r.sku.trim()
                  ? ("manual" as const)
                  : undefined,
          }));
          while (merged.length < nextRows.length) {
            merged.push({ ...EMPTY_ROW, dataSource: undefined });
          }
          const slice = merged.slice(0, nextRows.length);
          if (!rowsEquivalent(nextRows, slice)) {
            setRows(slice);
          }
          const overrides: Record<string, string> = {};
          for (const r of slice) {
            if (r.sku.trim() && r.fnsku.trim() && r.dataSource === "official") {
              overrides[r.sku.trim()] = r.fnsku.trim();
            }
          }
          if (Object.keys(overrides).length) {
            setFnskuOverrides((prev) => ({ ...prev, ...overrides }));
          }
        }

        const nextComputed = previewRes.rows.map((r) => computedFromApi(r));
        while (nextComputed.length < nextRows.length) {
          nextComputed.push(emptyComputed());
        }
        setComputed(nextComputed.slice(0, nextRows.length));
        setTotalCbm(previewRes.total_cbm ?? 0);
        setTotalVolWeight(previewRes.total_volumetric_weight ?? 0);
        setCargoDensity(previewRes.cargo_density ?? 0);
        setCostDashboard(previewRes.cost_dashboard ?? null);
        setWeightWarnings(previewRes.weight_warnings ?? []);
        setMasterGaps(previewRes.master_gaps ?? []);
        setValidationErrors(validateRes.errors);
      } catch (err) {
        if (seq !== previewSeq.current) return;
        setError(formatApiError(err));
      } finally {
        if (seq === previewSeq.current) setPreviewLoading(false);
      }
    },
    [throwRatio, setFnskuOverrides, setRows],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refreshPreview(rows);
    }, PREVIEW_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [rows, refreshPreview]);

  const update = useCallback(
    (i: number, key: keyof Row, value: string) => {
      const current = rows[i];
      if (!current || current[key] === value) return;
      markStale(stageInvalidatedByInputField(key));
      if (shouldUnlockBoxingOnInputField(key)) {
        setBoxLocked(false);
      }
      setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, [key]: value } : r)));
    },
    [markStale, rows, setBoxLocked, setRows],
  );

  const addRow = useCallback(() => {
    markStale("input");
    setBoxLocked(false);
    setRows((rs) => [...rs, { ...EMPTY_ROW }]);
    setComputed((cs) => [...cs, emptyComputed()]);
  }, [markStale, setBoxLocked, setRows]);

  const removeRow = useCallback(
    (i: number) => {
      markStale("input");
      setBoxLocked(false);
      setRows((rs) => {
        const next = rs.filter((_, idx) => idx !== i);
        return next.length ? next : [{ ...EMPTY_ROW }];
      });
      setComputed((cs) => {
        const next = cs.filter((_, idx) => idx !== i);
        return next.length ? next : [emptyComputed()];
      });
    },
    [markStale, setBoxLocked, setRows],
  );

  const clearAll = useCallback(() => {
    resetDownstreamFromInput();
    setRows([{ ...EMPTY_ROW }]);
    setComputed([emptyComputed()]);
    setValidationErrors([]);
    setWeightWarnings([]);
    setMasterGaps([]);
    setTotalCbm(0);
    setTotalVolWeight(0);
    setCargoDensity(0);
    setCostDashboard(null);
    setError(null);
    setSuccess(null);
  }, [resetDownstreamFromInput, setRows]);

  const applyParsedRows = useCallback(
    (apiRows: ApiSkuRow[], count: number, message: string) => {
      resetDownstreamFromInput();
      const next = apiRowsToRows(apiRows);
      setRows(next);
      setSuccess(message || `已解析 ${count} 条 SKU`);
      setError(null);
    },
    [resetDownstreamFromInput, setRows],
  );

  const handleParseLocal = useCallback(async () => {
    if (!text.trim()) {
      setError("请先粘贴要解析的文本");
      return;
    }
    setParseAction("local");
    setError(null);
    setSuccess(null);
    try {
      const res = await parseTextLocal(text);
      if (!res.rows.length) {
        setError("未解析到有效数据，请检查文本格式");
        return;
      }
      applyParsedRows(res.rows, res.count, `本地规则已解析 ${res.count} 条 SKU`);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setParseAction(null);
    }
  }, [text, applyParsedRows]);

  const handleParseDeepseek = useCallback(async () => {
    if (!text.trim()) {
      setError("请先粘贴要解析的文本");
      return;
    }
    const { apiKey, model, temperature } = getDeepseekOptions();
    if (!apiKey) {
      setError("请先在左侧边栏「系统设置」中填写 DeepSeek API Key");
      return;
    }
    setParseAction("deepseek");
    setError(null);
    setSuccess(null);
    try {
      const res = await parseTextDeepseek(text, { apiKey, model, temperature });
      if (!res.rows.length) {
        setError("DeepSeek 未识别到有效 SKU 数据");
        return;
      }
      applyParsedRows(res.rows, res.count, `DeepSeek 已识别 ${res.count} 条 SKU`);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setParseAction(null);
    }
  }, [text, applyParsedRows]);

  const handleExcelUpload = useCallback(
    async (file: File) => {
      setParseAction("excel");
      setError(null);
      setSuccess(null);
      try {
        const res = await parseExcelFile(file);
        if (!res.rows.length) {
          setError("样表中未读到有效 SKU 行，请检查表头与必填列");
          return;
        }
        const next = apiRowsToRows(res.rows);
        if (res.fnsku_overrides) {
          setFnskuOverrides(res.fnsku_overrides);
          for (const row of next) {
            const override = res.fnsku_overrides[row.sku];
            if (override && !row.fnsku) row.fnsku = override;
          }
        }
        resetDownstreamFromInput();
        setRows(next);
        setSuccess(`样表已导入 ${res.count} 条 SKU`);
      } catch (err) {
        setError(formatApiError(err));
      } finally {
        setParseAction(null);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [setFnskuOverrides, setRows, resetDownstreamFromInput],
  );

  const handleDownloadTemplate = useCallback(async () => {
    setParseAction("template");
    setError(null);
    try {
      await downloadInputTemplate();
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setParseAction(null);
    }
  }, []);

  const totals = aggregateTotals(computed);
  const weightHash = weightRowsHash(rows);
  const weightConfirmOpen = shouldPromptWeightConfirm(
    rows,
    acknowledgedWeightHash,
    weightWarnings.some((w) => w.requires_confirm),
  );

  const keepDeclaredWeights = useCallback(() => {
    setAcknowledgedWeightHash(weightRowsHash(rows));
  }, [rows]);

  const useCalculatedWeights = useCallback(() => {
    setRows((current) =>
      current.map((row, index) => {
        const warning = weightWarnings.find((item) => item.row_index === index && item.suggested_gross_kg != null);
        if (!warning || warning.suggested_gross_kg == null) return row;
        return { ...row, grossKg: String(warning.suggested_gross_kg) };
      }),
    );
    setAcknowledgedWeightHash(null);
  }, [setRows, weightWarnings]);

  return {
    rows,
    text,
    setText,
    computed,
    totalCbm,
    totalVolWeight,
    cargoDensity,
    costDashboard,
    actualPlacementFee,
    validationErrors,
    weightWarnings,
    masterGaps,
    weightConfirmOpen,
    weightHash,
    keepDeclaredWeights,
    useCalculatedWeights,
    parseAction,
    previewLoading,
    error,
    success,
    fileInputRef,
    excelInputId,
    totals,
    update,
    addRow,
    removeRow,
    clearAll,
    handleParseLocal,
    handleParseDeepseek,
    handleExcelUpload,
    handleDownloadTemplate,
  };
}
