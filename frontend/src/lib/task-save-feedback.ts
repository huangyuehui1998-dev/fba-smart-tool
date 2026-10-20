import { toast } from "sonner";

export const SAVE_CANCELLED_MESSAGE = "已取消保存 .fbox 文件（任务已存入历史任务库）";

export function downloadStartedMessage(filename: string): string {
  return `已开始下载：${filename}`;
}

export function downloadCancelledMessage(filename: string): string {
  return `已取消保存：${filename}`;
}

export function isAbortError(err: unknown): boolean {
  return err instanceof Error && err.name === "AbortError";
}

export function notifySaveCancelled(): void {
  toast.info(SAVE_CANCELLED_MESSAGE);
}

export function notifyDownloadCancelled(filename: string): void {
  toast.info(downloadCancelledMessage(filename));
}

export function notifyDownloadStarted(filename: string): void {
  toast.success(downloadStartedMessage(filename));
}

/** 先写入历史任务库，再写 .fbox。用户取消另存为时提示历史库已有一份。 */
export async function saveTaskFileAfterHistory(options: {
  saveHistory: () => Promise<unknown>;
  writeFile: () => Promise<string>;
}): Promise<string> {
  await options.saveHistory();
  try {
    return await options.writeFile();
  } catch (err) {
    if (isAbortError(err)) {
      notifySaveCancelled();
      throw new Error("已取消保存");
    }
    throw err;
  }
}
