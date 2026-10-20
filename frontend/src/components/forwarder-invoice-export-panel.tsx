import { useEffect, useState } from "react";
import { Download, Eye, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  downloadForwarderInvoice,
  ExportBlockedError,
  WarehouseUndecidedError,
  fetchExportForwarders,
  previewForwarderInvoice,
  type ExportForwarder,
  type ExportIssue,
  type ExportPreview,
} from "@/lib/api/invoice-export";

/** S7：按货代模板（SEND / 九方）导出发票——上传亚马逊货件 CSV → 预览 → 下载 xlsx */
export function ForwarderInvoiceExportPanel() {
  const [forwarders, setForwarders] = useState<ExportForwarder[]>([]);
  const [fw, setFw] = useState("");
  const [csv, setCsv] = useState<File | null>(null);
  const [measured, setMeasured] = useState<File | null>(null);
  const [weightBasis, setWeightBasis] = useState<"" | "per_box" | "per_unit">("");
  const [weightRef, setWeightRef] = useState<File | null>(null);
  const [ref, setRef] = useState("");
  const [orderNo, setOrderNo] = useState("");
  const [preview, setPreview] = useState<ExportPreview | null>(null);
  const [blocking, setBlocking] = useState<ExportIssue[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  // 同城多仓兜底：CSV 定不下仓库时后端给候选，这里选；也可手填
  const [warehouse, setWarehouse] = useState("");
  const [whCandidates, setWhCandidates] = useState<string[]>([]);
  // 外箱号更正：{ 单箱数据里多出的箱号: 对应货件的箱序号 }
  const [boxFix, setBoxFix] = useState<Record<string, number>>({});

  const mismatch = blocking.find((b) => b.code === "measured_box_mismatch");
  const extraIds = (mismatch?.extra as string[] | undefined) ?? [];
  const missingIds = (mismatch?.missing as string[] | undefined) ?? [];
  const boxNo = (id: string) => {
    const m = /U(\d+)$/i.exec(id);
    return m ? parseInt(m[1], 10) : parseInt(id, 10);
  };

  useEffect(() => {
    fetchExportForwarders()
      .then((list) => {
        setForwarders(list);
        if (list.length) setFw(list[0].id);
      })
      .catch((e: unknown) => setErr(e instanceof Error ? e.message : String(e)));
  }, []);

  const form = (fix: Record<string, number> = boxFix) => ({
    forwarder_id: fw,
    csv: csv as File,
    reference_id: ref.trim(),
    order_no: orderNo.trim(),
    warehouse: warehouse.trim().toUpperCase(),
    measured,
    box_id_fix: fix,
    weight_basis: weightBasis,
    weight_ref: weightRef,
  });

  const run = async (download: boolean) => {
    if (!csv || !fw) return;
    setBusy(true);
    setErr("");
    setBlocking([]);
    try {
      if (download) {
        const { blob, fileName } = await downloadForwarderInvoice(form());
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = fileName;
        a.click();
        URL.revokeObjectURL(url);
      } else {
        setPreview(await previewForwarderInvoice(form()));
      }
    } catch (e) {
      if (e instanceof WarehouseUndecidedError) {
        setPreview(null);
        setWhCandidates(e.candidates);
        setErr(e.message);
      } else if (e instanceof ExportBlockedError) {
        setPreview(null);
        setBlocking(e.blocking);
        setErr(e.message);
      } else setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">按货代模板导出发票（SEND / 九方）</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-xs">
        <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
          <label className="space-y-1">
            <div>货代</div>
            <select className="h-8 w-full rounded border bg-background px-2" value={fw} onChange={(e) => setFw(e.target.value)}>
              {forwarders.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name || f.id}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1">
            <div>亚马逊货件 CSV（必填）</div>
            <Input type="file" accept=".csv" className="h-8" onChange={(e) => setCsv(e.target.files?.[0] ?? null)} />
          </label>
          <label className="space-y-1">
            <div>九方单箱数据（可选，实测重量/尺寸）</div>
            <Input
              type="file"
              accept=".xlsx,.xls"
              className="h-8"
              onChange={(e) => {
                setMeasured(e.target.files?.[0] ?? null);
                setBoxFix({});
              }}
            />
          </label>
          <label className="space-y-1">
            <div>重量口径（德速 / 琪珞 T6：有的票填单箱重，有的填单件重）</div>
            <select
              className="h-8 w-full rounded border bg-background px-2"
              value={weightBasis}
              onChange={(e) => setWeightBasis(e.target.value as "" | "per_box" | "per_unit")}
            >
              <option value="">自动：按下面上传的货代原件和 CSV 核对（没上传则重量留空并提示）</option>
              <option value="per_box">单箱重</option>
              <option value="per_unit">单件重（单箱重 ÷ 每箱件数）</option>
            </select>
          </label>
          <label className="space-y-1">
            <div>货代给的这票发票（可选，用来判定重量口径）</div>
            <Input type="file" accept=".xlsx,.xls" className="h-8" onChange={(e) => setWeightRef(e.target.files?.[0] ?? null)} />
          </label>
          <label className="space-y-1">
            <div>Reference ID（亚马逊追踪号）</div>
            <Input className="h-8" value={ref} onChange={(e) => setRef(e.target.value)} />
          </label>
          <label className="space-y-1">
            <div>九方订单号</div>
            <Input className="h-8" value={orderNo} onChange={(e) => setOrderNo(e.target.value)} />
          </label>
          <label className="space-y-1">
            <div>仓库代码（默认按 CSV 自动识别；同城多仓识别不了时在这里选）</div>
            <Input
              className="h-8"
              list="fw-invoice-wh-candidates"
              placeholder="自动"
              value={warehouse}
              onChange={(e) => setWarehouse(e.target.value)}
            />
            <datalist id="fw-invoice-wh-candidates">
              {whCandidates.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
            {whCandidates.length > 0 && (
              <select
                className="h-8 w-full rounded border bg-background px-2"
                value={warehouse}
                onChange={(e) => setWarehouse(e.target.value)}
              >
                <option value="">请选择仓库…</option>
                {whCandidates.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            )}
          </label>
          <div className="flex items-end gap-2">
            <Button size="sm" variant="outline" disabled={!csv || busy} onClick={() => void run(false)}>
              {busy ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : <Eye className="mr-1 h-3 w-3" />}预览
            </Button>
            <Button size="sm" disabled={!csv || busy} onClick={() => void run(true)}>
              <Download className="mr-1 h-3 w-3" />
              导出 xlsx
            </Button>
          </div>
        </div>
        {err && <div className="text-red-600">{err}</div>}
        {blocking.length > 0 && (
          <ul className="list-disc space-y-0.5 pl-5 text-red-600">
            {blocking.map((b, i) => (
              <li key={i}>{b.message}</li>
            ))}
          </ul>
        )}
        {extraIds.length > 0 && (
          <div className="space-y-2 rounded border border-amber-300 bg-amber-50 p-2">
            <div className="font-medium">确认外箱号更正：单箱数据里多出的箱号对应货件的哪一箱？</div>
            {extraIds.map((x) => (
              <div key={x} className="flex items-center gap-2">
                <span className="font-mono">{x}</span>
                <span>→</span>
                <select
                  className="h-7 rounded border bg-background px-2"
                  value={boxFix[x] ?? ""}
                  onChange={(e) => {
                    const v = e.target.value;
                    setBoxFix((old) => {
                      const next = { ...old };
                      if (v) next[x] = parseInt(v, 10);
                      else delete next[x];
                      return next;
                    });
                  }}
                >
                  <option value="">不更正</option>
                  {missingIds.map((m) => (
                    <option key={m} value={boxNo(m)}>
                      {m}（第 {boxNo(m)} 箱）
                    </option>
                  ))}
                </select>
              </div>
            ))}
            <Button size="sm" variant="outline" disabled={busy || !Object.keys(boxFix).length} onClick={() => void run(false)}>
              确认更正并重新预览
            </Button>
          </div>
        )}
        {preview && Object.keys(boxFix).length > 0 && (
          <div className="text-amber-700">
            已按确认更正外箱号：
            {Object.entries(boxFix)
              .map(([k, v]) => `${k} → 第 ${v} 箱`)
              .join("；")}
          </div>
        )}
        {preview && (
          <div className="space-y-2">
            <div>
              货件 {preview.shipment_id}，仓库 {preview.warehouse || "—"}
              {preview.warehouse_source ? `（${preview.warehouse_source}）` : ""}，{preview.box_count} 箱，{preview.total_qty} 件，总价{" "}
              {preview.total_value} USD；文件名 {preview.file_name}
            </div>
            {preview.warnings.length > 0 && (
              <ul className="list-disc space-y-0.5 pl-5 text-amber-700">
                {preview.warnings.map((w, i) => (
                  <li key={i}>{w.message}</li>
                ))}
              </ul>
            )}
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th>箱号</th>
                  <th>FNSKU</th>
                  <th>每箱件数</th>
                  <th>单箱重(kg)</th>
                </tr>
              </thead>
              <tbody>
                {preview.ranges.map((r, i) => (
                  <tr key={i} className="border-b">
                    <td>{r.box}</td>
                    <td>{r.mixed ? `${r.fnsku}（混装）` : r.fnsku}</td>
                    <td>{r.qty}</td>
                    <td>{r.weight}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
