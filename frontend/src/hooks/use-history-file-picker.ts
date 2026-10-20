import { useCallback, useEffect, useRef, useState, type SetStateAction } from "react";
import type { HistoryFileItem } from "@/lib/api/history-files";
import { getCachedHistoryFile, getHistoryFileCached } from "@/lib/history-file-cache";
import { formatApiError } from "@/lib/format-api-error";

export type HistoryFileKind = "csv" | "pdf";

interface UseHistoryFilePickerOptions {
  kind: HistoryFileKind;
  files: File[];
  setFiles: (files: SetStateAction<File[]>) => void;
  selectedIds: Set<string>;
  setSelectedIds: React.Dispatch<React.SetStateAction<Set<string>>>;
  onPickError?: (message: string | null) => void;
  onAdded?: (itemId: string, fileName: string) => void;
  /** 列表接口不可用时，mock 项跳过网络直接生成本地占位 File */
  skipNetworkForMock?: boolean;
}

function normalizeFileList(prev: File[]): File[] {
  return Array.isArray(prev) ? prev : [];
}

function appendUniqueFile(prev: File[], file: File): File[] {
  const list = normalizeFileList(prev);
  return list.some((f) => f.name === file.name) ? list : [...list, file];
}

/** 可靠的历史文件点选：functional update + 世代号，避免快速连点丢文件 */
export function useHistoryFilePicker({
  kind,
  files,
  setFiles,
  selectedIds,
  setSelectedIds,
  onPickError,
  onAdded,
  skipNetworkForMock = false,
}: UseHistoryFilePickerOptions) {
  const intendedIdsRef = useRef<Set<string>>(new Set());
  const generationRef = useRef<Map<string, number>>(new Map());
  const nameToIdRef = useRef<Map<string, string>>(new Map());
  const [loadingIds, setLoadingIds] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    intendedIdsRef.current = new Set(selectedIds);
  }, [selectedIds]);

  const bumpGeneration = (id: string) => {
    const next = (generationRef.current.get(id) ?? 0) + 1;
    generationRef.current.set(id, next);
    return next;
  };

  const setLoading = (id: string, loading: boolean) => {
    setLoadingIds((prev) => {
      const next = new Set(prev);
      if (loading) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const toggle = useCallback(
    async (item: HistoryFileItem) => {
      try {
        const wantSelect = !intendedIdsRef.current.has(item.id);
        onPickError?.(null);

        if (wantSelect) {
          if (loadingIds.has(item.id)) return;

          intendedIdsRef.current.add(item.id);
          setSelectedIds((prev) => new Set(prev).add(item.id));

          const cached = getCachedHistoryFile(kind, item);
          if (cached) {
            setFiles((prev) => appendUniqueFile(prev, cached));
            nameToIdRef.current.set(cached.name, item.id);
            onAdded?.(item.id, cached.name);
            return;
          }

          const gen = bumpGeneration(item.id);
          setLoading(item.id, true);

          try {
            const file = await getHistoryFileCached(kind, item, { skipNetworkForMock });
            if (generationRef.current.get(item.id) !== gen) return;
            if (!intendedIdsRef.current.has(item.id)) return;

            setFiles((prev) => appendUniqueFile(prev, file));
            nameToIdRef.current.set(file.name, item.id);
            onAdded?.(item.id, file.name);
          } catch (err) {
            if (generationRef.current.get(item.id) !== gen) return;
            intendedIdsRef.current.delete(item.id);
            setSelectedIds((prev) => {
              const next = new Set(prev);
              next.delete(item.id);
              return next;
            });
            onPickError?.(formatApiError(err));
          } finally {
            if (generationRef.current.get(item.id) === gen) {
              setLoading(item.id, false);
            }
          }
        } else {
          bumpGeneration(item.id);
          intendedIdsRef.current.delete(item.id);
          setSelectedIds((prev) => {
            const next = new Set(prev);
            next.delete(item.id);
            return next;
          });
          nameToIdRef.current.delete(item.name);
          setFiles((prev) => normalizeFileList(prev).filter((f) => f.name !== item.name));
          setLoading(item.id, false);
        }
      } catch (err) {
        onPickError?.(formatApiError(err));
      }
    },
    [kind, loadingIds, onAdded, onPickError, setFiles, setSelectedIds, skipNetworkForMock],
  );

  const removeFileAt = useCallback(
    (index: number) => {
      const list = normalizeFileList(files);
      const file = list[index];
      if (!file) return;
      setFiles((prev) => normalizeFileList(prev).filter((_, i) => i !== index));
      const historyId = nameToIdRef.current.get(file.name);
      if (historyId) {
        bumpGeneration(historyId);
        intendedIdsRef.current.delete(historyId);
        nameToIdRef.current.delete(file.name);
        setSelectedIds((prev) => {
          const next = new Set(prev);
          next.delete(historyId);
          return next;
        });
        setLoading(historyId, false);
      }
    },
    [files, setFiles, setSelectedIds],
  );

  return { toggle, removeFileAt, loadingIds };
}
