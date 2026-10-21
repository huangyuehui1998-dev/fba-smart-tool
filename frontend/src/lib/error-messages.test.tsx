import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ErrorNotice } from "@/components/feedback/error-notice";
import { ApiError } from "@/lib/api/client";
import { explainApiError, formatErrorCopy } from "@/lib/error-messages";
import { formatApiError } from "@/lib/format-api-error";

describe("explainApiError", () => {
  it("renders the three-part weight confirm copy", () => {
    const copy = explainApiError(
      new ApiError(409, "毛重需要确认后才能导出", {
        code: "WEIGHT_CONFIRM_REQUIRED",
        message: "毛重需要确认后才能导出",
      }),
    );
    const html = renderToStaticMarkup(<ErrorNotice copy={copy} />);
    expect(html).toContain("发生了什么");
    expect(html).toContain("可能原因");
    expect(html).toContain("怎么处理");
    expect(html).toContain(copy.what);
    expect(formatErrorCopy(copy)).toContain("发生了什么");
  });

  it("does not blame a cancelled load on validation rules", () => {
    const text = formatApiError(new Error("已取消加载"));
    expect(text).toContain("已取消加载");
    expect(text).not.toContain("填写不满足规则");
  });

  it("explains a multi-warehouse 422 in Chinese and names the warehouses", () => {
    const err = new ApiError(422, "Unprocessable Content", {
      code: "warehouse_undecided",
      detail: "货件 CSV 配送地址对应多个仓库：TST1、TST2，请在面板上选择仓库",
      message: "货件 CSV 配送地址对应多个仓库：TST1、TST2，请在面板上选择仓库",
      warehouse_candidates: ["TST1", "TST2"],
    });
    const copy = explainApiError(err);
    const text = formatApiError(err);
    expect(text).not.toMatch(/unprocessable/i);
    expect(copy.what).toContain("多个仓库");
    expect(text).toContain("选择仓库");
    expect(text).toContain("TST1");
    expect(text).toContain("TST2");
  });

  it("does not show Internal Server Error", () => {
    const html = renderToStaticMarkup(
      <ErrorNotice copy={explainApiError(new ApiError(500, "Internal Server Error"))} />,
    );
    expect(html).not.toContain("Internal Server Error");
    expect(formatApiError(new ApiError(500, "Internal Server Error"))).not.toContain(
      "Internal Server Error",
    );
  });
});
