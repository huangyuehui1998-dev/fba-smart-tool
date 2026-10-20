/** Step3 运输方式。默认 SPD-合作承运人，写入任务快照。 */
export const TRANSPORT_MODES = [
  { value: "spd_partnered", label: "SPD-合作承运人" },
  { value: "spd_own", label: "SPD-自选承运人" },
  { value: "ltl", label: "LTL-FTL" },
] as const;

export type TransportMode = (typeof TRANSPORT_MODES)[number]["value"];

export const DEFAULT_TRANSPORT_MODE: TransportMode = "spd_partnered";

export function normalizeTransportMode(value: unknown): TransportMode {
  const raw = String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/-/g, "_");
  if (raw === "spd_own" || raw === "own" || raw === "spd_自选承运人") return "spd_own";
  if (raw === "ltl" || raw === "ftl" || raw === "ltl_ftl") return "ltl";
  return DEFAULT_TRANSPORT_MODE;
}

export function transportModeLabel(mode: TransportMode): string {
  return TRANSPORT_MODES.find((item) => item.value === mode)?.label ?? TRANSPORT_MODES[0].label;
}
