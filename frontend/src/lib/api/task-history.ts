import { apiFetchJson, apiPostJson } from "@/lib/api/client";
import type { TaskHistorySnapshot } from "@/lib/task-history-snapshot";

export interface TaskHistoryIndexRow {
  id: string;
  name: string;
  updated_at: string;
  step: number;
  saved_at?: string;
}

export function fetchTaskHistoryList() {
  return apiFetchJson<{ tasks: TaskHistoryIndexRow[] }>("/api/tasks/history");
}

export function saveTaskHistory(snapshot: TaskHistorySnapshot, name?: string) {
  return apiPostJson<{
    ok: boolean;
    task_id: string;
    task_name: string;
    updated_at?: string;
  }>("/api/tasks/history", { snapshot, name: name?.trim() || undefined });
}

export function loadTaskHistory(taskId: string) {
  return apiFetchJson<{ snapshot: Record<string, unknown> }>(`/api/tasks/history/${taskId}`);
}

export function renameTaskHistory(taskId: string, name: string) {
  return apiFetchJson<{ ok: boolean; task_id: string; name: string }>(
    `/api/tasks/history/${taskId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    },
  );
}

export function deleteTaskHistory(taskId: string) {
  return apiFetchJson<{ ok: boolean; task_id: string }>(`/api/tasks/history/${taskId}`, {
    method: "DELETE",
  });
}
