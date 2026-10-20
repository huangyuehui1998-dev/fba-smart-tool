export interface Step1IssueInput {
  row_index: number;
  field?: string;
  message?: string;
}

export interface Step1IssueSummary {
  blockCount: number;
  warnCount: number;
  blockRows: Set<number>;
  warnRows: Set<number>;
}

export function summarizeStep1Issues(
  errors: Step1IssueInput[],
  warnings: Step1IssueInput[],
): Step1IssueSummary {
  const blockRows = new Set(errors.map((item) => item.row_index));
  const warnRows = new Set(warnings.map((item) => item.row_index));
  return {
    blockCount: errors.length,
    warnCount: warnings.length,
    blockRows,
    warnRows,
  };
}

export function visibleStep1Indexes(
  rowCount: number,
  summary: Step1IssueSummary,
  onlyIssues: boolean,
): number[] {
  const indexes: number[] = [];
  for (let i = 0; i < rowCount; i += 1) {
    const problem = summary.blockRows.has(i) || summary.warnRows.has(i);
    if (!onlyIssues || problem) indexes.push(i);
  }
  return indexes;
}

export function step1FixHint(
  rowIndex: number,
  errors: Step1IssueInput[],
  warnings: Step1IssueInput[],
): string {
  const missing = errors.filter((item) => item.row_index === rowIndex).map((item) => item.field).filter(Boolean);
  if (missing.length) return `补上${missing.join("、")}`;
  const warning = warnings.find((item) => item.row_index === rowIndex);
  return warning?.message || "";
}
