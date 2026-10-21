import { AlertTriangle } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  STAGE_LABELS,
  getOfficialFilesForStage,
  getStaleStageLabels,
  type WorkflowStage,
  type WorkflowStaleness,
} from "@/lib/workflow-invalidation";

/** 各 UI 步骤对应的过期阶段（Step 1 无过期概念）。 */
const STEP_STALE_STAGE: Record<number, WorkflowStage | null> = {
  1: null,
  2: "boxing",
  3: "export",
  3.5: "routing",
  4: "validation",
  4.5: "invoice",
  5: "customs",
};

interface StaleDataBannerProps {
  step: number;
  staleness: WorkflowStaleness;
  /** 点击「重新计算/校验」时的回调；不提供则仅展示提示 */
  onRefresh?: () => void;
  refreshLabel?: string;
  loading?: boolean;
}

export function StaleDataBanner({
  step,
  staleness,
  onRefresh,
  refreshLabel = "重新计算",
  loading = false,
}: StaleDataBannerProps) {
  const stage = STEP_STALE_STAGE[step];
  if (!stage || !staleness[stage]) return null;

  const upstreamHint =
    stage === "boxing"
      ? STAGE_LABELS.input
      : STAGE_ORDER_UPSTREAM[stage] ?? "上游步骤";

  const files = getOfficialFilesForStage(stage);
  const affected = getStaleStageLabels(staleness);

  return (
    <Alert variant="destructive" className="border-amber-300 bg-amber-50 text-amber-950">
      <AlertTriangle className="h-4 w-4 !text-amber-600" />
      <AlertTitle className="text-sm font-semibold">当前结果已过期</AlertTitle>
      <AlertDescription className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-2 text-xs">
        <span>
          {STAGE_LABELS[stage]} 的数据基于旧版 {upstreamHint}，请重新计算或校验后再继续。
          {affected.length > 0 ? ` 受影响的步骤：${affected.join("、")}。` : ""}
          {files.length > 0 ? ` 正式文件请勿再发送：${files.join("、")}。` : ""}
        </span>
        {onRefresh && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-7 border-amber-400 bg-white text-amber-900 hover:bg-amber-100"
            disabled={loading}
            onClick={onRefresh}
          >
            {loading ? "处理中…" : refreshLabel}
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}

const STAGE_ORDER_UPSTREAM: Partial<Record<WorkflowStage, string>> = {
  boxing: STAGE_LABELS.input,
  export: STAGE_LABELS.boxing,
  routing: STAGE_LABELS.export,
  validation: STAGE_LABELS.export,
  invoice: STAGE_LABELS.validation,
  customs: STAGE_LABELS.invoice,
};

/** Header 步骤按钮：是否显示过期标记。 */
export function isHeaderStepStale(stepId: number, staleness: WorkflowStaleness): boolean {
  const stage = STEP_STALE_STAGE[stepId];
  return stage ? staleness[stage] : false;
}
