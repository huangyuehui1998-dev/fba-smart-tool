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
