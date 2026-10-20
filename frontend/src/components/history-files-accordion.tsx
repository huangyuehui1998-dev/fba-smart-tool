import { useEffect, useState } from "react";
import { FileSpreadsheet, FileText, Loader2, CheckCircle2 } from "lucide-react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";
import { formatFileSize } from "@/lib/box-editor";
import { formatApiError } from "@/lib/format-api-error";
import {
  MOCK_HISTORY_FILES,
  fetchHistoryFiles,
  type HistoryFileItem,
} from "@/lib/api/history-files";
import { prefetchHistoryFiles } from "@/lib/history-file-cache";

function HistoryFileRow({
  item,
  kind,
  selected,
  loading,
  successFlash,
  onToggle,
}: {
  item: HistoryFileItem;
  kind: "csv" | "pdf";
  selected: boolean;
  loading: boolean;
  successFlash: boolean;
  onToggle: (item: HistoryFileItem) => void;
}) {
  const Icon = kind === "csv" ? FileSpreadsheet : FileText;
  const tone =
    kind === "csv"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : "border-rose-200 bg-rose-50 text-rose-700";

  return (
    <li
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      aria-busy={loading}
      aria-label={`${selected ? "取消选择" : "选择"} ${item.name}`}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onToggle(item);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          e.stopPropagation();
          onToggle(item);
        }
      }}
      className={cn(
        "flex cursor-pointer items-center gap-2 rounded-md border px-2.5 py-2 transition-all duration-300 outline-none",
        "hover:bg-muted/60 focus-visible:ring-2 focus-visible:ring-primary/40",
        selected && !loading && "border-primary/35 bg-primary/[0.07]",
        !selected && "border-border bg-card",
        loading && "border-primary/20 bg-muted/40",
        successFlash && "scale-[1.01] border-emerald-400/60 bg-emerald-50/80 shadow-sm",
      )}
    >
      <Checkbox
        checked={selected}
        onCheckedChange={() => undefined}
        tabIndex={-1}
        className="pointer-events-none"
        aria-hidden
      />
      <span className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-md border", tone)}>
        {loading ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : successFlash ? (
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
        ) : (
          <Icon className="h-3.5 w-3.5" />
        )}
      </span>
      <div className="min-w-0 flex-1 select-none">
        <div className="truncate text-xs font-medium text-foreground">{item.name}</div>
        <div className="text-[10px] text-muted-foreground">
          {formatFileSize(item.size_bytes)}
          {item.source !== "mock" ? ` · ${item.source}` : " · 测试数据"}
          {loading ? " · 正在加入上传区…" : selected ? " · 已加入上方上传区" : " · 点击整行选中"}
        </div>
      </div>
    </li>
  );
}

function HistoryListSection({
  title,
  kind,
  items,
  selectedIds,
  loadingIds,
  successFlashIds,
  onToggle,
}: {
  title: string;
  kind: "csv" | "pdf";
  items: HistoryFileItem[];
  selectedIds: Set<string>;
  loadingIds: Set<string>;
  successFlashIds: Set<string>;
  onToggle: (item: HistoryFileItem) => void;
}) {
  const selectedCount = items.filter((i) => selectedIds.has(i.id)).length;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-xs font-semibold text-foreground">{title}</h4>
        {selectedCount > 0 && (
          <span className="text-[10px] font-medium text-primary">已选 {selectedCount} 个</span>
        )}
      </div>
      {items.length === 0 ? (
        <p className="text-[11px] text-muted-foreground">暂无历史文件</p>
      ) : (
        <ul className="space-y-1.5">
          {items.map((item) => (
            <HistoryFileRow
              key={item.id}
              item={item}
              kind={kind}
              selected={selectedIds.has(item.id)}
              loading={loadingIds.has(item.id)}
              successFlash={successFlashIds.has(item.id)}
              onToggle={onToggle}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

export function HistoryFilesAccordion({
  selectedHistoryCSVs,
  selectedHistoryPDFs,
  csvLoadingIds,
  pdfLoadingIds,
  csvSuccessFlashIds,
  pdfSuccessFlashIds,
  onToggleCsv,
  onTogglePdf,
  pickError,
  onHistoryReady,
}: {
  selectedHistoryCSVs: Set<string>;
  selectedHistoryPDFs: Set<string>;
  csvLoadingIds: Set<string>;
  pdfLoadingIds: Set<string>;
  csvSuccessFlashIds: Set<string>;
  pdfSuccessFlashIds: Set<string>;
  onToggleCsv: (item: HistoryFileItem) => void;
  onTogglePdf: (item: HistoryFileItem) => void;
  pickError?: string | null;
  onHistoryReady?: (meta: { skipNetworkForMock: boolean }) => void;
}) {
  const [data, setData] = useState(MOCK_HISTORY_FILES);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;

    let cancelled = false;
    setLoading(true);
    fetchHistoryFiles()
      .then((res) => {
        if (!cancelled) {
          setData(res);
          setLoadError(null);
          onHistoryReady?.({ skipNetworkForMock: false });
          prefetchHistoryFiles("pdf", res.pdf, { concurrency: 4 });
          prefetchHistoryFiles("csv", res.csv, { concurrency: 4 });
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setData(MOCK_HISTORY_FILES);
          setLoadError(
            `无法连接历史文件接口（${formatApiError(err)}）。已显示本地 Mock 列表。`,
          );
          onHistoryReady?.({ skipNetworkForMock: true });
          prefetchHistoryFiles("pdf", MOCK_HISTORY_FILES.pdf, {
            skipNetworkForMock: true,
            concurrency: 4,
          });
          prefetchHistoryFiles("csv", MOCK_HISTORY_FILES.csv, {
            skipNetworkForMock: true,
            concurrency: 4,
          });
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [onHistoryReady]);

  return (
    <div className="space-y-2">
      <Accordion type="single" collapsible className="rounded-lg border border-border bg-card px-4 shadow-sm">
        <AccordionItem value="history-files" className="border-none">
          <AccordionTrigger className="py-3 text-sm hover:no-underline">
            <span>📂 从历史测试文件中快速选择（点击整行即可加入上方上传区）</span>
            {loading && <Loader2 className="ml-2 h-3.5 w-3.5 animate-spin text-muted-foreground" />}
          </AccordionTrigger>
          <AccordionContent>
            <div className="grid grid-cols-1 gap-4 pb-1 md:grid-cols-2">
              <HistoryListSection
                title="历史 FBA CSV"
                kind="csv"
                items={data.csv}
                selectedIds={selectedHistoryCSVs}
                loadingIds={csvLoadingIds}
                successFlashIds={csvSuccessFlashIds}
                onToggle={onToggleCsv}
              />
              <HistoryListSection
                title="历史 FBA 箱唛 PDF"
                kind="pdf"
                items={data.pdf}
                selectedIds={selectedHistoryPDFs}
                loadingIds={pdfLoadingIds}
                successFlashIds={pdfSuccessFlashIds}
                onToggle={onTogglePdf}
              />
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
      {(loadError || pickError) && (
        <p className="text-[11px] text-destructive">{pickError ?? loadError}</p>
      )}
    </div>
  );
}
