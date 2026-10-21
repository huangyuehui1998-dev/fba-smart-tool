/** 一键修正：毛重 = 装量 × 单重 + 皮重。结果保留 3 位，避免二进制小数。 */
export function grossFromUnitQtyTare(qty: number, unit: number, tare: number): number {
  return Math.round((qty * unit + tare) * 1000) / 1000;
}
