export const COMPARE_COLUMNS = [
  "箱号",
  "SKU",
  "申报 L/W/H/kg",
  "实测 L/W/H/kg",
  "差值",
  "体积重差",
  "计费重差",
  "状态",
] as const;

export const TABLE_SCROLL_CLASS = "overflow-x-auto";
export const TABLE_HEAD_CLASS = "sticky top-0 z-10 bg-background";
export const PAGE_PADDING_CLASS = "pb-24";
export const ABNORMAL_CLASS = "text-red-600";
export const CONFIRM_NEW_SPEC_TITLE = "生成新箱规版本";

export interface CompareRow {
  箱号?: string;
  SKU?: string;
  "申报 L/W/H/kg"?: string;
  "实测 L/W/H/kg"?: string;
  差值?: string;
  体积重差?: string;
  计费重差?: string;
  状态?: string;
  status_class?: string;
}

export interface CompareReport {
  columns?: string[];
  rows?: CompareRow[];
  quality?: { match_status?: string; fba_box_id?: string; kind?: string }[];
  summary?: {
    headline?: string;
    reference?: string;
    dup_note?: string;
    dup_detail?: string;
    suggest_text?: string;
  };
  message?: string;
}

export function dupExcludedNote(duplicateCount: number): string {
  return `${duplicateCount} 个重复箱号未计入汇总`;
}

export function statusClass(status: string | undefined): string {
  return status === "异常" ? ABNORMAL_CLASS : "";
}

export function legacyImportMessage(path: string): string {
  return `检测到旧数据目录 ${path}，是否导入`;
}

export function compareColumns(report: CompareReport): string[] {
  return report.columns?.length ? report.columns : [...COMPARE_COLUMNS];
}
