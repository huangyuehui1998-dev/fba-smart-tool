import { Check, Download, Upload, RefreshCw, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { Link } from "@tanstack/react-router";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { DEEPSEEK_KEY_STORAGE } from "@/lib/step1-rows";
import {
  DEEPSEEK_MODEL_OPTIONS,
  DEEPSEEK_MODEL_STORAGE,
  DEEPSEEK_TEMPERATURE_STORAGE,
  DEFAULT_DEEPSEEK_MODEL,
  DEFAULT_DEEPSEEK_TEMPERATURE,
  type DeepseekModel,
} from "@/lib/deepseek-settings";
import {
  downloadTemplateFile,
  fetchTemplatePreview,
  fetchTemplatesList,
  uploadTemplateFile,
} from "@/lib/api/templates";
import { ParamsSection } from "@/components/params-section";
import { TableScrollArea } from "@/components/table-scroll-area";
import { formatApiError } from "@/lib/format-api-error";
import { autoTaskName } from "@/lib/workflow-storage";
import { useWorkflow } from "@/context/workflow-context";
import { rememberReturnStep } from "@/lib/return-step";
import {
  deleteTaskHistory,
  fetchTaskHistoryList,
  loadTaskHistory,
  renameTaskHistory,
  type TaskHistoryIndexRow,
} from "@/lib/api/task-history";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  fetchLingxingSettings,
  saveLingxingSettings,
} from "@/lib/api/lingxing";
import { Badge } from "@/components/ui/badge";
import { Slider } from "@/components/ui/slider";
import { cn } from "@/lib/utils";
import {
  deleteExporter,
  fetchExporters,
  newExporterId,
  setActiveExporter,
  upsertExporter,
  type ExporterProfile,
} from "@/lib/api/exporters";
import {
  Table,
  TableBody,
  TableCell,
  TableRow,
} from "@/components/ui/table";

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs font-medium text-foreground">{label}</Label>
      {children}
      {hint && <p className="text-[10px] leading-tight text-muted-foreground">{hint}</p>}
    </div>
  );
}

function ExportersSection() {
  const [profiles, setProfiles] = useState<ExporterProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Partial<ExporterProfile>>({ name: "", credit_code: "", signed_at: "武汉", domestic_source: "武汉" });

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchExporters();
      setProfiles(res.profiles);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const saveDraft = async () => {
    if (!draft.name?.trim()) return;
    const id = draft.id || newExporterId(draft.name);
    setLoading(true);
    try {
      await upsertExporter(id, {
        name: draft.name.trim(),
        credit_code: draft.credit_code ?? "",
        address: draft.address ?? "",
        tel: draft.tel ?? "",
        signed_at: draft.signed_at ?? "武汉",
        domestic_source: draft.domestic_source ?? "武汉",
      });
      setDraft({ name: "", credit_code: "", signed_at: "武汉", domestic_source: "武汉" });
      await reload();
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3 rounded-md border border-border bg-muted/20 p-3">
      <p className="text-xs font-semibold text-foreground">出口商档案</p>
      {error && <p className="text-[11px] text-destructive">{error}</p>}
      <div className="max-h-36 space-y-1 overflow-y-auto">
        {profiles.map((p) => (
          <div key={p.id} className="flex items-center justify-between gap-2 rounded border border-border bg-card px-2 py-1.5 text-xs">
            <button
              type="button"
              className="truncate text-left hover:underline"
              onClick={() => setDraft(p)}
              title={p.name}
            >
              {p.name}
              {p.is_active && <Badge className="ml-1 scale-90">默认</Badge>}
            </button>
            <div className="flex shrink-0 gap-1">
              {!p.is_active && (
                <Button size="sm" variant="ghost" className="h-6 px-2 text-[10px]" onClick={() => void setActiveExporter(p.id).then(reload)}>
                  默认
                </Button>
              )}
              <Button
                size="sm"
                variant="ghost"
                className="h-6 px-2 text-[10px] text-destructive"
                onClick={() => void deleteExporter(p.id).then(reload)}
              >
                删
              </Button>
            </div>
          </div>
        ))}
      </div>
      <Field label="名称">
        <Input value={draft.name ?? ""} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} />
      </Field>
      <Field label="统一社会信用代码">
        <Input value={draft.credit_code ?? ""} onChange={(e) => setDraft((d) => ({ ...d, credit_code: e.target.value }))} />
      </Field>
      <div className="grid grid-cols-2 gap-2">
        <Field label="签约地">
          <Input value={draft.signed_at ?? ""} onChange={(e) => setDraft((d) => ({ ...d, signed_at: e.target.value }))} />
        </Field>
        <Field label="货源地">
          <Input value={draft.domestic_source ?? ""} onChange={(e) => setDraft((d) => ({ ...d, domestic_source: e.target.value }))} />
        </Field>
      </div>
      <Button size="sm" className="w-full" disabled={loading || !draft.name?.trim()} onClick={() => void saveDraft()}>
        {draft.id ? "更新出口商" : "新增出口商"}
      </Button>
    </div>
  );
}

function TemplatesSection() {
  const [templatesDir, setTemplatesDir] = useState("");
  const [files, setFiles] = useState<string[]>([]);
  const [selected, setSelected] = useState("");
  const [preview, setPreview] = useState<(string | number | null)[][]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadList = useCallback(async (keepSelection = true) => {
    setLoadingList(true);
    setError(null);
    try {
      const data = await fetchTemplatesList();
      setTemplatesDir(data.templates_dir);
      setFiles(data.files);
      setSelected((prev) => {
        if (keepSelection && prev && data.files.includes(prev)) return prev;
        return data.files[0] ?? "";
      });
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    void loadList(false);
  }, [loadList]);

  useEffect(() => {
    if (!selected) {
      setPreview([]);
      return;
    }
    setLoadingPreview(true);
    fetchTemplatePreview(selected)
      .then((res) => setPreview(res.headers))
      .catch((err) => {
        setPreview([]);
        setError(formatApiError(err));
      })
      .finally(() => setLoadingPreview(false));
  }, [selected]);

  const handleUpload = async (file: File) => {
    setUploading(true);
    setError(null);
    try {
      const res = await uploadTemplateFile(file);
      setFiles(res.files);
      setSelected(res.filename);
      await loadList(true);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setUploading(false);
    }
  };

  const handleDownload = async () => {
    if (!selected) return;
    setError(null);
    try {
      await downloadTemplateFile(selected);
    } catch (err) {
      setError(formatApiError(err));
    }
  };

  const previewCols = preview.reduce((max, row) => Math.max(max, row.length), 0);

  return (
    <AccordionItem value="templates" className="border-0 px-4">
      <AccordionTrigger className="text-sm font-semibold hover:no-underline">
        模板目录
      </AccordionTrigger>
      <AccordionContent className="space-y-3 pb-4">
        <Field label="目录路径" hint="后端实际读取的 templates 目录（只读展示）。">
          <code className="block break-all rounded-md border border-border bg-muted px-3 py-2 font-mono text-[10px] text-foreground">
            {templatesDir || "加载中…"}
          </code>
        </Field>

        <Field label="选择模板">
          <div className="flex gap-2">
            <Select
              value={selected || undefined}
              onValueChange={setSelected}
              disabled={loadingList || files.length === 0}
            >
              <SelectTrigger className="flex-1">
                <SelectValue placeholder={loadingList ? "加载中…" : "暂无模板文件"} />
              </SelectTrigger>
              <SelectContent>
                {files.map((name) => (
                  <SelectItem key={name} value={name}>
                    {name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              size="sm"
              variant="outline"
              className="shrink-0 px-2"
              onClick={() => void loadList(true)}
              disabled={loadingList}
              title="刷新列表"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loadingList ? "animate-spin" : ""}`} />
            </Button>
          </div>
        </Field>

        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            className="gap-1"
            disabled={uploading}
            onClick={() => fileInputRef.current?.click()}
          >
            <Upload className="h-3.5 w-3.5" />
            {uploading ? "上传中…" : "上传"}
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="gap-1"
            disabled={!selected}
            onClick={() => void handleDownload()}
          >
            <Download className="h-3.5 w-3.5" /> 下载
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xls,.csv"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void handleUpload(file);
              e.target.value = "";
            }}
          />
        </div>

        {files.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {files.map((name) => (
              <Badge
                key={name}
                variant="secondary"
                className={`cursor-pointer gap-1 text-[10px] ${
                  selected === name
                    ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                    : "hover:bg-muted"
                }`}
                onClick={() => setSelected(name)}
              >
                <Check className="h-3 w-3" /> {name}
              </Badge>
            ))}
          </div>
        )}

        <Field label="预览（前 8 行）" hint={selected ? `当前：${selected}` : "请先选择模板"}>
          {!selected ? (
            <p className="text-xs text-muted-foreground">目录中暂无可用模板，或尚未选择文件。</p>
          ) : loadingPreview ? (
            <p className="text-xs text-muted-foreground">加载预览…</p>
          ) : preview.length === 0 ? (
            <p className="text-xs text-muted-foreground">无法读取预览内容。</p>
          ) : (
            <TableScrollArea maxHeight="12rem">
              <Table>
                <TableBody>
                  {preview.map((row, ri) => (
                    <TableRow key={ri} className={ri === 0 ? "bg-muted/50 font-medium" : undefined}>
                      {Array.from({ length: previewCols }, (_, ci) => (
                        <TableCell key={ci} className="px-2 py-1 text-[10px] whitespace-nowrap">
                          {row[ci] ?? ""}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableScrollArea>
          )}
        </Field>

        {error && <p className="text-xs text-destructive">{error}</p>}
      </AccordionContent>
    </AccordionItem>
  );
}

export function AppSidebar({
  isOpen,
  onToggle,
}: {
  isOpen: boolean;
  onToggle: () => void;
}) {
  const [deepseekKey, setDeepseekKey] = useState("");
  const [deepseekModel, setDeepseekModel] = useState<DeepseekModel>(DEFAULT_DEEPSEEK_MODEL);
  const [temperature, setTemperature] = useState(DEFAULT_DEEPSEEK_TEMPERATURE);
  const [lingxingKey, setLingxingKey] = useState("");
  const [lingxingUrl, setLingxingUrl] = useState("https://openmcp.lingxing.com/mcp-servers/lingxing-mcp");
  const [lingxingHint, setLingxingHint] = useState("");
  const [lingxingSaving, setLingxingSaving] = useState(false);
  const [lingxingMsg, setLingxingMsg] = useState<string | null>(null);
  const { taskName, setTaskName, saveCurrentTaskToHistory, loadTaskFromHistory, refreshConfigLimits, step } =
    useWorkflow();
  const [taskNameDraft, setTaskNameDraft] = useState(taskName);
  const [historyTasks, setHistoryTasks] = useState<TaskHistoryIndexRow[]>([]);
  const [selectedHistoryId, setSelectedHistoryId] = useState("");
  const [renameDraft, setRenameDraft] = useState("");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historySaving, setHistorySaving] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const refreshHistoryTasks = useCallback(async () => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const res = await fetchTaskHistoryList();
      setHistoryTasks(res.tasks);
      setSelectedHistoryId((prev) =>
        prev && res.tasks.some((t) => t.id === prev) ? prev : (res.tasks[0]?.id ?? ""),
      );
    } catch (err) {
      setHistoryError(formatApiError(err));
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshHistoryTasks();
  }, [refreshHistoryTasks]);

  useEffect(() => {
    setTaskNameDraft(taskName);
  }, [taskName]);

  useEffect(() => {
    setTaskNameDraft(taskName);
  }, [taskName]);

  useEffect(() => {
    localStorage.removeItem(DEEPSEEK_KEY_STORAGE);
    setDeepseekKey("");
    const storedModel = localStorage.getItem(DEEPSEEK_MODEL_STORAGE);
    if (DEEPSEEK_MODEL_OPTIONS.some((m) => m.value === storedModel)) {
      setDeepseekModel(storedModel as DeepseekModel);
    }
    const storedTemp = localStorage.getItem(DEEPSEEK_TEMPERATURE_STORAGE);
    if (storedTemp) {
      const n = Number.parseFloat(storedTemp);
      if (!Number.isNaN(n)) setTemperature(Math.min(2, Math.max(0, n)));
    }
    void fetchLingxingSettings()
      .then((s) => {
        setLingxingUrl(s.mcp_url);
        setLingxingHint(s.mcp_key_hint);
      })
      .catch(() => {
        setLingxingMsg("无法读取领星配置（后端未启动？）");
      });
  }, []);

  const saveDeepseekKey = (value: string) => {
    void fetch("/api/settings/deepseek-key", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: value }),
    }).finally(() => setDeepseekKey(""));
  };

  const saveDeepseekModel = (value: DeepseekModel) => {
    setDeepseekModel(value);
    localStorage.setItem(DEEPSEEK_MODEL_STORAGE, value);
  };

  const saveTemperature = (value: number) => {
    setTemperature(value);
    localStorage.setItem(DEEPSEEK_TEMPERATURE_STORAGE, String(value));
  };

  const saveLingxing = async () => {
    setLingxingSaving(true);
    setLingxingMsg(null);
    try {
      const body: { mcp_url: string; mcp_key?: string } = { mcp_url: lingxingUrl.trim() };
      if (lingxingKey.trim()) body.mcp_key = lingxingKey.trim();
      const saved = await saveLingxingSettings(body);
      setLingxingHint(saved.mcp_key_hint);
      setLingxingKey("");
      setLingxingMsg(saved.mcp_key_set ? `已保存（${saved.mcp_key_hint}）` : "已保存 URL，尚未填写 Key");
    } catch (err) {
      setLingxingMsg(formatApiError(err));
    } finally {
      setLingxingSaving(false);
    }
  };

  return (
    <aside
      className={cn(
        "relative z-30 flex h-[calc(100vh-73px)] shrink-0 flex-col overflow-hidden border-r border-border bg-card transition-[width] duration-300 ease-in-out",
        isOpen ? "w-[340px]" : "w-12",
      )}
    >
      {!isOpen ? (
        <div className="flex h-full flex-col items-center py-3">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-9 w-9 shrink-0"
            onClick={onToggle}
            title="展开侧边栏"
            aria-label="展开侧边栏"
          >
            <PanelLeftOpen className="h-4 w-4" />
          </Button>
        </div>
      ) : (
        <>
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <span className="text-xs font-medium text-muted-foreground">侧边栏</span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 gap-1 px-2 text-xs text-muted-foreground"
          onClick={onToggle}
          title="收起侧边栏"
        >
          <PanelLeftClose className="h-3.5 w-3.5" />
          收起
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto">
        <Accordion
          type="multiple"
          defaultValue={[]}
          className="divide-y divide-border"
        >
          {/* 1. 系统设置 */}
          <AccordionItem value="system" className="border-0 px-4">
            <AccordionTrigger className="text-sm font-semibold hover:no-underline">
              系统设置
            </AccordionTrigger>
            <AccordionContent className="space-y-3 pb-4">
              <Field
                label="DeepSeek API Key"
                hint="智能文本解析需要 API Key；本地逗号分隔解析无需 Key。"
              >
                <Input
                  type="password"
                  placeholder="sk-..."
                  value={deepseekKey}
                  onChange={(e) => saveDeepseekKey(e.target.value)}
                />
              </Field>
              <Field label="DeepSeek 模型" hint="解析与发票 AI 补全均使用所选模型。">
                <Select value={deepseekModel} onValueChange={(v) => saveDeepseekModel(v as DeepseekModel)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {DEEPSEEK_MODEL_OPTIONS.map((m) => (
                      <SelectItem key={m.value} value={m.value}>
                        {m.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field
                label={`Temperature · ${temperature.toFixed(2)}`}
                hint="越低越稳定，越高越有创造性。建议解析/发票：0.1–0.3。"
              >
                <Slider
                  min={0}
                  max={2}
                  step={0.05}
                  value={[temperature]}
                  onValueChange={(vals) => saveTemperature(Number(vals[0] ?? 0))}
                />
              </Field>
              <Field
                label="领星 MCP Key"
                hint={lingxingHint ? `当前已保存：${lingxingHint}。密钥只写本机 app_data，不会进 Git。` : "在领星开放平台复制 MCP Key，保存后用于主数据一键同步。"}
              >
                <Input
                  type="password"
                  placeholder={lingxingHint ? "留空则保持已保存的 Key" : "粘贴 X-Mcp-Key"}
                  value={lingxingKey}
                  onChange={(e) => setLingxingKey(e.target.value)}
                />
              </Field>
              <Field label="领星 MCP URL">
                <Input
                  value={lingxingUrl}
                  onChange={(e) => setLingxingUrl(e.target.value)}
                />
              </Field>
              <Button
                type="button"
                size="sm"
                variant="secondary"
                disabled={lingxingSaving}
                onClick={() => void saveLingxing()}
              >
                {lingxingSaving ? "保存中…" : "保存领星设置"}
              </Button>
              {lingxingMsg && <p className="text-[10px] leading-tight text-muted-foreground">{lingxingMsg}</p>}
              <Link
                to="/"
                data-testid="nav-workflow"
                className="flex items-center gap-2 rounded-md border border-border bg-muted/30 px-3 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-muted/60"
                activeProps={{ className: "border-primary/30 bg-primary/10 text-primary" }}
              >
                工作流
              </Link>
              <Link
                to="/master-data"
                className="flex items-center gap-2 rounded-md border border-border bg-muted/30 px-3 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-muted/60"
                activeProps={{ className: "border-primary/30 bg-primary/10 text-primary" }}
              >
                📦 产品主数据库
              </Link>
              <Link
                to="/pdf-labels"
                className="flex items-center gap-2 rounded-md border border-border bg-muted/30 px-3 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-muted/60"
                activeProps={{ className: "border-primary/30 bg-primary/10 text-primary" }}
              >
                🧰 PDF 标签处理
              </Link>
              <Link
                to="/carton-compare"
                data-testid="nav-carton"
                className="flex items-center gap-2 rounded-md border border-border bg-muted/30 px-3 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-muted/60"
                activeProps={{ className: "border-primary/30 bg-primary/10 text-primary" }}
                onClick={() => rememberReturnStep(step)}
              >
                箱规对比
              </Link>
              <Link
                to="/about"
                className="flex items-center gap-2 rounded-md border border-border bg-muted/30 px-3 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-muted/60"
                activeProps={{ className: "border-primary/30 bg-primary/10 text-primary" }}
              >
                关于
              </Link>
              <ExportersSection />
            </AccordionContent>
          </AccordionItem>

          {/* 2. 历史任务 */}
          <AccordionItem value="history" className="border-0 px-4">
            <AccordionTrigger className="text-sm font-semibold hover:no-underline">
              历史任务
            </AccordionTrigger>
            <AccordionContent className="space-y-3 pb-4">
              <div className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
                当前：<span className="font-medium text-foreground">{taskName}</span>
              </div>
              <p className="text-[10px] leading-tight text-muted-foreground">
                点击右上角「重新开始」时会自动将当前任务存入历史。
              </p>

              {historyError && (
                <p className="text-[11px] text-destructive">{historyError}</p>
              )}

              <Field label="任务名称">
                <div className="space-y-2">
                  <Input
                    placeholder="留空则自动命名"
                    className="w-full min-w-0"
                    value={taskNameDraft}
                    onChange={(e) => setTaskNameDraft(e.target.value)}
                  />
                  <Button
                    size="sm"
                    className="w-full"
                    variant="secondary"
                    onClick={() => setTaskName(taskNameDraft.trim() || autoTaskName())}
                  >
                    应用
                  </Button>
                </div>
              </Field>

              <Button
                size="sm"
                className="w-full"
                disabled={historySaving}
                onClick={async () => {
                  setHistorySaving(true);
                  setHistoryError(null);
                  try {
                    const savedName = await saveCurrentTaskToHistory(
                      taskNameDraft.trim() || taskName,
                    );
                    setTaskName(savedName);
                    setTaskNameDraft(savedName);
                    await refreshHistoryTasks();
                  } catch (err) {
                    setHistoryError(formatApiError(err));
                  } finally {
                    setHistorySaving(false);
                  }
                }}
              >
                {historySaving ? "保存中…" : "保存当前任务"}
              </Button>

              <Field label="选择历史任务">
                <div className="space-y-2">
                  <Select
                    value={selectedHistoryId}
                    onValueChange={setSelectedHistoryId}
                    disabled={historyLoading || historyTasks.length === 0}
                  >
                    <SelectTrigger className="w-full min-w-0">
                      <SelectValue placeholder={historyLoading ? "加载中…" : "选择任务..."} />
                    </SelectTrigger>
                    <SelectContent>
                      {historyTasks.map((task) => (
                        <SelectItem key={task.id} value={task.id}>
                          {task.name}
                          {task.updated_at ? ` · ${task.updated_at}` : ""}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button
                    size="sm"
                    className="w-full"
                    variant="secondary"
                    disabled={!selectedHistoryId || historyLoading}
                    onClick={async () => {
                      if (!selectedHistoryId) return;
                      setHistoryLoading(true);
                      setHistoryError(null);
                      try {
                        const res = await loadTaskHistory(selectedHistoryId);
                        loadTaskFromHistory(res.snapshot);
                        await refreshHistoryTasks();
                      } catch (err) {
                        setHistoryError(formatApiError(err));
                      } finally {
                        setHistoryLoading(false);
                      }
                    }}
                  >
                    {historyLoading ? "加载中…" : "加载选中任务"}
                  </Button>
                </div>
              </Field>

              <Field label="重命名 / 删除">
                <div className="space-y-2">
                  <Input
                    placeholder="新名称"
                    className="w-full min-w-0"
                    value={renameDraft}
                    onChange={(e) => setRenameDraft(e.target.value)}
                  />
                  <div className="grid grid-cols-2 gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={!selectedHistoryId || !renameDraft.trim()}
                    onClick={async () => {
                      if (!selectedHistoryId || !renameDraft.trim()) return;
                      setHistoryError(null);
                      try {
                        await renameTaskHistory(selectedHistoryId, renameDraft.trim());
                        await refreshHistoryTasks();
                      } catch (err) {
                        setHistoryError(formatApiError(err));
                      }
                    }}
                  >
                    重命名
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    disabled={!selectedHistoryId}
                    onClick={async () => {
                      if (!selectedHistoryId) return;
                      setHistoryError(null);
                      try {
                        await deleteTaskHistory(selectedHistoryId);
                        setSelectedHistoryId("");
                        setRenameDraft("");
                        await refreshHistoryTasks();
                      } catch (err) {
                        setHistoryError(formatApiError(err));
                      }
                    }}
                  >
                    删除
                  </Button>
                  </div>
                </div>
              </Field>
            </AccordionContent>
          </AccordionItem>

          <TemplatesSection />

          {/* 4. 产品主数据（已收口至 SQLite，见 /master-data） */}
          <AccordionItem value="products" className="border-0 px-4">
            <AccordionTrigger className="text-sm font-semibold hover:no-underline">
              产品主数据
            </AccordionTrigger>
            <AccordionContent className="space-y-3 pb-4">
              <p className="text-xs text-muted-foreground">
                发票报关字段、尺寸与条码已统一维护在产品主数据库（SQLite），不再使用本地 产品信息表.csv。
              </p>
              <Button size="sm" variant="secondary" className="w-full" asChild>
                <Link to="/master-data">打开产品主数据库 →</Link>
              </Button>
            </AccordionContent>
          </AccordionItem>

          {/* 5. 参数与公式 */}
          <AccordionItem value="params" className="border-0 px-4">
            <AccordionTrigger className="text-sm font-semibold hover:no-underline">
              参数与公式（持久化）
            </AccordionTrigger>
            <AccordionContent className="space-y-3 pb-4">
              <ParamsSection
                onSaved={() => {
                  void refreshConfigLimits().catch(() => undefined);
                }}
              />
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </div>

      <div className="border-t border-border px-4 py-3">
        <p className="text-[10px] leading-tight text-muted-foreground/70">
          也可使用页面右上角「重新开始」清空当前任务（会自动存入历史）。
        </p>
      </div>
        </>
      )}
    </aside>
  );
}
