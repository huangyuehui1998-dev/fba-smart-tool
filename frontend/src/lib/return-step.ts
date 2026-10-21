const KEY = "fba_return_step";

export function rememberReturnStep(step: number): void {
  try {
    sessionStorage.setItem(KEY, String(step));
  } catch {
    // 隐私模式写不了 sessionStorage 时，工作流步骤仍留在内存里。
  }
}

export function readReturnStep(): number | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (raw == null || raw === "") return null;
    const value = Number(raw);
    return Number.isFinite(value) ? value : null;
  } catch {
    return null;
  }
}
