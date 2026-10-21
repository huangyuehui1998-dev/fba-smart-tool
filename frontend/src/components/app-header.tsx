import { useEffect, useState } from "react";
import { ConfirmDialog } from "@/components/feedback/confirm-dialog";
import { Package, RefreshCw, Check, X, FileBox, Loader2, CloudOff, Moon, Sun, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { FboxSaveStatus } from "@/lib/fbox-file-manager";
import { applyTheme, loadThemePreference, saveThemePreference, type ThemePreference } from "@/lib/theme";
import { isHeaderStepStale } from "@/components/stale-data-banner";
import type { WorkflowStaleness } from "@/lib/workflow-invalidation";
import {
  WORKFLOW_STEPS,
  canEnterStep,
  getStepBlockDetail,
  getStepBlockReason,
  type StepGuardState,
} from "@/lib/workflow-steps";

const STEPS = WORKFLOW_STEPS;

interface AppHeaderProps {
  currentStep?: number;
  taskName?: string;
  showRestoredToast?: boolean;
  onDismissRestored?: () => void;
  showArchivedToast?: boolean;
  archivedTaskName?: string | null;
  onDismissArchived?: () => void;
  onStepChange?: (step: number) => void;
  onRestart?: () => void | Promise<void>;
  onSaveTask?: () => void | Promise<void>;
  restarting?: boolean;
  savingTask?: boolean;
  projectFileName?: string | null;
  fboxSaveStatus?: FboxSaveStatus;
  fboxWritable?: boolean;
  staleness?: WorkflowStaleness;
  stepGuard?: StepGuardState;
}

export function AppHeader({
  currentStep = 1,
  taskName = "",
  showRestoredToast = false,
  onDismissRestored,
  showArchivedToast = false,
  archivedTaskName,
  onDismissArchived,
  onStepChange,
  onRestart,
  onSaveTask,
  restarting = false,
  savingTask = false,
  projectFileName = null,
  fboxSaveStatus = "idle",
  fboxWritable = false,
  staleness,
  stepGuard,
}: AppHeaderProps) {
  const [theme, setTheme] = useState<ThemePreference>(() => loadThemePreference());
  const [blockedStep, setBlockedStep] = useState<number | null>(null);
  const darkActive = theme === "dark" || (theme === "system" && typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches);

  const toggleTheme = () => {
    const next: ThemePreference = darkActive ? "light" : "dark";
    setTheme(next);
    saveThemePreference(next);
    applyTheme(next);
  };

  useEffect(() => {
    if (!showRestoredToast) return;
    const timer = window.setTimeout(() => onDismissRestored?.(), 5000);
    return () => window.clearTimeout(timer);
  }, [showRestoredToast, onDismissRestored]);

  useEffect(() => {
    if (!showArchivedToast) return;
    const timer = window.setTimeout(() => onDismissArchived?.(), 6000);
    return () => window.clearTimeout(timer);
  }, [showArchivedToast, onDismissArchived]);

  return (
    <header className="relative border-b border-border bg-card">
      <div className="flex items-start gap-6 px-6 py-3">
        <div className="flex min-w-[280px] flex-col">
          <div className="flex items-center gap-2">
            <Package className="h-6 w-6 text-primary" />
            <h1 className="text-base font-semibold tracking-tight text-foreground">
              亚马逊 FBA 智能装箱与货件处理工具
            </h1>
          </div>
          <p className="mt-1 text-[11px] leading-tight text-muted-foreground">
            U盘便携版 V3.3 · 点击步骤名可跳转 · 当前任务：{taskName || "未命名"}
            {!projectFileName && (
              <span className="text-amber-700 dark:text-amber-400">
                {" "}
                · 可直接开始工作，完成后点「保存任务」
              </span>
            )}
          </p>
          {projectFileName && (
            <p className="mt-0.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <FileBox className="h-3 w-3 shrink-0 text-primary" />
              <span className="truncate max-w-[240px]" title={projectFileName}>
                {projectFileName}
              </span>
              {fboxSaveStatus === "saving" && (
                <span className="inline-flex items-center gap-0.5 text-amber-600">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  保存中
                </span>
              )}
              {fboxSaveStatus === "saved" && fboxWritable && (
                <span className="text-emerald-600">已保存</span>
              )}
              {fboxSaveStatus === "error" && (
                <span className="text-destructive">保存失败</span>
              )}
              {!fboxWritable && (
                <span className="inline-flex items-center gap-0.5 text-amber-600" title="只读打开，修改不会写回磁盘">
                  <CloudOff className="h-3 w-3" />
                  只读
                </span>
              )}
            </p>
          )}
        </div>

        <nav className="flex flex-1 items-center justify-center">
          <ol className="flex items-center gap-1 rounded-lg border border-border bg-background p-1">
            {STEPS.map((s, i) => {
              const active = currentStep === s.id;
              const stale = staleness ? isHeaderStepStale(s.id, staleness) : false;
              const blocked =
                stepGuard != null && !canEnterStep(s.id, currentStep, stepGuard);
              const blockReason = blocked && stepGuard ? getStepBlockReason(s.id, stepGuard) : null;
              return (
                <li key={s.id} className="flex items-center">
                  <button
                    type="button"
                    onClick={() => {
                      if (blocked) {
                        setBlockedStep(s.id);
                        return;
                      }
                      onStepChange?.(s.id);
                    }}
                    aria-disabled={blocked || undefined}
                    title={
                      blockReason
                        ?? (stale ? "可查看上一版（已过期，不能当正式稿）" : undefined)
                    }
                    className={cn(
                      "relative rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                      active
                        ? "bg-primary text-primary-foreground shadow-sm"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                      stale && !active && "ring-1 ring-amber-400/80",
                      blocked && "cursor-not-allowed opacity-45 hover:bg-transparent hover:text-muted-foreground",
                    )}
                  >
                    {s.label}
                    {stale && (
                      <span
                        className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-amber-500"
                        title="该步骤结果已过期"
                      />
                    )}
                  </button>
                  {i < STEPS.length - 1 && <span className="mx-0.5 h-px w-3 bg-border" />}
                </li>
              );
            })}
          </ol>
        </nav>

        <div className="flex min-w-[220px] items-center justify-end gap-2">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={toggleTheme}
            title={darkActive ? "切换浅色模式" : "切换深色模式"}
          >
            {darkActive ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void onSaveTask?.()}
            disabled={savingTask || restarting}
            className="gap-2"
            title="将当前进度保存为 .fbox 工程文件"
          >
            {savingTask ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            {savingTask ? "保存中…" : "保存任务"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void onRestart?.()}
            disabled={restarting}
            className="gap-2"
          >
            <RefreshCw className={cn("h-4 w-4", restarting && "animate-spin")} />
            {restarting ? "处理中…" : "新建任务"}
          </Button>
        </div>
      </div>

      {blockedStep != null && stepGuard && getStepBlockDetail(blockedStep, stepGuard) && (
        <ConfirmDialog
          open
          title="还不能进入这一步"
          description={[
            getStepBlockDetail(blockedStep, stepGuard)!.message,
            ...getStepBlockDetail(blockedStep, stepGuard)!.missing.map((item) => `缺失：${item}`),
          ].join("\n")}
          confirmLabel="前往补齐"
          onConfirm={() => {
            const detail = getStepBlockDetail(blockedStep, stepGuard);
            setBlockedStep(null);
            if (detail) onStepChange?.(detail.jumpTo);
          }}
          onCancel={() => setBlockedStep(null)}
        />
      )}

      {showArchivedToast && (
        <div className="pointer-events-none absolute right-6 top-full z-20 mt-2 flex justify-end">
          <div className="pointer-events-auto flex max-w-md items-center gap-2 rounded-md border border-sky-200 bg-sky-50 px-3 py-1.5 text-xs font-medium text-sky-800 shadow-sm">
            <Check className="h-3.5 w-3.5 shrink-0" />
            <span>
              当前任务已存入历史
              {archivedTaskName ? `：${archivedTaskName}` : ""}
            </span>
            <button
              type="button"
              onClick={onDismissArchived}
              className="ml-1 rounded p-0.5 hover:bg-sky-100"
              aria-label="关闭提示"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        </div>
      )}

      {showRestoredToast && (
        <div className="pointer-events-none absolute right-6 top-full z-20 mt-2 flex justify-end">
          <div className="pointer-events-auto flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 shadow-sm">
            <Check className="h-3.5 w-3.5 shrink-0" />
            <span>已从本地恢复上次进度</span>
            <button
              type="button"
              onClick={onDismissRestored}
              className="ml-1 rounded p-0.5 hover:bg-emerald-100"
              aria-label="关闭提示"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        </div>
      )}
    </header>
  );
}
