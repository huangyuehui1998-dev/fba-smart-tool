import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

export type TableScrollAreaProps = HTMLAttributes<HTMLDivElement> & {
  children: ReactNode;
  /** CSS max-height for vertical scrolling */
  maxHeight?: string;
  /** card = bordered preview panel; plain = scroll only (inside Card) */
  variant?: "card" | "plain";
};

const STICKY_HEAD =
  "[&_thead_th]:sticky [&_thead_th]:top-0 [&_thead_th]:z-10 [&_thead_th]:bg-muted/90 [&_thead_th]:backdrop-blur-sm";

/**
 * 表格预览区：同时支持横向与纵向滚动，避免宽表/长表被裁切。
 */
export function TableScrollArea({
  children,
  className,
  maxHeight = "min(70vh, 32rem)",
  variant = "card",
  style,
  ...props
}: TableScrollAreaProps) {
  return (
    <div
      className={cn(
        "w-full min-w-0 overflow-auto overscroll-contain",
        STICKY_HEAD,
        variant === "card" && "rounded-lg border border-border bg-card",
        className,
      )}
      style={{ maxHeight, ...style }}
      {...props}
    >
      {children}
    </div>
  );
}
