export async function exportRoutingPreview(files: File[]) {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }

  const res = await fetch("/api/routing/preview", {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "预览失败");
  }

  return res.json();
}

/** S8 D2：预览 + 仓库代码警告（CSV 优先；文件名不一致 / 只能用文件名 / 都没有时给提示） */
export async function exportRoutingPreviewWithWarnings(files: File[]): Promise<{ rows: any[]; warnings: string[] }> {
  const formData = new FormData();
  for (const file of files) formData.append("files", file);
  const res = await fetch("/api/routing/preview", { method: "POST", body: formData });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "预览失败");
  }
  let warnings: string[] = [];
  const raw = res.headers.get("X-Routing-Warnings");
  if (raw) {
    try {
      warnings = JSON.parse(decodeURIComponent(raw)) as string[];
    } catch {
      warnings = [];
    }
  }
  return { rows: (await res.json()) as any[], warnings };
}

export async function downloadRoutingForwarder(forwarderData: any[]) {
  const res = await fetch("/api/routing/export", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ forwarder: forwarderData }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "导出失败");
  }

  const blob = await res.blob();
  const { triggerBrowserDownload } = await import("./client");
  await triggerBrowserDownload(blob, "刷仓货代表.xlsx");
}

export interface RoutingSnapshot {
  id: string;
  name: string;
  created_at: string;
  forwarder_data: any[];
}

export async function saveRoutingSnapshot(taskId: string, name: string, forwarderData: any[]) {
  const res = await fetch(`/api/routing/snapshots/${taskId}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name, forwarder_data: forwarderData }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "保存快照失败");
  }

  return res.json();
}

export async function getRoutingSnapshots(taskId: string): Promise<RoutingSnapshot[]> {
  const res = await fetch(`/api/routing/snapshots/${taskId}`);
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "获取快照列表失败");
  }
  const data = await res.json();
  return data.snapshots || [];
}

export async function deleteRoutingSnapshot(snapshotId: string) {
  const res = await fetch(`/api/routing/snapshots/${snapshotId}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "删除快照失败");
  }
  return res.json();
}
