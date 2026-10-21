/** 各步骤输入的 SHA-256。用浏览器 crypto.subtle，不用手写摘要。 */

export async function sha256HexOfText(text: string): Promise<string> {
  const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** 只纳入会影响下游箱数和重量的录入字段，键顺序固定。 */
export function canonicalInputRows(rows: ReadonlyArray<Record<string, unknown>>): string {
  return JSON.stringify(
    rows.map((row) => ({
      sku: String(row.sku ?? ""),
      fnsku: String(row.fnsku ?? ""),
      totalQty: String(row.totalQty ?? ""),
      perBox: String(row.perBox ?? ""),
      l: String(row.l ?? ""),
      w: String(row.w ?? ""),
      h: String(row.h ?? ""),
      unitKg: String(row.unitKg ?? ""),
      emptyKg: String(row.emptyKg ?? ""),
      grossKg: String(row.grossKg ?? ""),
    })),
  );
}
