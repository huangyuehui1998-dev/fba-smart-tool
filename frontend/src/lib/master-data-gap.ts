export type MasterDataGap = {
  sku: string;
  missing: string[];
};

/** Step1 主库缺口横幅。空列表返回空串。 */
export function masterDataGapBannerText(gaps: MasterDataGap[]): string {
  const count = gaps.filter((gap) => gap.sku.trim() && gap.missing.length).length;
  if (!count) return "";
  return `${count} 个 SKU 缺 ASIN/品名/单品尺寸`;
}
