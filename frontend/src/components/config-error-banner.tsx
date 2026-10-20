import { useEffect, useState } from "react";
import { resolveApiUrl } from "@/lib/api/client";

type ConfigError = { file: string; message: string };

/** S7-fix1：user_settings.json / formulas.json 写坏时在顶部提示（后端同时写日志，暂用出厂值） */
export function ConfigErrorBanner() {
  const [errors, setErrors] = useState<ConfigError[]>([]);
  useEffect(() => {
    fetch(resolveApiUrl("/api/config/errors"))
      .then((r) => (r.ok ? r.json() : null))
      .then((j: { errors?: ConfigError[] } | null) => setErrors(j?.errors ?? []))
      .catch(() => setErrors([]));
  }, []);
  if (!errors.length) return null;
  return (
    <div role="alert" className="border-b border-amber-300 bg-amber-50 px-6 py-2 text-xs text-amber-800">
      {errors.map((e) => (
        <div key={e.file}>
          配置文件 {e.file} 有问题，已暂时使用出厂值：{e.message}。改好后刷新页面。
        </div>
      ))}
    </div>
  );
}
