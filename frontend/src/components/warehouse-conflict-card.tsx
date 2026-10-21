import { useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  applyWarehouseChoice,
  type WarehouseChoice,
  type WarehouseWarning,
} from "@/lib/warehouse-choice";

export function WarehouseConflictCards({
  warnings,
  rows,
  onRows,
}: {
  warnings: WarehouseWarning[];
  rows: Record<string, unknown>[];
  onRows: (rows: Record<string, unknown>[]) => void;
}) {
  const [choiceById, setChoiceById] = useState<Record<string, WarehouseChoice>>({});

  if (!warnings.length) return null;

  return (
    <div className="space-y-2">
      {warnings.map((warning) => {
        const choice = choiceById[warning.shipment_id] ?? "csv";
        const pick = (next: WarehouseChoice) => {
          setChoiceById((prev) => ({ ...prev, [warning.shipment_id]: next }));
          onRows(applyWarehouseChoice(rows, warning, next));
        };
        return (
          <article
            key={warning.shipment_id}
            data-testid="warehouse-warning-card"
            className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950"
          >
            <p className="font-medium">仓库代码来源不一致</p>
            <p className="mt-1 text-xs">
              {warning.message ||
                `CSV=${warning.csv_code}，PDF=${warning.pdf_code}，已采用 CSV，请人工确认`}
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                variant={choice === "csv" ? "default" : "outline"}
                className={cn(choice === "csv" && "bg-amber-700 hover:bg-amber-700")}
                onClick={() => pick("csv")}
              >
                采用 CSV（默认）
              </Button>
              <Button
                type="button"
                size="sm"
                variant={choice === "pdf" ? "default" : "outline"}
                onClick={() => pick("pdf")}
              >
                采用 PDF
              </Button>
            </div>
          </article>
        );
      })}
    </div>
  );
}
