import { ApiError, resolveApiUrl } from "@/lib/api/client";

export type LingxingSettings = {
  mcp_url: string;
  mcp_key_set: boolean;
  mcp_key_hint: string;
};

export type LingxingSyncDiff = {
  kind: string;
  sku: string;
  message: string;
};

export type LingxingSyncStep = {
  name: string;
  ok: boolean;
  detail: string;
};

export type LingxingPreviewField = {
  field: string;
  label: string;
  local_value: string;
  remote_value: string;
  default_checked: boolean;
  sensitive?: boolean;
};

/** S9-step2 A / S9-step2-fix：预览里的价格信息（按会写入的价格字段计算“确认写入后”的申报价）。 */
export type LingxingPreviewPriceVariant = {
  currency: string;
  listing_price: number | null;
  /** remote = 本次领星返回并写入；local = 库里的旧值；"" = 没有 */
  listing_price_origin: string;
  regular_price: number | null;
  regular_price_origin: string;
  regular_price_informative: boolean;
  /** S9-step4（D-16）：领星常规价采集日期（YYYY-MM-DD）；常规价只在采集后 90 天内有效 */
  regular_price_at?: string;
  /** S9-step4（D-16）：库里的常规价已超过 90 天，不再作为正常价 */
  regular_price_expired?: boolean;
  /** S9-step4（D-15）：S9-B 提示“无促销前历史价，申报价可能偏低，请人工确认”；没有则为空 */
  history_hint?: string;
  declared_price: number | null;
  declared_source: string;
  declared_source_label: string;
  promo: boolean;
  promo_drop_pct: number | null;
  /** S9-step3 UI(j)：降幅文字（1 位小数、向下取），如 "低 20.0%"、"低约 5.0%（已超过 5% 阈值）" */
  promo_drop_text: string;
  /** S9-step3 UI(i)：领星常规价高于售价但低不到 5%（不算促销）时的说明；其余为空 */
  regular_gap_text?: string;
  /** 促销时申报价高于售价（UI e 用来突出显示） */
  declared_above_listing: boolean;
  normal_price: number | null;
  normal_source_label: string;
  /** 正常价取自哪里：领星常规价 / 近 90 天非促销价 */
  normal_basis_label: string;
  warnings: string[];
};

export type LingxingPreviewPriceInfo = LingxingPreviewPriceVariant & {
  price_fields: string[];
  default_key: string;
  /** 键：勾选的价格字段按 listing_price、regular_price 顺序用 + 连接；都不勾为 "" */
  variants: Record<string, LingxingPreviewPriceVariant>;
};

export type LingxingPreviewSku = {
  sku: string;
  is_new: boolean;
  group_kind: string;
  mismatch_skus: string[];
  review_reasons?: string[];
  fields: LingxingPreviewField[];
  price_info?: LingxingPreviewPriceInfo;
};

export type LingxingPreviewPayload = {
  run_id: number | null;
  status: string;
  pending?: boolean;
  groups?: {
    new?: LingxingPreviewSku[];
    needs_review?: LingxingPreviewSku[];
    changed?: LingxingPreviewSku[];
    sku_mismatch?: LingxingPreviewSku[];
    unchanged?: LingxingPreviewSku[];
  };
  summary?: Record<string, number>;
  field_labels?: Record<string, string>;
};

export type LingxingSyncResult = {
  ok: boolean;
  status: string;
  run_id: number;
  steps: LingxingSyncStep[];
  counts: Record<string, number>;
  diffs: LingxingSyncDiff[];
  error?: string | null;
  preview?: LingxingPreviewPayload | null;
};

export type LingxingStockAlert = {
  sku: string;
  asin: string;
  sid: number | null;
  title: string;
  days_fba: number | null;
  fulfillable: number | null;
  qty_local_to_fba: number | null;
  out_stock_date: string;
  message: string;
};

export type LingxingLastRunResponse = {
  run: Record<string, unknown> | null;
  diffs?: LingxingSyncDiff[];
  shops?: Record<string, unknown>[];
  alerts: LingxingStockAlert[];
  preview?: LingxingPreviewPayload | null;
};

export function fetchLingxingSettings() {
  return apiJson<LingxingSettings>("/api/lingxing/settings");
}

export function saveLingxingSettings(body: { mcp_key?: string; mcp_url?: string }) {
  return apiJson<LingxingSettings>("/api/lingxing/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function fetchLingxingLastRun() {
  return apiJson<LingxingLastRunResponse>("/api/lingxing/last-run");
}

export function fetchLingxingPreview(runId?: number) {
  const q = runId != null ? `?run_id=${runId}` : "";
  return apiJson<LingxingPreviewPayload>(`/api/lingxing/sync/preview${q}`);
}

export function confirmLingxingPreview(runId: number, items: { sku: string; fields: string[] }[]) {
  return apiJson<{ ok: boolean; run_id: number; skus_patched: number; fields_written: number; skipped: number }>(
    "/api/lingxing/sync/confirm",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: runId, items }),
    },
  );
}

async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(resolveApiUrl(path), {
    ...init,
    headers: { Accept: "application/json", ...init?.headers },
  });
  if (!res.ok) {
    let message = res.statusText || `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") message = body.detail;
    } catch {
      // keep status text
    }
    throw new ApiError(res.status, message);
  }
  return (await res.json()) as T;
}

export function syncLingxingWithProgress(
  onProgress: (percent: number, message: string, step?: string) => void,
): Promise<LingxingSyncResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", resolveApiUrl("/api/lingxing/sync/stream"));
    xhr.responseType = "text";
    xhr.setRequestHeader("Accept", "application/x-ndjson");

    let offset = 0;
    let lineBuffer = "";
    let settled = false;
    let lastResult: LingxingSyncResult | null = null;

    const finish = (res: LingxingSyncResult) => {
      if (settled) return;
      settled = true;
      resolve(res);
    };
    const fail = (err: Error) => {
      if (settled) return;
      settled = true;
      reject(err);
    };

    const drainNdjson = () => {
      const chunk = xhr.responseText.slice(offset);
      if (!chunk) return;
      offset = xhr.responseText.length;
      lineBuffer += chunk;
      const lines = lineBuffer.split("\n");
      lineBuffer = lines.pop() ?? "";
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        try {
          const ev = JSON.parse(trimmed) as {
            event?: string;
            message?: string;
            percent?: number;
            step?: string;
            data?: LingxingSyncResult;
          };
          if (ev.event === "progress" && ev.message != null) {
            onProgress(ev.percent ?? 0, ev.message, ev.step);
          }
          if (ev.event === "result" && ev.data) {
            lastResult = ev.data;
            finish(ev.data);
          }
          if (ev.event === "error") {
            fail(new ApiError(xhr.status || 500, ev.message || "领星同步失败", ev.data));
          }
        } catch {
          // 等待更多字节
        }
      }
    };

    xhr.onprogress = () => drainNdjson();
    xhr.onload = () => {
      drainNdjson();
      if (lineBuffer.trim()) {
        try {
          const ev = JSON.parse(lineBuffer.trim()) as {
            event?: string;
            message?: string;
            data?: LingxingSyncResult;
          };
          if (ev.event === "result" && ev.data) {
            finish(ev.data);
            return;
          }
          if (ev.event === "error") {
            fail(new ApiError(xhr.status || 500, ev.message || "领星同步失败", ev.data));
            return;
          }
        } catch {
          // fall through
        }
      }
      if (settled) return;
      if (xhr.status >= 400) {
        fail(new ApiError(xhr.status, xhr.statusText || `HTTP ${xhr.status}`));
        return;
      }
      if (lastResult) {
        finish(lastResult);
        return;
      }
      fail(new ApiError(xhr.status || 500, "同步未返回结果"));
    };
    xhr.onerror = () => fail(new ApiError(0, "网络错误，无法连接领星同步接口"));
    xhr.onabort = () => fail(new ApiError(0, "同步已取消"));
    xhr.send();
  });
}

// ---------------------------------------------------------------- S5 定时同步
export type LingxingSchedule = {
  enabled: boolean;
  interval_minutes: number;
  max_retries: number;
  retry_delay_seconds: number;
  auto_apply: boolean;
};

export type LingxingScheduleStatus = {
  running: boolean;
  next_run_at: string | null;
  last_success_at?: string | null;
  loop_active: boolean;
  last_result: { ok: boolean; status: string; message?: string; run_id?: number; attempts?: number } | null;
};

export type LingxingScheduleResponse = {
  config: LingxingSchedule;
  status: LingxingScheduleStatus;
  limits?: { min_interval: number; max_interval: number };
};

export type LingxingRun = {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: string;
  trigger: string | null;
  attempt: number | null;
  error: string | null;
  diff_counts: Record<string, number>;
};

export function fetchLingxingSchedule() {
  return apiJson<LingxingScheduleResponse>("/api/lingxing/schedule");
}

export function saveLingxingSchedule(body: Partial<LingxingSchedule>) {
  return apiJson<LingxingScheduleResponse>("/api/lingxing/schedule", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function runLingxingScheduleNow() {
  return apiJson<{ ok: boolean; status: string; message?: string; run_id?: number }>("/api/lingxing/schedule/run-now", {
    method: "POST",
  });
}

export function fetchLingxingRuns(limit = 30) {
  return apiJson<{ items: LingxingRun[] }>(`/api/lingxing/runs?limit=${limit}`);
}

export function fetchLingxingRunDetail(runId: number) {
  return apiJson<{ run: LingxingRun; diffs: LingxingSyncDiff[] }>(`/api/lingxing/runs/${runId}`);
}

export function fetchLingxingSyncLog(lines = 200) {
  return apiJson<{ lines: string[] }>(`/api/lingxing/sync-log?lines=${lines}`);
}
