import React, { useState, useCallback, useEffect } from "react";
import { Upload, X, FileSpreadsheet, Download, FileBox, PanelLeftClose, PanelLeftOpen, Trash2, History, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { TableScrollArea } from "@/components/table-scroll-area";
import {
  exportRoutingPreviewWithWarnings,
  downloadRoutingForwarder,
  saveRoutingSnapshot,
  getRoutingSnapshots,
  deleteRoutingSnapshot,
  RoutingSnapshot,
} from "@/lib/api/routing";
import {
  forwarderTableColumns,
  formatForwarderCell,
  isForwarderSubtotalRow,
  shouldSkipForwarderCell,
  forwarderDimColSpan,
} from "@/lib/forwarder-table";
import { useWorkflow } from "@/context/workflow-context";
import { StaleDataBanner } from "@/components/stale-data-banner";
import { Input } from "@/components/ui/input";

export function Step35RoutingWorkspace() {
  const { taskId, staleness, clearStageStale, setRoutingSnapshotCount } = useWorkflow();
  const [files, setFiles] = useState<File[]>([]);
  const [previewData, setPreviewData] = useState<any[] | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [snapshots, setSnapshots] = useState<RoutingSnapshot[]>([]);
  const [activeSnapshotId, setActiveSnapshotId] = useState<string | null>(null);
  const [saveName, setSaveName] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [whWarnings, setWhWarnings] = useState<string[]>([]);

  const loadSnapshots = useCallback(async () => {
    if (!taskId) return;
    try {
      const data = await getRoutingSnapshots(taskId);
      setSnapshots(data);
    } catch (e) {
      console.error("加载快照失败", e);
    }
  }, [taskId]);

  useEffect(() => {
    loadSnapshots();
  }, [loadSnapshots]);

  useEffect(() => {
    setRoutingSnapshotCount(snapshots.length);
  }, [snapshots.length, setRoutingSnapshotCount]);

  const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const droppedFiles = Array.from(e.dataTransfer.files).filter(
      (f) => f.name.toLowerCase().endsWith(".csv")
    );
    setFiles((prev) => [...prev, ...droppedFiles]);
  }, []);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const selectedFiles = Array.from(e.target.files).filter(
        (f) => f.name.toLowerCase().endsWith(".csv")
      );
      setFiles((prev) => [...prev, ...selectedFiles]);
    }
  }, []);

  const handleRemoveFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
    setPreviewData(null);
    setActiveSnapshotId(null);
  };

  const handleGeneratePreview = async () => {
    if (files.length === 0) {
      toast.error("请先上传分仓 CSV 文件");
      return;
    }

    setIsLoading(true);
    try {
      const { rows: data, warnings } = await exportRoutingPreviewWithWarnings(files);
      setPreviewData(data);
      setWhWarnings(warnings);
      warnings.forEach((w) => toast.warning(w, { duration: 10000 }));
      setActiveSnapshotId(null);
      setSaveName("");
      clearStageStale("routing");
      toast.success("成功生成刷仓货代表预览");
    } catch (err: any) {
      toast.error(err.message || "生成失败");
    } finally {
      setIsLoading(false);
    }
  };

  const handleDownload = async () => {
    if (staleness.routing) {
      toast.error("刷仓结果已过期，请重新生成预览后再下载");
      return;
    }
    if (!previewData || previewData.length === 0) return;
    try {
      await downloadRoutingForwarder(previewData);
      toast.success("货代表已开始下载");
    } catch (err: any) {
      toast.error(err.message || "下载失败");
    }
  };

  const handleSaveSnapshot = async () => {
    if (!previewData || previewData.length === 0) return;
    setIsSaving(true);
    try {
      await saveRoutingSnapshot(taskId, saveName, previewData);
      toast.success("方案保存成功！");
      setSaveName("");
      await loadSnapshots();
    } catch (err: any) {
      toast.error(err.message || "保存失败");
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeleteSnapshot = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await deleteRoutingSnapshot(id);
      toast.success("方案删除成功！");
      if (activeSnapshotId === id) {
        setActiveSnapshotId(null);
        setPreviewData(null);
      }
      await loadSnapshots();
    } catch (err: any) {
      toast.error(err.message || "删除失败");
    }
  };

  const handleSelectSnapshot = (snapshot: RoutingSnapshot) => {
    setActiveSnapshotId(snapshot.id);
    setPreviewData(snapshot.forwarder_data);
  };

  const handleNewSnapshot = () => {
    setActiveSnapshotId(null);
    setPreviewData(null);
    setFiles([]);
    setSaveName("");
  };

  const forwarderCols = previewData && previewData.length > 0 
    ? forwarderTableColumns(previewData) 
    : [];

  return (
    <div className="flex h-full w-full bg-white dark:bg-zinc-950 overflow-hidden relative">
      {/* 隐藏/展开开关 (悬浮于左上角) */}
      <Button
        variant="ghost"
        size="icon"
        className="absolute top-3 left-3 z-50 text-zinc-500 hover:text-zinc-900 bg-white/50 backdrop-blur"
        onClick={() => setIsSidebarOpen(!isSidebarOpen)}
      >
        {isSidebarOpen ? <PanelLeftClose className="w-5 h-5" /> : <PanelLeftOpen className="w-5 h-5" />}
      </Button>

      {/* 左侧历史抽屉 */}
      <div
        className={`flex-none bg-zinc-50 dark:bg-zinc-900 border-r dark:border-zinc-800 transition-all duration-300 flex flex-col ${
          isSidebarOpen ? "w-64" : "w-0 overflow-hidden opacity-0"
        }`}
      >
        <div className="p-4 pt-14 border-b dark:border-zinc-800">
          <Button onClick={handleNewSnapshot} className="w-full flex items-center justify-center gap-2">
            <Plus className="w-4 h-4" /> 新建刷仓方案
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto p-3">
          <div className="flex items-center gap-2 text-sm text-zinc-500 mb-3 px-1">
            <History className="w-4 h-4" /> 历史方案 ({snapshots.length})
          </div>
          <div className="space-y-2">
            {snapshots.map((s) => (
              <div
                key={s.id}
                onClick={() => handleSelectSnapshot(s)}
                className={`group p-3 rounded-md cursor-pointer border transition-colors relative ${
                  activeSnapshotId === s.id
                    ? "bg-indigo-50 border-indigo-200 dark:bg-indigo-950/30 dark:border-indigo-800"
                    : "bg-white dark:bg-zinc-950 border-transparent hover:border-zinc-200 dark:hover:border-zinc-800 shadow-sm"
                }`}
              >
                <div className="font-medium text-sm truncate pr-6 text-zinc-900 dark:text-zinc-100">
                  {s.name}
                </div>
                <div className="text-xs text-zinc-500 mt-1 truncate">
                  {s.created_at}
                </div>
                <button
                  onClick={(e) => handleDeleteSnapshot(s.id, e)}
                  className="absolute right-2 top-2 p-1 text-zinc-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity rounded hover:bg-zinc-100 dark:hover:bg-zinc-800"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
            {snapshots.length === 0 && (
              <p className="text-xs text-zinc-400 text-center py-6">暂无历史方案</p>
            )}
          </div>
        </div>
      </div>

      {/* 右侧主工作区 */}
      <div className="flex-1 flex flex-col min-w-0 transition-all duration-300">
        <div className="flex-none p-4 pl-14 border-b dark:border-zinc-800 flex justify-between items-center bg-zinc-50 dark:bg-zinc-900/50">
          <div>
            <h1 className="text-xl font-bold flex items-center gap-2">
              <FileSpreadsheet className="w-5 h-5 text-indigo-500" />
              刷仓货代表助手
            </h1>
            <p className="text-sm text-zinc-500 mt-1">
              上传分发给不同仓库的 CSV 装箱单（例如“第一票ONT8.csv”），一键合并生成全套货代表信息。
            </p>
          </div>
          <div className="flex gap-2">
            <Button
              onClick={handleDownload}
              disabled={!previewData || previewData.length === 0 || staleness.routing}
              title={staleness.routing ? "结果已过期，不能作为正式文件下载" : undefined}
              variant="outline"
            >
              <Download className="w-4 h-4 mr-2" />
              下载 Excel
            </Button>
          </div>
        </div>

        <div className="flex-1 flex flex-col md:flex-row overflow-hidden bg-zinc-50/50 dark:bg-zinc-950 relative">
          {/* 当选中历史快照时，隐藏上传区，给表格最大空间 */}
          {!activeSnapshotId && (
            <div className="w-full md:w-80 border-r dark:border-zinc-800 flex flex-col p-4 overflow-y-auto shrink-0 bg-white dark:bg-zinc-950">
              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleDrop}
                className="border-2 border-dashed rounded-lg p-6 flex flex-col items-center justify-center text-center cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-900/50 transition-colors"
              >
                <Upload className="w-8 h-8 text-zinc-400 mb-2" />
                <p className="text-sm font-medium mb-1">拖拽 CSV 文件到此处</p>
                <p className="text-xs text-zinc-500 mb-4">或者点击下方按钮选择</p>
                <label>
                  <Button variant="outline" size="sm" className="cursor-pointer" asChild>
                    <span>选择文件</span>
                  </Button>
                  <input
                    type="file"
                    multiple
                    accept=".csv"
                    className="hidden"
                    onChange={handleFileSelect}
                  />
                </label>
              </div>

              <div className="mt-6 flex-1">
                <h3 className="font-semibold text-sm mb-3 flex items-center gap-2">
                  <FileBox className="w-4 h-4" />
                  已选文件 ({files.length})
                </h3>
                <ul className="space-y-2">
                  {files.map((file, i) => (
                    <li
                      key={i}
                      className="flex items-center justify-between text-sm p-2 rounded bg-zinc-50 dark:bg-zinc-900 border dark:border-zinc-800"
                    >
                      <span className="truncate flex-1 mr-2" title={file.name}>
                        {file.name}
                      </span>
                      <button
                        onClick={() => handleRemoveFile(i)}
                        className="text-zinc-400 hover:text-red-500 p-1 rounded hover:bg-zinc-200 dark:hover:bg-zinc-800 transition-colors"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </li>
                  ))}
                  {files.length === 0 && (
                    <p className="text-sm text-zinc-500 text-center py-4">暂无文件</p>
                  )}
                </ul>
              </div>

              <div className="mt-4 pt-4 border-t dark:border-zinc-800">
                <Button
                  onClick={handleGeneratePreview}
                  disabled={files.length === 0 || isLoading}
                  className="w-full bg-indigo-600 hover:bg-indigo-700 text-white"
                >
                  {isLoading ? "正在生成..." : "生成货代表预览"}
                </Button>
              </div>
            </div>
          )}

          {/* 右侧预览区 */}
          <div className="flex-1 p-4 overflow-hidden flex flex-col bg-transparent">
            {/* 顶层操作条：展示方案信息 / 保存功能 */}
            <div className="flex items-center justify-between mb-3 min-h-[32px]">
              <div className="font-semibold text-sm">
                {activeSnapshotId ? (
                  <span className="flex items-center gap-2 text-indigo-600">
                    <History className="w-4 h-4" /> 正在查看历史方案
                  </span>
                ) : (
                  <span>预览数据</span>
                )}
              </div>
              
              {!activeSnapshotId && previewData && previewData.length > 0 && (
                <div className="flex items-center gap-2">
                  <Input
                    placeholder="给这个方案起个名字..."
                    value={saveName}
                    onChange={(e) => setSaveName(e.target.value)}
                    className="w-48 h-8 text-sm"
                  />
                  <Button
                    size="sm"
                    onClick={handleSaveSnapshot}
                    disabled={isSaving}
                    variant="outline"
                    className="h-8"
                  >
                    💾 保存为历史方案
                  </Button>
                </div>
              )}
            </div>

            {whWarnings.length > 0 && previewData && !activeSnapshotId && (
              <ul className="mb-2 list-disc space-y-0.5 rounded border border-amber-300 bg-amber-50 py-2 pl-6 pr-3 text-xs text-amber-800">
                {whWarnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            )}

            {!previewData ? (
              <div className="flex-1 flex items-center justify-center border rounded-lg bg-white dark:bg-zinc-900 text-zinc-400">
                {activeSnapshotId ? "方案数据为空" : "请上传文件并点击“生成货代表预览”"}
              </div>
            ) : (
              <TableScrollArea>
                <Table>
                  <TableHeader className="sticky top-0 bg-zinc-100 dark:bg-zinc-800 z-10">
                    <TableRow>
                      {forwarderCols.map((c) => (
                        <TableHead
                          key={c}
                          className="font-bold text-zinc-900 dark:text-zinc-100 border-x dark:border-zinc-700 whitespace-nowrap text-center"
                        >
                          {c}
                        </TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {previewData.map((row, i) => {
                      const isSubtotal = isForwarderSubtotalRow(row);
                      return (
                        <TableRow
                          key={i}
                          className={
                            isSubtotal ? "bg-orange-50/50 dark:bg-orange-950/20 font-medium" : ""
                          }
                        >
                          {forwarderCols.map((c) => {
                            if (shouldSkipForwarderCell(c, row)) return null;
                            const dimSpan = c === "箱子长(cm)" ? forwarderDimColSpan(row) : undefined;
                            return (
                              <TableCell
                                key={c}
                                colSpan={dimSpan}
                                className="border-x dark:border-zinc-800 whitespace-nowrap"
                              >
                                {formatForwarderCell(c, row)}
                              </TableCell>
                            );
                          })}
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableScrollArea>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
