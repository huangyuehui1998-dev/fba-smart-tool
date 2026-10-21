import { ApiError } from "@/lib/api/client";

/** 给用户看的三段式说明：发生了什么 / 可能原因 / 怎么处理。 */
export interface ErrorCopy {
  what: string;
  why: string;
  action: string;
}

const SERVER_COPY: ErrorCopy = {
  what: "服务暂时没有完成这次操作",
  why: "服务内部出错，或刚才的请求没被正确处理。",
  action: "稍后重试。如果连续出现，把你刚做的步骤告诉维护的人。",
};

const NETWORK_COPY: ErrorCopy = {
  what: "页面连不上服务",
  why: "网络中断、服务没启动，或端口被占用。",
  action: "只保留一个后端进程，刷新页面后再试。",
};

export const ERROR_MESSAGES: Record<string, ErrorCopy> = {
  FX_RATE_REQUIRED: {
    what: "这一申报月没有可用的计征汇率",
    why: "汇率按报关完成申报之日所在月取值，缺了不能改用别的月份。",
    action: "去录入汇率后再生成预览。",
  },
  WEIGHT_CONFIRM_REQUIRED: {
    what: "毛重还没确认，导出被拦住了",
    why: "录入的单箱毛重和按单重算出的值不一致，或者混装箱超过了重量上限。",
    action: "核对警告里的箱重。确认无误后可以继续导出。",
  },
  BOX_WEIGHT_TOO_LOW: {
    what: "有多件箱轻于 2lb，导出被拦住了",
    why: "这是内部规则：一件以上的箱子，毛重不能轻于 2lb，除非确认放行。",
    action: "核对箱重。确认后可以继续导出。",
  },
};

export function errorCode(detail: unknown): string {
  if (!detail || typeof detail !== "object") return "";
  const code = (detail as { code?: unknown }).code;
  return typeof code === "string" ? code : "";
}

export function warehouseCandidatesOf(detail: unknown): string[] {
  if (!detail || typeof detail !== "object") return [];
  const raw = (detail as { warehouse_candidates?: unknown }).warehouse_candidates;
  if (!Array.isArray(raw)) return [];
  return raw.map((item) => String(item || "").trim()).filter(Boolean);
}

export function warehouseCandidatesFromError(err: unknown): string[] {
  if (!(err instanceof ApiError)) return [];
  return warehouseCandidatesOf(err.detail);
}

export function explainApiError(err: unknown): ErrorCopy {
  if (isNetworkFetchError(err)) return NETWORK_COPY;
  const status = err instanceof ApiError ? err.status : 0;
  const detail = err instanceof ApiError ? err.detail : undefined;
  const code = errorCode(detail);
  if (code && ERROR_MESSAGES[code]) return ERROR_MESSAGES[code];
  const raw = rawMessage(err);
  const candidates = warehouseCandidatesOf(detail);
  if (code === "warehouse_undecided" || candidates.length > 0) {
    const listed = candidates.length ? candidates.join("、") : "";
    const server = raw && !/unprocessable/i.test(raw) ? raw : "";
    return {
      what: "这个配送地址对应多个仓库，发票还不能确定派送仓",
      why: server || (listed ? `同一个城市有多个仓库：${listed}` : "同一个城市有多个仓库代码。"),
      action: listed ? `请选择仓库后再填写。候选：${listed}。` : "请选择仓库后再填写。",
    };
  }
  if (status >= 500 && (!raw || /internal server error/i.test(raw) || /^HTTP 5\d\d$/.test(raw))) {
    return SERVER_COPY;
  }
  if (/internal server error/i.test(raw)) return SERVER_COPY;
  if (/已取消/.test(raw)) {
    return {
      what: raw,
      why: "这次操作被取消了，没有继续提交。",
      action: "需要的话再做一次。",
    };
  }
  return {
    what: raw || "请求没有完成",
    why: "填写不满足规则，或服务返回了错误。",
    action: "按提示修改后重试。",
  };
}

export function formatErrorCopy(copy: ErrorCopy): string {
  return `发生了什么：${copy.what}\n可能原因：${copy.why}\n怎么处理：${copy.action}`;
}

function rawMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "";
}

function isNetworkFetchError(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  return /Failed to fetch|NetworkError|ECONNRESET|Load failed|network/i.test(err.message);
}
