import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";

/** Playwright 启动后端用的 Python。设了 FBA_E2E_PYTHON 就用它；否则用现成的 venv，再不行就用当前 python3。 */
export function e2ePython(): string {
  const fromEnv = process.env.FBA_E2E_PYTHON?.trim();
  if (fromEnv) return fromEnv;
  const preferred = "/tmp/fba-venv/bin/python";
  if (existsSync(preferred)) return preferred;
  for (const cmd of ["python3", "python"]) {
    try {
      const found = execFileSync(cmd, ["-c", "import sys; print(sys.executable)"], {
        encoding: "utf-8",
        timeout: 10_000,
      }).trim();
      if (found && existsSync(found)) return found;
    } catch {
      // 这个名字不在 PATH 上，试下一个。
    }
  }
  return "python3";
}
