import type { ReactNode } from "react";

import type { ErrorCopy } from "@/lib/error-messages";

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
      <p>
        <span className="font-semibold">发生了什么：</span>
        {copy.what}
      </p>
      <p>
        <span className="font-semibold">可能原因：</span>
        {copy.why}
      </p>
      <p>
        <span className="font-semibold">怎么处理：</span>
        {copy.action}
      </p>
      {extra}
    </div>
  );
}
