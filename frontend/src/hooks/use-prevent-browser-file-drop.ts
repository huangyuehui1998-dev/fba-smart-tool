import { useEffect } from "react";

import { isFboxFileDrag } from "@/lib/fbox-file-manager";

const DROP_ZONE_SELECTOR = "[data-file-drop]";

function isInsideDropZone(target: EventTarget | null): boolean {
  return target instanceof Element && Boolean(target.closest(DROP_ZONE_SELECTOR));
}

/** 阻止浏览器在页面任意位置 drop 文件时自动打开/下载；保留 .fbox 全局拖入与 data-file-drop 上传区。 */
export function usePreventBrowserFileDrop(enabled = true) {
  useEffect(() => {
    if (!enabled) return;

    const preventDragOver = (event: DragEvent) => {
      if (isFboxFileDrag(event)) return;
      event.preventDefault();
    };

    const preventDrop = (event: DragEvent) => {
      if (isFboxFileDrag(event)) return;
      if (isInsideDropZone(event.target)) return;
      event.preventDefault();
    };

    window.addEventListener("dragover", preventDragOver);
    window.addEventListener("drop", preventDrop);
    return () => {
      window.removeEventListener("dragover", preventDragOver);
      window.removeEventListener("drop", preventDrop);
    };
  }, [enabled]);
}

export const fileDropZoneProps = {
  "data-file-drop": true,
} as const;
