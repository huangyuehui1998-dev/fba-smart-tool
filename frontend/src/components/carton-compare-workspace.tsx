import { useState } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  ABNORMAL_CLASS,
  CONFIRM_NEW_SPEC_TITLE,
  PAGE_PADDING_CLASS,
  TABLE_HEAD_CLASS,
  TABLE_SCROLL_CLASS,
  compareColumns,
  statusClass,
  type CompareReport,
} from "@/lib/carton-compare-view";
import { cn } from "@/lib/utils";

export function CartonCompareWorkspace({
  report,
  onCreateMeasuredSpec,
}: {
  report: CompareReport;
  onCreateMeasuredSpec?: () => void;
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const columns = compareColumns(report);
  const headline = report.summary?.headline ?? "";
  const reference = report.summary?.reference ?? "";
  const dupNote = report.summary?.dup_note ?? "";
  const dupDetail = report.summary?.dup_detail ?? dupNote;

  return (
    <div className={cn("space-y-4", PAGE_PADDING_CLASS)}>
      {report.message ? <p className="text-sm text-muted-foreground">{report.message}</p> : null}
      {headline ? <p className="text-sm font-medium">{headline}</p> : null}
      {reference ? <p className="text-sm">{reference}</p> : null}
      {dupNote ? (
        <a href="#carton-quality" data-testid="dup-excluded-note" className="text-sm text-amber-700 underline">
          {dupDetail || dupNote}
        </a>
      ) : null}
      {report.summary?.suggest_text ? (
        <div className="flex items-center gap-3">
          <p className="text-sm">{report.summary.suggest_text}</p>
          <Button type="button" size="sm" variant="secondary" onClick={() => setConfirmOpen(true)}>
            {CONFIRM_NEW_SPEC_TITLE}
          </Button>
        </div>
      ) : null}
      <div className={TABLE_SCROLL_CLASS}>
        <table className="min-w-[960px] w-full border-collapse text-xs">
          <thead className={TABLE_HEAD_CLASS}>
            <tr>
              {columns.map((column) => (
                <th key={column} className="border-b bg-background px-2 py-2 text-left font-medium">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(report.rows ?? []).map((row, index) => (
              <tr key={`${row.箱号 ?? "row"}-${index}`}>
                {columns.map((column) => {
                  const value = row[column as keyof typeof row];
                  const abnormal = column === "状态" && row.状态 === "异常";
                  return (
                    <td key={column} className={cn("border-b px-2 py-1", abnormal && (row.status_class || ABNORMAL_CLASS || statusClass(row.状态)))}>
                      {value == null ? "" : String(value)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <section id="carton-quality" className="space-y-2">
        <h2 className="text-sm font-medium">过机数据质量问题</h2>
        <ul className="text-xs text-muted-foreground">
          {(report.quality ?? []).map((row, index) => (
            <li key={`${row.fba_box_id ?? "q"}-${index}`}>
              {row.match_status} {row.fba_box_id}
            </li>
          ))}
        </ul>
      </section>
      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{CONFIRM_NEW_SPEC_TITLE}</AlertDialogTitle>
            <AlertDialogDescription>新版本来源是实测均值，不会自动设为默认箱规。</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setConfirmOpen(false);
                onCreateMeasuredSpec?.();
              }}
            >
              确认
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
