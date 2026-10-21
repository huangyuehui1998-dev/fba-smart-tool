import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({
  toast: {
    info: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { toast } from "sonner";

import {
  SAVE_CANCELLED_MESSAGE,
  downloadCancelledMessage,
  downloadStartedMessage,
  notifyDownloadCancelled,
  notifyDownloadStarted,
  saveTaskFileAfterHistory,
} from "./task-save-feedback";

describe("save and download feedback", () => {
  beforeEach(() => {
    vi.mocked(toast.info).mockClear();
    vi.mocked(toast.success).mockClear();
  });

  it("writes history then toasts when the save picker is cancelled", async () => {
    const saveHistory = vi.fn().mockResolvedValue("TESTTASK");
    const abort = Object.assign(new Error("The user aborted a request."), { name: "AbortError" });
    const writeFile = vi.fn().mockRejectedValue(abort);

    await expect(saveTaskFileAfterHistory({ saveHistory, writeFile })).rejects.toThrow("已取消保存");

    expect(saveHistory).toHaveBeenCalledTimes(1);
    expect(writeFile).toHaveBeenCalledTimes(1);
    expect(toast.info).toHaveBeenCalledWith(SAVE_CANCELLED_MESSAGE);
    expect(SAVE_CANCELLED_MESSAGE).toBe("已取消保存 .fbox 文件（任务已存入历史任务库）");
  });

  it("toasts when a download picker is cancelled or falls back", () => {
    notifyDownloadCancelled("STA.xlsx");
    expect(toast.info).toHaveBeenCalledWith(downloadCancelledMessage("STA.xlsx"));
    expect(downloadCancelledMessage("STA.xlsx")).toBe("已取消保存：STA.xlsx");

    notifyDownloadStarted("STA.xlsx");
    expect(toast.success).toHaveBeenCalledWith(downloadStartedMessage("STA.xlsx"));
    expect(downloadStartedMessage("STA.xlsx")).toBe("已开始下载：STA.xlsx");
  });
});
