export const FILL_FAILED_EXPORT_BLOCK =
  "自动填写失败，已阻止导出空模板。请先处理上面的错误，再重新开始自动填写。";

export function exportBlockAfterFailedFill(fillFailed: boolean): string | null {
  return fillFailed ? FILL_FAILED_EXPORT_BLOCK : null;
}
