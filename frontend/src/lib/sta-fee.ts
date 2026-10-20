/** STA 实际配置费是否落在估算区间外。区间端点算在范围内。 */
export function staFeeOutOfRange(entered: number, estimateMin: number, estimateMax: number): boolean {
  if (!Number.isFinite(entered) || !Number.isFinite(estimateMin) || !Number.isFinite(estimateMax)) {
    return false;
  }
  return entered < estimateMin || entered > estimateMax;
}
