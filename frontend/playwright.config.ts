import { defineConfig, devices } from "@playwright/test";

import { e2ePython } from "./e2e/python-bin";

const python = e2ePython();

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:4173",
    viewport: { width: 1440, height: 1800 },
  },
  webServer: [
    {
      command: `${python} -m uvicorn main:app --host 127.0.0.1 --port 8002`,
      cwd: "../backend",
      url: "http://127.0.0.1:8002/api/health",
      reuseExistingServer: true,
      timeout: 120_000,
      env: {
        ...process.env,
        FBA_APP_DATA_DIR: "/tmp/fba-e2e-data",
        FBA_DISABLE_SCHEDULER: "1",
      },
    },
    {
      command: "npm run preview -- --host 127.0.0.1 --port 4173 --strictPort",
      url: "http://127.0.0.1:4173",
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
});
