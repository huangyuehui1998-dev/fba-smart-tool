import { Fragment, type ReactNode } from "react";

import type { ErrorCopy } from "@/lib/error-messages";

const ERROR_LINE = /^(发生了什么|可能原因|怎么处理)：(.*)$/;

/** 三段标题同一列宽，说明从同一位置起排。 */
export function ErrorLines({ text }: { text: string }) {
  const parts = text.split("\n").map((line) => {
    const match = line.match(ERROR_LINE);
    return match ? { label: match[1], value: match[2] } : null;
  });
  if (!parts.length || parts.some((part) => part == null)) {
    return <span className="whitespace-pre-wrap">{text}</span>;
  }
  return (
    <div className="grid grid-cols-[6.5rem_1fr] gap-x-3 gap-y-1">
      {parts.map((part) => (
        <Fragment key={part!.label}>
          <span className="font-semibold">{part!.label}</span>
          <span>{part!.value}</span>
        </Fragment>
      ))}
    </div>
  );
}

/** 固定三段式报错。不用门户，方便在页面里直接展示，也方便测试读到文本。 */
export function ErrorNotice({
  copy,
  extra,
}: {
  copy: ErrorCopy | null;
  extra?: ReactNode;
}) {
  if (!copy) return null;
  return (
    <div
      role="alert"
      data-testid="error-notice"
      className="space-y-1 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
    >
      <div className="grid grid-cols-[6.5rem_1fr] gap-x-3 gap-y-1">
        <span className="font-semibold">发生了什么</span>
        <span>{copy.what}</span>
        <span className="font-semibold">可能原因</span>
        <span>{copy.why}</span>
        <span className="font-semibold">怎么处理</span>
        <span>{copy.action}</span>
      </div>
      {extra}
    </div>
  );
}
