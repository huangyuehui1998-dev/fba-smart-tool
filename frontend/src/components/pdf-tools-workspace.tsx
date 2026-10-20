import { useCallback, useEffect, useRef, useState } from "react";

import { ArrowLeft, Download, FileText, Loader2, Settings2, Wrench, X } from "lucide-react";

import { Link } from "@tanstack/react-router";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import { Button } from "@/components/ui/button";

import { Input } from "@/components/ui/input";

import { Label } from "@/components/ui/label";

import { Alert, AlertDescription } from "@/components/ui/alert";

import { Progress } from "@/components/ui/progress";

import {

  Select,

  SelectContent,

  SelectItem,

  SelectTrigger,

  SelectValue,

} from "@/components/ui/select";

import { Badge } from "@/components/ui/badge";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";

import { cn } from "@/lib/utils";

import { formatApiError } from "@/lib/format-api-error";

import {

  convertLabelPdfs,

  fetchPdfLabelSizes,

  type PdfLabelSize,

} from "@/lib/api/pdf-tools";

import {
  loadPdfLabelAdvancedOptions,
  MAX_CUSTOM_TEXT_LEN,
  savePdfLabelAdvancedOptions,
  type PdfLabelAdvancedOptions,
  type PdfLabelDetectDpi,
} from "@/lib/pdf-label-advanced-options";

import { usePreventBrowserFileDrop, fileDropZoneProps } from "@/hooks/use-prevent-browser-file-drop";



const CUSTOM_SIZE_KEY = "custom";



const DEFAULT_SIZES: PdfLabelSize[] = [

  { key: "carton_100x100", name: "外箱标 100×100mm", width_mm: 100, height_mm: 100 },

  { key: "product_60x40", name: "产品标 60×40mm", width_mm: 60, height_mm: 40 },

  { key: "product_100x150", name: "面单 100×150mm", width_mm: 100, height_mm: 150 },

  { key: "product_40x30", name: "小标 40×30mm", width_mm: 40, height_mm: 30 },

];



export function PdfToolsWorkspace() {

  const [files, setFiles] = useState<File[]>([]);

  const [sizes, setSizes] = useState<PdfLabelSize[]>(DEFAULT_SIZES);

  const [sizeKey, setSizeKey] = useState("carton_100x100");

  const [customWidth, setCustomWidth] = useState("100");

  const [customHeight, setCustomHeight] = useState("100");

  const [dragOver, setDragOver] = useState(false);

  const [converting, setConverting] = useState(false);

  const [progress, setProgress] = useState(0);

  const [progressMsg, setProgressMsg] = useState("");

  const [progressLog, setProgressLog] = useState<string[]>([]);

  const [error, setError] = useState<string | null>(null);

  const [advanced, setAdvanced] = useState<PdfLabelAdvancedOptions>(() =>
    loadPdfLabelAdvancedOptions(),
  );

  const inputRef = useRef<HTMLInputElement>(null);



  usePreventBrowserFileDrop();



  useEffect(() => {

    fetchPdfLabelSizes()

      .then((res) => {

        if (res.sizes?.length) setSizes(res.sizes);

      })

      .catch(() => undefined);

  }, []);



  useEffect(() => {

    savePdfLabelAdvancedOptions(advanced);

  }, [advanced]);



  const updateAdvanced = <K extends keyof PdfLabelAdvancedOptions>(

    key: K,

    value: PdfLabelAdvancedOptions[K],

  ) => {

    setAdvanced((prev) => ({ ...prev, [key]: value }));

  };



  const addFiles = useCallback((incoming: FileList | File[]) => {

    const pdfs = Array.from(incoming).filter(

      (f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"),

    );

    if (!pdfs.length) {

      setError("请上传 PDF 文件");

      return;

    }

    setError(null);

    setFiles((prev) => {

      const names = new Set(prev.map((f) => f.name));

      const merged = [...prev];

      for (const f of pdfs) {

        if (!names.has(f.name)) merged.push(f);

      }

      return merged;

    });

  }, []);



  const resolveSizeParams = () => {

    if (sizeKey === CUSTOM_SIZE_KEY) {

      const widthMm = Number.parseFloat(customWidth);

      const heightMm = Number.parseFloat(customHeight);

      if (!Number.isFinite(widthMm) || !Number.isFinite(heightMm) || widthMm <= 0 || heightMm <= 0) {

        throw new Error("请输入有效的自定义宽高（mm）");

      }

      return { sizeKey: "carton_100x100", widthMm, heightMm };

    }

    return { sizeKey };

  };



  const handleConvert = async () => {

    if (!files.length) {

      setError("请先上传至少一个 PDF");

      return;

    }

    setConverting(true);

    setError(null);

    setProgress(0);

    setProgressMsg("准备转换…");

    setProgressLog([]);

    try {

      const params = resolveSizeParams();

      await convertLabelPdfs(files, {

        ...params,

        advanced,

        onProgress: (pct, msg) => {

          setProgress(pct);

          setProgressMsg(msg);

          setProgressLog((prev) => {

            if (prev[prev.length - 1] === msg) return prev;

            const next = [...prev, msg];

            return next.length > 10 ? next.slice(-10) : next;

          });

        },

      });

    } catch (err) {

      setError(formatApiError(err));

      setProgress(0);

      setProgressMsg("");

      setProgressLog([]);

    } finally {

      setConverting(false);

    }

  };



  const preventDrag = (e: React.DragEvent) => {

    e.preventDefault();

    e.stopPropagation();

  };



  return (

    <div className="mx-auto max-w-3xl space-y-6">

      <div className="flex items-center gap-3">

        <Link

          to="/"

          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"

        >

          <ArrowLeft className="h-4 w-4" />

          返回主流程

        </Link>

      </div>



      <div className="flex items-center gap-3">

        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">

          <Wrench className="h-5 w-5" />

        </div>

        <div>

          <h1 className="text-2xl font-bold tracking-tight">PDF 标签处理</h1>

          <p className="text-sm text-muted-foreground">

            智能检测墨迹边界，将 A4 / Letter 箱唛或产品贴裁剪为热敏打印尺寸；批量处理时保持原文件名一一对应下载。

          </p>

        </div>

      </div>



      {error && (

        <Alert variant="destructive">

          <AlertDescription>{error}</AlertDescription>

        </Alert>

      )}



      <Card>

        <CardHeader>

          <CardTitle className="text-base">上传 PDF（支持批量）</CardTitle>

        </CardHeader>

        <CardContent className="space-y-4">

          <div

            {...fileDropZoneProps}

            className={cn(

              "flex min-h-[160px] cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-6 transition-colors",

              dragOver

                ? "border-primary bg-primary/5"

                : "border-border bg-muted/30 hover:border-primary/40",

            )}

            onDragEnter={(e) => {

              preventDrag(e);

              setDragOver(true);

            }}

            onDragLeave={(e) => {

              preventDrag(e);

              if (e.currentTarget.contains(e.relatedTarget as Node)) return;

              setDragOver(false);

            }}

            onDragOver={(e) => {

              preventDrag(e);

              e.dataTransfer.dropEffect = "copy";

              setDragOver(true);

            }}

            onDrop={(e) => {

              preventDrag(e);

              setDragOver(false);

              if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files);

            }}

            onClick={() => inputRef.current?.click()}

          >

            <FileText className="mb-2 h-8 w-8 text-muted-foreground" />

            <p className="text-sm font-medium">拖拽 PDF 到此处，或点击选择文件</p>

            <p className="mt-1 text-xs text-muted-foreground">支持多文件；自动识别单页多标签并切分</p>

            <input

              ref={inputRef}

              type="file"

              accept=".pdf,application/pdf"

              multiple

              className="hidden"

              onChange={(e) => {

                if (e.target.files?.length) addFiles(e.target.files);

                e.target.value = "";

              }}

            />

          </div>



          {files.length > 0 && (

            <div className="flex flex-wrap gap-2">

              {files.map((f) => (

                <Badge key={f.name} variant="secondary" className="gap-1 text-xs">

                  {f.name}

                  <button

                    type="button"

                    className="ml-1 text-muted-foreground hover:text-foreground"

                    onClick={() => setFiles((prev) => prev.filter((x) => x.name !== f.name))}

                    aria-label={`移除 ${f.name}`}

                  >

                    ×

                  </button>

                </Badge>

              ))}

            </div>

          )}

        </CardContent>

      </Card>



      <Card>

        <CardHeader>

          <CardTitle className="text-base">目标尺寸</CardTitle>

        </CardHeader>

        <CardContent className="space-y-4">

          <Select value={sizeKey} onValueChange={setSizeKey}>

            <SelectTrigger>

              <SelectValue placeholder="选择目标尺寸" />

            </SelectTrigger>

            <SelectContent>

              {sizes.map((s) => (

                <SelectItem key={s.key} value={s.key}>

                  {s.name}

                </SelectItem>

              ))}

              <SelectItem value={CUSTOM_SIZE_KEY}>自定义尺寸 (mm)</SelectItem>

            </SelectContent>

          </Select>



          {sizeKey === CUSTOM_SIZE_KEY && (

            <div className="grid grid-cols-2 gap-3">

              <div className="space-y-1.5">

                <Label htmlFor="pdf-width-mm">宽度 (mm)</Label>

                <Input

                  id="pdf-width-mm"

                  type="number"

                  min={1}

                  step={0.1}

                  value={customWidth}

                  onChange={(e) => setCustomWidth(e.target.value)}

                />

              </div>

              <div className="space-y-1.5">

                <Label htmlFor="pdf-height-mm">高度 (mm)</Label>

                <Input

                  id="pdf-height-mm"

                  type="number"

                  min={1}

                  step={0.1}

                  value={customHeight}

                  onChange={(e) => setCustomHeight(e.target.value)}

                />

              </div>

            </div>

          )}



          <Accordion type="single" collapsible className="rounded-lg border px-4">

            <AccordionItem value="advanced" className="border-0">

              <AccordionTrigger className="py-3 text-sm hover:no-underline">

                <span className="flex items-center gap-2 text-muted-foreground">

                  <Settings2 className="h-4 w-4" />

                  展开进阶打印设置

                </span>

              </AccordionTrigger>

              <AccordionContent className="space-y-4">

                <div className="space-y-1.5">

                  <Label htmlFor="pdf-padding-mm">边缘留白补偿 (mm)</Label>

                  <Input

                    id="pdf-padding-mm"

                    type="number"

                    min={0}

                    step={0.1}

                    value={advanced.paddingMm}

                    onChange={(e) =>

                      updateAdvanced("paddingMm", Number.parseFloat(e.target.value) || 0)

                    }

                  />

                  <p className="text-[11px] text-muted-foreground">

                    若热敏打印时边缘文字被切掉，请适当调大此值

                  </p>

                </div>



                <div className="space-y-1.5">

                  <Label htmlFor="pdf-ignore-top-mm">忽略顶部杂讯 (mm)</Label>

                  <Input

                    id="pdf-ignore-top-mm"

                    type="number"

                    min={0}

                    step={0.5}

                    value={advanced.ignoreTopMm}

                    onChange={(e) =>

                      updateAdvanced("ignoreTopMm", Number.parseFloat(e.target.value) || 0)

                    }

                  />

                  <p className="text-[11px] text-muted-foreground">

                    应对亚马逊标签顶部的 Fulfillment 等干扰文字

                  </p>

                </div>



                <div className="space-y-1.5">

                  <Label htmlFor="pdf-ignore-bottom-mm">忽略底部杂讯 (mm)</Label>

                  <Input

                    id="pdf-ignore-bottom-mm"

                    type="number"

                    min={0}

                    step={0.5}

                    value={advanced.ignoreBottomMm}

                    onChange={(e) =>

                      updateAdvanced("ignoreBottomMm", Number.parseFloat(e.target.value) || 0)

                    }

                  />

                </div>



                <div className="space-y-1.5">

                  <Label htmlFor="pdf-detect-dpi">墨迹检测精度</Label>

                  <Select

                    value={String(advanced.detectDpi)}

                    onValueChange={(v) => updateAdvanced("detectDpi", Number(v) as PdfLabelDetectDpi)}

                  >

                    <SelectTrigger id="pdf-detect-dpi">

                      <SelectValue />

                    </SelectTrigger>

                    <SelectContent>

                      <SelectItem value="120">120 DPI（默认极速）</SelectItem>

                      <SelectItem value="200">200 DPI（均衡）</SelectItem>

                      <SelectItem value="300">300 DPI（高清较慢）</SelectItem>

                    </SelectContent>

                  </Select>

                  <p className="text-[11px] text-muted-foreground">

                    仅当标签极度模糊、底纹干扰导致检测失败时，再调高此项。调高会增加处理耗时

                  </p>

                </div>



                <div className="space-y-1.5">

                  <Label htmlFor="pdf-custom-text">底部附加文本（选填）</Label>

                  <div className="relative">

                    <Input

                      id="pdf-custom-text"

                      type="text"

                      maxLength={MAX_CUSTOM_TEXT_LEN}

                      placeholder="例如：MADE IN CHINA"

                      value={advanced.customText}

                      onChange={(e) =>

                        updateAdvanced("customText", e.target.value.slice(0, MAX_CUSTOM_TEXT_LEN))

                      }

                      className={advanced.customText ? "pr-9" : undefined}

                    />

                    {advanced.customText ? (

                      <button

                        type="button"

                        className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted-foreground hover:text-foreground"

                        aria-label="清除底部附加文本"

                        onClick={() => updateAdvanced("customText", "")}

                      >

                        <X className="h-4 w-4" />

                      </button>

                    ) : null}

                  </div>

                  <p className="text-[11px] text-muted-foreground">

                    自动在生成的标签底部正中央添加一行文本（常用于产地标或内部 SKU）。目前仅支持英文与数字

                  </p>

                </div>

              </AccordionContent>

            </AccordionItem>

          </Accordion>



          <Button

            size="lg"

            className="w-full gap-2 sm:w-auto"

            disabled={converting || !files.length}

            onClick={() => void handleConvert()}

          >

            {converting ? (

              <Loader2 className="h-4 w-4 animate-spin" />

            ) : (

              <Download className="h-4 w-4" />

            )}

            一键智能转换

          </Button>



          {(converting || progress > 0) && (

            <div className="space-y-2 rounded-lg border bg-muted/20 p-4">

              <div className="flex items-center justify-between text-sm">

                <span className="text-muted-foreground">{progressMsg || "处理中…"}</span>

                <span className="font-medium tabular-nums">{progress}%</span>

              </div>

              <Progress value={progress} className="h-2" />

              {converting && progressLog.length > 0 && (

                <div className="max-h-24 space-y-0.5 overflow-y-auto text-[11px] leading-relaxed text-muted-foreground">

                  {progressLog.map((line, i) => (

                    <p

                      key={`${i}-${line}`}

                      className={cn(i === progressLog.length - 1 && "font-medium text-foreground")}

                    >

                      {line}

                    </p>

                  ))}

                </div>

              )}

            </div>

          )}

        </CardContent>

      </Card>

    </div>

  );

}


