import { Fragment, useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { DIFF_LABEL, diffItemClass } from "@/lib/diff-kinds";
import {
  fetchLingxingRunDetail,
  fetchLingxingRuns,
  fetchLingxingSchedule,
  fetchLingxingSyncLog,
  runLingxingScheduleNow,
  saveLingxingSchedule,
  type LingxingRun,
  type LingxingScheduleResponse,
  type LingxingSyncDiff,
} from "@/lib/api/lingxing";

const STATUS_LABEL: Record<string, string> = {
  running: "进行中",
  preview_pending: "待确认",
  partial: "部分成功",
  confirmed: "已确认写入",
  auto_applied: "已自动写入",
  auto_applied_partial: "已自动写入（部分步骤失败）",
  failed: "失败",
  skipped: "跳过（上一轮未结束）",
};
const TRIGGER_LABEL: Record<string, string> = {
  manual: "手动拉取",
  scheduled: "定时",
  retry: "立即重试",
  xlsx_import: "网页导出",
};

function fmt(ts: string | null | undefined) {
  if (!ts) return "—";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleString();
}

/** S5：领星定时同步设置 + 同步记录 + 每次的差异 + 日志 */
export function LingxingSchedulePanel({ onSynced }: { onSynced?: () => void }) {
  const [data, setData] = useState<LingxingScheduleResponse | null>(null);
  const [runs, setRuns] = useState<LingxingRun[]>([]);
  const [openRun, setOpenRun] = useState<number | null>(null);
  const [diffs, setDiffs] = useState<LingxingSyncDiff[]>([]);
  const [log, setLog] = useState<string[] | null>(null);
  const [interval, setIntervalText] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const reload = useCallback(async () => {
    try {
      const [s, r] = await Promise.all([fetchLingxingSchedule(), fetchLingxingRuns(30)]);
      setData(s);
      setIntervalText(String(s.config.interval_minutes));
      setRuns(r.items);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const save = async (patch: Record<string, unknown>) => {
    setBusy(true);
    setMsg("");
    try {
      const s = await saveLingxingSchedule(patch);
      setData((d) => (d ? { ...d, ...s } : s)); // 后端已按新间隔重算下次时间，这里直接显示
      setIntervalText(String(s.config.interval_minutes));
      setMsg("已保存");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const runNow = async () => {
    setBusy(true);
    setMsg("正在同步…");
    try {
      const r = await runLingxingScheduleNow();
      setMsg(r.ok ? "同步完成" : `同步失败：${r.message || r.status}`);
      onSynced?.();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      void reload();
    }
  };

  const toggleRun = async (id: number) => {
    if (openRun === id) {
      setOpenRun(null);
      return;
    }
    setOpenRun(id);
    setDiffs([]);
    try {
      setDiffs((await fetchLingxingRunDetail(id)).diffs);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  };

  const cfg = data?.config;
  const st = data?.status;
  const last = st?.last_result;
  return (
    <div className="space-y-3 rounded-md border p-3 text-xs">
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-medium">定时自动同步</span>
        <label className="flex items-center gap-1">
          <Checkbox checked={!!cfg?.enabled} disabled={busy || !cfg} onCheckedChange={(v) => void save({ enabled: v === true })} />
          启用（默认关闭）
        </label>
        <label className="flex items-center gap-1">
          每
          <Input
            className="h-7 w-20"
            value={interval}
            onChange={(e) => setIntervalText(e.target.value)}
            onBlur={() => cfg && interval !== String(cfg.interval_minutes) && void save({ interval_minutes: Number(interval) })}
          />
          分钟（{data?.limits?.min_interval ?? 15}–{data?.limits?.max_interval ?? 10080}）
        </label>
        <span>失败重试 {cfg?.max_retries ?? "—"} 次</span>
        <Button size="sm" variant="outline" disabled={busy || st?.running} onClick={() => void runNow()}>
          {busy || st?.running ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : <RefreshCw className="mr-1 h-3 w-3" />}
          立即同步 / 重试
        </Button>
        <Button size="sm" variant="ghost" onClick={() => void reload()}>
          刷新
        </Button>
      </div>
      <div className="text-muted-foreground">
        上次成功：{fmt(st?.last_success_at)}；下次：{cfg?.enabled ? fmt(st?.next_run_at) : "未启用"}；上次结果：
        {last ? (last.ok ? `成功（第 ${last.attempts ?? 1} 次尝试）` : `${STATUS_LABEL[last.status] || last.status}：${last.message || ""}`) : "—"}
        。产品库以领星 MCP 为准（D-02），手填字段保持锁定，申报价按 D-01 领星价优先；报关敏感字段和 SKU 对不上的记为“待人工确认”。
      </div>
      {msg && <div className="text-amber-700">{msg}</div>}

      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="py-1">#</th>
            <th>开始</th>
            <th>方式</th>
            <th>尝试</th>
            <th>状态</th>
            <th>差异</th>
            <th>错误</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <Fragment key={r.id}>
              <tr className="cursor-pointer border-b hover:bg-muted/50" onClick={() => void toggleRun(r.id)}>
                <td className="py-1">{r.id}</td>
                <td>{fmt(r.started_at)}</td>
                <td>{TRIGGER_LABEL[r.trigger || "manual"] || r.trigger}</td>
                <td>{r.attempt ?? 1}</td>
                <td className={r.status === "failed" ? "text-red-600" : ""}>{STATUS_LABEL[r.status] || r.status}</td>
                <td>
                  {Object.entries(r.diff_counts || {})
                    .map(([k, n]) => `${DIFF_LABEL[k] || k} ${n}`)
                    .join("，") || "—"}
                </td>
                <td className="max-w-xs truncate" title={r.error || ""}>
                  {r.error || ""}
                  {r.backup_path ? (
                    <button
                      type="button"
                      className="ml-2 underline"
                      data-testid="lingxing-rollback"
                      onClick={(event) => {
                        event.stopPropagation();
                        void fetch(`/api/lingxing/runs/${r.id}/rollback`, { method: "POST" }).then(() => void reload());
                      }}
                    >
                      回滚
                    </button>
                  ) : null}
                </td>
              </tr>
              {openRun === r.id && (
                <tr>
                  <td colSpan={7} className="bg-muted/30 p-2">
                    {diffs.length ? (
                      <ul className="max-h-48 space-y-0.5 overflow-auto">
                        {diffs.map((d, i) => (
                          <li key={i} className={diffItemClass(d.kind)}>
                            [{DIFF_LABEL[d.kind] || d.kind}] {d.sku ? `${d.sku}：` : ""}
                            {d.message}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      "没有差异记录"
                    )}
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>

      <details onToggle={(e) => (e.currentTarget as HTMLDetailsElement).open && void fetchLingxingSyncLog(200).then((r) => setLog(r.lines))}>
        <summary className="cursor-pointer">同步日志（app_data/logs/lingxing_sync.log）</summary>
        <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap text-[11px]">{log ? log.join("\n") || "（空）" : "加载中…"}</pre>
      </details>
    </div>
  );
}
