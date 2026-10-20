/** 亚马逊主导模式下应隐藏的本地箱号 / 贴标映射类日志（非致命宏观错误）。 */
const MAPPING_NOISE_PATTERNS: RegExp[] = [
  /无法在亚马逊 CSV 中找到内容一致的箱/,
  /本地\s*Box-\d+/i,
  /本地箱号/,
  /贴标映射/,
  /映射差异/,
  /存在多个内容相同的亚马逊箱/,
  /无法建立贴标映射/,
  /本地装箱方案为空/,
  /未解析到有效箱数据，无法建立/,
];

export function isMappingNoiseLog(line: string): boolean {
  return MAPPING_NOISE_PATTERNS.some((pattern) => pattern.test(line));
}

export function filterStep4Logs(lines: string[], isStrictMapping: boolean): string[] {
  if (isStrictMapping) return lines;
  return lines.filter((line) => !isMappingNoiseLog(line));
}
