/** Playwright 和种子脚本共用。默认仍是 /tmp/fba-e2e-data，可用 FBA_E2E_DATA_DIR 换掉。 */
export function e2eDataDir(): string {
  return process.env.FBA_E2E_DATA_DIR || "/tmp/fba-e2e-data";
}
