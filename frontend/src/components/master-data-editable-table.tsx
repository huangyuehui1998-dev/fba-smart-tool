import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
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
import { TableScrollArea } from "@/components/table-scroll-area";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { formatApiError } from "@/lib/format-api-error";
import {
  deleteMasterSku,
  patchMasterSkuField,
  type MasterPatchableField,
  type MasterProduct,
} from "@/lib/api/master-data";

type EditableColumn = {
  field: MasterPatchableField;
  label: string;
  kind: "text" | "number";
  decimals?: number;
};

const EDITABLE_COLUMNS: EditableColumn[] = [
  { field: "asin", label: "ASIN", kind: "text" },
  { field: "fnsku", label: "FNSKU", kind: "text" },
  { field: "english_name", label: "英文品名", kind: "text" },
  { field: "model_name", label: "中文名称(型号)", kind: "text" },
  { field: "chinese_name", label: "商品报关名称", kind: "text" },
  { field: "hs_code", label: "海关编码", kind: "text" },
  { field: "category", label: "品类", kind: "text" },
  { field: "declare_unit", label: "申报单位", kind: "text" },
  { field: "invoice_unit", label: "发票单位", kind: "text" },
  { field: "pcs_per_set", label: "每套件数", kind: "number", decimals: 0 },
  { field: "purchase_price", label: "采购单价(CNY)", kind: "number", decimals: 2 },
  { field: "material_en", label: "英文材质", kind: "text" },
  { field: "purpose_en", label: "英文用途", kind: "text" },
  { field: "dest_hs_code", label: "目的国HS", kind: "text" },
  { field: "fob_unit_value", label: "FOB单价(USD)", kind: "number", decimals: 2 },
  { field: "local_name", label: "本地品名", kind: "text" },
  { field: "brand", label: "品牌", kind: "text" },
  { field: "material", label: "材质", kind: "text" },
  { field: "purpose", label: "用途", kind: "text" },
  { field: "declared_value", label: "申报单价", kind: "number", decimals: 2 },
  { field: "unit_length", label: "单品长", kind: "number", decimals: 1 },
  { field: "unit_width", label: "单品宽", kind: "number", decimals: 1 },
  { field: "unit_height", label: "单品高", kind: "number", decimals: 1 },
  { field: "unit_weight", label: "单品重", kind: "number", decimals: 2 },
  { field: "carton_length", label: "外箱长", kind: "number", decimals: 1 },
  { field: "carton_width", label: "外箱宽", kind: "number", decimals: 1 },
  { field: "carton_height", label: "外箱高", kind: "number", decimals: 1 },
  { field: "carton_weight", label: "外箱重", kind: "number", decimals: 2 },
  { field: "carton_gross_weight", label: "单箱毛重", kind: "number", decimals: 2 },
  { field: "listing_status", label: "Listing", kind: "text" },
];

const STICKY_SKU =
  "sticky left-0 z-20 min-w-[9rem] bg-card shadow-[4px_0_6px_-2px_rgba(0,0,0,0.06)]";
const STICKY_ACTIONS =
  "sticky right-0 z-20 min-w-[4.5rem] bg-card shadow-[-4px_0_6px_-2px_rgba(0,0,0,0.06)]";

function displayValue(value: unknown, decimals?: number): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") {
    if (Number.isNaN(value)) return "—";
    return decimals !== undefined ? value.toFixed(decimals) : String(value);
  }
  const text = String(value).trim();
  return text || "—";
}

function parseDraftValue(kind: "text" | "number", draft: string): string | number | null {
  const text = draft.trim();
  if (!text || text === "—") return kind === "number" ? null : "";
  if (kind === "number") {
    const n = Number(text);
    return Number.isFinite(n) ? n : null;
  }
  return text;
}

function valuesEqual(
  kind: "text" | "number",
  a: unknown,
  b: string | number | null,
): boolean {
  if (kind === "number") {
    const left = a === null || a === undefined || a === "" ? null : Number(a);
    const right = b === null ? null : Number(b);
    if (left === null && right === null) return true;
    if (left === null || right === null) return false;
    return Math.abs(left - right) < 1e-9;
  }
  const left = String(a ?? "").trim();
  const right = String(b ?? "").trim();
  return left === right;
}

function EditableCell({
  sku,
  field,
  kind,
  decimals,
  value,
  onSaved,
}: {
  sku: string;
  field: MasterPatchableField;
  kind: "text" | "number";
  decimals?: number;
  value: unknown;
  onSaved: (row: MasterProduct) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const beginEdit = () => {
    if (saving) return;
    const initial =
      value === null || value === undefined || value === ""
        ? ""
        : kind === "number" && typeof value === "number"
          ? value.toFixed(decimals ?? 2)
          : String(value);
    setDraft(initial);
    setEditing(true);
  };

  useEffect(() => {
    if (!editing) return;
    const el = inputRef.current;
    if (!el) return;
    el.focus();
    el.select();
  }, [editing]);

  const commit = async () => {
    if (!editing) return;
    setEditing(false);
    const next = parseDraftValue(kind, draft);
    if (valuesEqual(kind, value, next)) return;
    if (field === "hs_code" && typeof next === "string" && next.trim()) {
      // S8 D6：HS 编码前端先校验（8 或 10 位数字，点/空格/横线会被去掉），后端还会再校验一次
      const digits = next.replace(/[.\s-]/g, "");
      if (!/^\d{8}$|^\d{10}$/.test(digits)) {
        toast.error(`HS 编码格式不对：${next}（应为 8 或 10 位数字，如 9507100090）`);
        return;
      }
    }

    setSaving(true);
    try {
      const updated = await patchMasterSkuField(sku, field, next);
      onSaved(updated);
      toast.success("更新成功");
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setSaving(false);
    }
  };

  if (editing) {
    return (
      <Input
        ref={inputRef}
        value={draft}
        className="h-7 min-w-[5rem] px-1.5 font-mono text-xs"
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => void commit()}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            void commit();
          }
          if (e.key === "Escape") {
            setEditing(false);
          }
        }}
      />
    );
  }

  return (
    <button
      type="button"
      className={cn(
        "w-full cursor-text rounded px-1 py-0.5 text-left font-mono text-xs",
        "transition-colors hover:bg-muted/80 hover:ring-1 hover:ring-border/80",
        saving && "opacity-60",
      )}
      title="双击编辑"
      onDoubleClick={beginEdit}
      disabled={saving}
    >
      {saving ? <Loader2 className="inline h-3 w-3 animate-spin" /> : displayValue(value, decimals)}
    </button>
  );
}

export function MasterDataEditableTable({
  items,
  loading,
  onRowUpdated,
  onRowDeleted,
  className,
  tableMaxHeight,
}: {
  items: MasterProduct[];
  loading: boolean;
  onRowUpdated: (row: MasterProduct) => void;
  onRowDeleted: (sku: string) => void;
  className?: string;
  tableMaxHeight?: string;
}) {
  const [sorting, setSorting] = useState<SortingState>([{ id: "sku", desc: false }]);
  const [globalFilter, setGlobalFilter] = useState("");
  const [deleteSku, setDeleteSku] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const handleSaved = useCallback(
    (row: MasterProduct) => {
      onRowUpdated(row);
    },
    [onRowUpdated],
  );

  const confirmDelete = async () => {
    if (!deleteSku) return;
    setDeleting(true);
    try {
      await deleteMasterSku(deleteSku);
      onRowDeleted(deleteSku);
      toast.success(`已删除 SKU：${deleteSku}`);
      setDeleteSku(null);
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setDeleting(false);
    }
  };

  const columns = useMemo<ColumnDef<MasterProduct>[]>(() => {
    const cols: ColumnDef<MasterProduct>[] = [
      {
        id: "sku",
        accessorKey: "sku",
        header: "SKU",
        cell: ({ row }) => (
          <span className="font-mono text-xs font-medium">{row.original.sku}</span>
        ),
        meta: { sticky: "left" as const },
      },
    ];

    for (const col of EDITABLE_COLUMNS) {
      cols.push({
        id: col.field,
        accessorKey: col.field,
        header: col.label,
        cell: ({ row }) => (
          <EditableCell
            sku={row.original.sku}
            field={col.field}
            kind={col.kind}
            decimals={col.decimals}
            value={row.original[col.field]}
            onSaved={handleSaved}
          />
        ),
      });
    }

    cols.push({
      id: "lingxing_synced_at",
      accessorKey: "lingxing_synced_at",
      header: "领星同步",
      cell: ({ row }) => (
        <span className="text-xs text-muted-foreground">
          {row.original.lingxing_synced_at
            ? new Date(row.original.lingxing_synced_at).toLocaleString()
            : "—"}
        </span>
      ),
    });

    cols.push({
      id: "updated_at",
      accessorKey: "updated_at",
      header: "更新时间",
      cell: ({ row }) => (
        <span className="text-xs text-muted-foreground">
          {row.original.updated_at ? new Date(row.original.updated_at).toLocaleString() : "—"}
        </span>
      ),
    });

    cols.push({
      id: "actions",
      header: "操作",
      enableSorting: false,
      cell: ({ row }) => (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-destructive hover:bg-destructive/10 hover:text-destructive"
          title="删除 SKU"
          onClick={() => setDeleteSku(row.original.sku)}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      ),
      meta: { sticky: "right" as const },
    });

    return cols;
  }, [handleSaved]);

  const table = useReactTable({
    data: items,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    globalFilterFn: (row, _columnId, filter) => {
      const q = String(filter ?? "").trim().toLowerCase();
      if (!q) return true;
      const p = row.original;
      return (
        p.sku.toLowerCase().includes(q) ||
        (p.model_name ?? "").toLowerCase().includes(q) ||
        (p.chinese_name ?? "").toLowerCase().includes(q) ||
        (p.english_name ?? "").toLowerCase().includes(q) ||
        (p.hs_code ?? "").toLowerCase().includes(q) ||
        (p.asin ?? "").toLowerCase().includes(q) ||
        (p.fnsku ?? "").toLowerCase().includes(q)
      );
    },
  });

  const stickyClass = (id: string) => {
    if (id === "sku") return STICKY_SKU;
    if (id === "actions") return STICKY_ACTIONS;
    return undefined;
  };

  return (
    <div className={cn("flex min-h-0 flex-1 flex-col gap-3", className)}>
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 px-4 pt-3">
        <p className="text-xs text-muted-foreground">双击可编辑单元格，失焦自动保存</p>
        <Input
          value={globalFilter}
          onChange={(e) => setGlobalFilter(e.target.value)}
          placeholder="搜索 SKU / 品名 / 海关编码…"
          className="h-8 max-w-xs text-xs"
        />
      </div>

      <TableScrollArea
        variant="plain"
        className="min-h-0 flex-1 px-1"
        maxHeight={tableMaxHeight ?? "100%"}
        style={tableMaxHeight ? undefined : { height: "100%" }}
      >
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id} className="bg-muted/50">
                {hg.headers.map((header) => (
                  <TableHead
                    key={header.id}
                    className={cn(
                      "whitespace-nowrap text-xs",
                      header.column.getCanSort() && "cursor-pointer",
                      stickyClass(header.column.id),
                    )}
                    onClick={header.column.getToggleSortingHandler()}
                  >
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    {{
                      asc: " ↑",
                      desc: " ↓",
                    }[header.column.getIsSorted() as string] ?? null}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="py-8 text-center text-sm text-muted-foreground">
                  <Loader2 className="mx-auto mb-2 h-5 w-5 animate-spin" />
                  加载中…
                </TableCell>
              </TableRow>
            ) : table.getRowModel().rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="py-8 text-center text-sm text-muted-foreground">
                  暂无主数据，请上传亚马逊报告或产品信息总表
                </TableCell>
              </TableRow>
            ) : (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell
                      key={cell.id}
                      className={cn("p-1 align-middle", stickyClass(cell.column.id))}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableScrollArea>

      <AlertDialog open={deleteSku !== null} onOpenChange={(open) => !open && !deleting && setDeleteSku(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确定删除该 SKU？</AlertDialogTitle>
            <AlertDialogDescription>
              将永久从主数据库删除 <span className="font-mono font-medium">{deleteSku}</span>
              ，此操作不可撤销。发票/装箱若引用该 SKU 将显示缺主数据。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={deleting}
              onClick={(e) => {
                e.preventDefault();
                void confirmDelete();
              }}
            >
              {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : "删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
