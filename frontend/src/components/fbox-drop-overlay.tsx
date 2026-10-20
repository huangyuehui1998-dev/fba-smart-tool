import { useCallback, useEffect, useState } from "react";
import { FileBox, Loader2 } from "lucide-react";

import { useWorkflow } from "@/context/workflow-context";
import { isFboxFileDrag, resolveFboxFromDataTransfer } from "@/lib/fbox-file-manager";
import { cn } from "@/lib/utils";

/**
 * 全局 .fbox 拖拽层：捕获阶段优先于 usePreventBrowserFileDrop，打开工程文件。
 */
export function FboxDropOverlay() {
  const { loadFboxFromDrop } = useWorkflow();
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);

  const onDragEnter = useCallback((e: DragEvent) => {
    if (!isFboxFileDrag(e)) return;
    e.preventDefault();
    e.stopPropagation();
    setDragging(true);
  }, []);

  const onDragOver = useCallback((e: DragEvent) => {
    if (!isFboxFileDrag(e)) return;
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
    setDragging(true);
  }, []);

  const onDragLeave = useCallback((e: DragEvent) => {
    if (!isFboxFileDrag(e)) return;
    if (e.relatedTarget && document.documentElement.contains(e.relatedTarget as Node)) return;
    setDragging(false);
  }, []);

  const onDrop = useCallback(
    async (e: DragEvent) => {
      if (!isFboxFileDrag(e) || !e.dataTransfer) return;
      e.preventDefault();
      e.stopPropagation();
      setDragging(false);
      setLoading(true);
      try {
        const resolved = await resolveFboxFromDataTransfer(e.dataTransfer);
        if (!resolved) return;
        await loadFboxFromDrop(resolved.handle, resolved.file);
      } finally {
        setLoading(false);
      }
    },
    [loadFboxFromDrop],
  );

  useEffect(() => {
    window.addEventListener("dragenter", onDragEnter, true);
    window.addEventListener("dragover", onDragOver, true);
    window.addEventListener("dragleave", onDragLeave, true);
    window.addEventListener("drop", onDrop, true);
    return () => {
      window.removeEventListener("dragenter", onDragEnter, true);
      window.removeEventListener("dragover", onDragOver, true);
      window.removeEventListener("dragleave", onDragLeave, true);
      window.removeEventListener("drop", onDrop, true);
    };
  }, [onDragEnter, onDragOver, onDragLeave, onDrop]);

  if (!dragging && !loading) return null;

  return (
    <div
      className={cn(
        "pointer-events-none fixed inset-0 z-[100] flex items-center justify-center bg-primary/10 backdrop-blur-[2px]",
        dragging && "border-4 border-dashed border-primary",
      )}
      aria-hidden
    >
      <div className="flex flex-col items-center gap-3 rounded-xl border border-primary/40 bg-card/95 px-10 py-8 shadow-lg">
        {loading ? (
          <Loader2 className="h-12 w-12 animate-spin text-primary" />
        ) : (
          <FileBox className="h-12 w-12 text-primary" />
        )}
        <p className="text-base font-semibold text-foreground">
          {loading ? "正在打开工程文件…" : "松开鼠标打开 .fbox 工程"}
        </p>
        <p className="text-xs text-muted-foreground">支持拖入历史工程，软件升级后仍可打开</p>
      </div>
    </div>
  );
}
