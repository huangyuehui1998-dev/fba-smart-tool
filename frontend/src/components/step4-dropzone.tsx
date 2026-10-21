import { useId, useState, type DragEvent } from "react";
import { FileSpreadsheet, FileText, UploadCloud, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatFileSize } from "@/lib/box-editor";
import { fileDropZoneProps } from "@/hooks/use-prevent-browser-file-drop";

export function FileChip({
  file,
  kind,
  onRemove,
  isNew,
}: {
  file: File;
  kind: "csv" | "pdf";
  onRemove?: () => void;
  isNew?: boolean;
}) {
  const Icon = kind === "csv" ? FileSpreadsheet : FileText;
  const tone =
    kind === "csv"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : "border-rose-200 bg-rose-50 text-rose-700";
  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-md border border-border bg-card px-3 py-2 transition-all duration-300",
        isNew && "animate-in fade-in slide-in-from-bottom-2 ring-2 ring-primary/30",
      )}
    >
      <span className={cn("flex h-9 w-9 items-center justify-center rounded-md border", tone)}>
        <Icon className="h-4 w-4" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-xs font-medium text-foreground">{file.name}</div>
        <div className="text-[10px] text-muted-foreground">
          {formatFileSize(file.size)} · 已选择
        </div>
      </div>
      {onRemove && (
        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={onRemove}>
          <X className="h-3.5 w-3.5" />
        </Button>
      )}
    </div>
  );
}

export function Dropzone({
  title,
  accept,
  files,
  kind,
  onFiles,
  onRemoveAt,
  historyHighlight,
  newFileNames,
}: {
  title: string;
  accept: string;
  files: File[];
  kind: "csv" | "pdf";
  onFiles: (files: File[]) => void;
  onRemoveAt?: (index: number) => void;
  historyHighlight?: boolean;
  newFileNames?: Set<string>;
}) {
  const inputId = useId();
  const [dragOver, setDragOver] = useState(false);
  const acceptExts = accept
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);

  const addFiles = (incoming: FileList | null) => {
    if (!incoming?.length) return;
    const picked = Array.from(incoming).filter((file) => {
      if (!acceptExts.length) return true;
      const name = file.name.toLowerCase();
      return acceptExts.some((ext) => name.endsWith(ext.startsWith(".") ? ext : `.${ext}`));
    });
    if (!picked.length) return;
    onFiles([...files, ...picked]);
  };

  const preventDrag = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDragEnter = (e: DragEvent) => {
    preventDrag(e);
    setDragOver(true);
  };

  const handleDragLeave = (e: DragEvent) => {
    preventDrag(e);
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
    setDragOver(false);
  };

  const handleDragOver = (e: DragEvent) => {
    preventDrag(e);
    e.dataTransfer.dropEffect = "copy";
    setDragOver(true);
  };

  const handleDrop = (e: DragEvent) => {
    preventDrag(e);
    setDragOver(false);
    addFiles(e.dataTransfer.files);
  };

  return (
    <div
      {...fileDropZoneProps}
      className="space-y-2"
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      <div
        className={cn(
          "relative rounded-lg border-2 border-dashed transition-all duration-500",
          dragOver
            ? "border-primary bg-primary/10"
            : historyHighlight
              ? "border-primary bg-primary/15 shadow-[0_0_0_4px_rgba(var(--primary),0.12)] scale-[1.01]"
              : "border-border bg-muted/30 hover:border-primary/40 hover:bg-primary/[0.03]",
        )}
      >
        <label
          htmlFor={inputId}
          className="flex cursor-pointer flex-col items-center justify-center gap-1 px-4 py-5 text-center"
        >
          <UploadCloud className={cn("h-6 w-6", dragOver ? "text-primary" : "text-muted-foreground")} />
          <div className="text-xs font-medium text-foreground">{title}</div>
          <div className="text-[11px] text-muted-foreground">点击或拖入本地文件，或从下方历史面板点选</div>
        </label>
      </div>
      <input
        id={inputId}
        type="file"
        accept={accept}
        multiple
        className="sr-only"
        onClick={(e) => e.stopPropagation()}
        onChange={(e) => {
          addFiles(e.target.files);
          e.target.value = "";
        }}
      />
      <div className="space-y-1.5">
        {(Array.isArray(files) ? files : []).map((f, i) => (
          <FileChip
            key={`${f.name}-${i}`}
            file={f}
            kind={kind}
            isNew={newFileNames?.has(f.name)}
            onRemove={() => onRemoveAt?.(i)}
          />
        ))}
      </div>
    </div>
  );
}

export function FeeCompareCell({
  label,
  min,
  max,
  highlight,
}: {
  label: string;
  min: number | null | undefined;
  max: number | null | undefined;
  highlight?: boolean;
}) {
  const text =
    min == null || max == null
      ? "—"
      : min === max
        ? `$${min.toFixed(2)}`
        : `$${min.toFixed(2)} – $${max.toFixed(2)}`;
  return (
    <div
      className={cn(
        "rounded-md border px-3 py-2",
        highlight ? "border-emerald-300 bg-emerald-50/50" : "border-border bg-muted/20",
      )}
    >
      <div className="text-[10px] text-muted-foreground">{label}</div>
      <div className={cn("mt-0.5 font-semibold tabular-nums", highlight && "text-emerald-900")}>
        {text}
      </div>
    </div>
  );
}
