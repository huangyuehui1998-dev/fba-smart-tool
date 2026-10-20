import { useEffect, useState } from "react";
import { Loader2, ScanSearch } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  detectInvoiceTemplate,
  fetchInvoiceTemplates,
  parseInvoiceTemplate,
  type DetectResult,
  type InvoiceTemplateInfo,
  type ParseResult,
} from "@/lib/api/invoice-templates";

/** S8 D3：识别货代发票（T1–T8）——上传 → 自动识别（打平/认不出时手选模板）→ 解析出票据；可附货件 CSV 核对并确认修正 */
export function InvoiceTemplateRecognizePanel() {
  const [templates, setTemplates] = useState<InvoiceTemplateInfo[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [csvFiles, setCsvFiles] = useState<File[]>([]);
  const [detect, setDetect] = useState<DetectResult | null>(null);
  const [tpl, setTpl] = useState("");
  const [result, setResult] = useState<ParseResult | null>(null);
  const [accept, setAccept] = useState<string[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchInvoiceTemplates()
      .then(setTemplates)
      .catch((e: unknown) => setErr(e instanceof Error ? e.message : String(e)));
  }, []);

  const onFile = async (f: File | null) => {
    setFile(f);
    setDetect(null);
    setResult(null);
    setAccept([]);
    setErr("");
    if (!f) return;
    setBusy(true);
    try {
      const d = await detectInvoiceTemplate(f);
      setDetect(d);
      setTpl(d.template_id ?? "");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const parse = async (acc: string[] = accept) => {
    if (!file) return;
    setBusy(true);
    setErr("");
    try {
      setResult(await parseInvoiceTemplate(file, tpl, csvFiles, acc));
    } catch (e) {
      setResult(null);
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">识别货代发票（T1–T8：九方 / SEND / 德速 / 琪珞）</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-xs">
        <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
          <label className="space-y-1">
            <div>货代发票 Excel（必填）</div>
            <Input type="file" accept=".xlsx,.xls" className="h-8" onChange={(e) => void onFile(e.target.files?.[0] ?? null)} />
          </label>
          <label className="space-y-1">
            <div>模板（默认自动识别；认不出或打平时手选）</div>
            <select className="h-8 w-full rounded border bg-background px-2" value={tpl} onChange={(e) => setTpl(e.target.value)}>
              <option value="">自动识别</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.id} {t.name}
                  {t.forwarder ? `（${t.forwarder}）` : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1">
            <div>货件 CSV（可选，多选；用来核对箱数/重量/仓库）</div>
            <Input
              type="file"
              accept=".csv"
              multiple
              className="h-8"
              onChange={(e) => setCsvFiles(Array.from(e.target.files ?? []))}
            />
          </label>
        </div>
        {detect && (
          <div className={detect.template_id ? "text-muted-foreground" : "text-amber-700"}>
            识别结果：{detect.template_id ?? "未定"}
            {detect.message ? ` — ${detect.message}` : ""}
            {detect.candidates.length > 0 &&
              `（候选：${detect.candidates.map((c) => `${c.template_id} ${Math.round(c.score * 100)}%`).join("、")}）`}
          </div>
        )}
        <Button size="sm" variant="outline" disabled={!file || busy} onClick={() => void parse()}>
          {busy ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : <ScanSearch className="mr-1 h-3 w-3" />}
          解析
        </Button>
        {err && <div className="text-red-600">{err}</div>}
        {result && (
          <div className="space-y-3">
            <div>
              模板 {result.template_id} {result.template_name}（{result.forwarder}），共 {result.tickets.length} 票
            </div>
            {result.issues.length > 0 && (
              <ul className="list-disc pl-5 text-amber-700">
                {result.issues.map((i, k) => (
                  <li key={k}>{i.message}</li>
                ))}
              </ul>
            )}
            {result.tickets.map((t, ti) => (
              <div key={ti} className="space-y-1 rounded border p-2">
                <div className="font-medium">
                  {t.shipment_id} · 仓库 {t.warehouse || "—"} · {t.box_count ?? "?"} 箱 · {t.verify_status}
                </div>
                {t.issues.length > 0 && (
                  <ul className="list-disc pl-5 text-amber-700">
                    {t.issues.map((i, k) => (
                      <li key={k}>{i.message}</li>
                    ))}
                  </ul>
                )}
                {t.proposals.length > 0 && (
                  <div className="space-y-1 rounded bg-amber-50 p-2">
                    <div>建议修正（勾选后点“确认修正并重新解析”才生效）：</div>
                    {t.proposals.map((p) => (
                      <label key={p.id} className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={accept.includes(p.id)}
                          onChange={(e) =>
                            setAccept((old) => (e.target.checked ? [...old, p.id] : old.filter((x) => x !== p.id)))
                          }
                        />
                        {p.message}
                      </label>
                    ))}
                  </div>
                )}
                <table className="w-full border-collapse">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th>箱号</th>
                      <th>品名</th>
                      <th>HS</th>
                      <th>数量</th>
                      <th>单价</th>
                    </tr>
                  </thead>
                  <tbody>
                    {t.lines.map((l, li) => (
                      <tr key={li} className="border-b">
                        <td>{l.box_range}</td>
                        <td>
                          {l.chinese_name} / {l.english_name}
                        </td>
                        <td>{l.hs_code}</td>
                        <td>{l.qty ?? ""}</td>
                        <td>{l.unit_price ?? ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
            {result.tickets.some((t) => t.proposals.length > 0) && (
              <Button size="sm" variant="outline" disabled={busy || !csvFiles.length || !accept.length} onClick={() => void parse(accept)}>
                确认修正并重新解析
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
