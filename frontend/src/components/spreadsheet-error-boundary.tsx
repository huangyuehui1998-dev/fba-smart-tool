import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

interface Props {
  children: ReactNode;
  /** 变化时清除已捕获的渲染错误（例如 Workbook 重挂载后） */
  resetKey?: number | string;
  onError?: (error: Error) => void;
}

interface State {
  error: Error | null;
}

export class SpreadsheetErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[InvoiceSpreadsheet]", error, info);
    this.props.onError?.(error);
  }

  componentDidUpdate(prevProps: Props) {
    if (this.state.error && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  render() {
    if (this.state.error) {
      return (
        <Alert variant="destructive" className="rounded-lg">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle className="text-sm">表格渲染失败</AlertTitle>
          <AlertDescription className="text-xs">
            {this.state.error.message || "FortuneSheet 无法加载该模板，请尝试重新上传或换一份 .xlsx 文件。"}
          </AlertDescription>
        </Alert>
      );
    }
    return this.props.children;
  }
}
