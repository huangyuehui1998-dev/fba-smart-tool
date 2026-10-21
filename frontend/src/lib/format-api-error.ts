import { ApiError } from "@/lib/api/client";
import { explainApiError, formatErrorCopy } from "@/lib/error-messages";

const NETWORK_ERROR_HINT =
  "无法连接后端（网络中断、后端未启动或端口冲突）。请只保留一个后端进程，刷新页面后重试。";

function isNetworkFetchError(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  return /Failed to fetch|NetworkError|ECONNRESET|Load failed|network/i.test(err.message);
}

export function extractApiErrors(err: unknown): string[] {
  if (err instanceof ApiError) {
    const detail = err.detail;
    if (detail && typeof detail === "object" && Array.isArray((detail as { errors?: string[] }).errors)) {
      return (detail as { errors: string[] }).errors;
    }
    return [err.message];
  }
  if (err instanceof Error) return [err.message];
  return ["请求失败，请稍后重试"];
}

export function formatApiError(err: unknown): string {
  if (isNetworkFetchError(err)) return NETWORK_ERROR_HINT;
  return formatErrorCopy(explainApiError(err));
}
