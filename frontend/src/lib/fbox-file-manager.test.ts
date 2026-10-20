import { describe, expect, it, vi, afterEach } from "vitest";

import {
  FBOX_CURRENT_VERSION,
  defaultFboxFileName,
  isFboxFileDrag,
  isFboxFileName,
  migrateProjectData,
  parseFboxText,
  serializeFboxProject,
  throttle,
} from "./fbox-file-manager";

describe("migrateProjectData", () => {
  it("migrates v1 project with grid_data", () => {
    const raw = {
      version: 1,
      task_id: "task-abc",
      task_name: "Task-20260101",
      saved_at: "2026-01-01T00:00:00.000Z",
      grid_data: {
        task_id: "task-abc",
        task_name: "Task-20260101",
        step: 2,
        input_df: [],
      },
      settings: { step: 2, throw_ratio: 6000 },
    };
    const migrated = migrateProjectData(raw);
    expect(migrated.version).toBe(FBOX_CURRENT_VERSION);
    expect(migrated.task_id).toBe("task-abc");
    expect(migrated.task_name).toBe("Task-20260101");
    expect(migrated.settings.step).toBe(2);
    expect(migrated.settings.throw_ratio).toBe(6000);
    expect(migrated.grid_data.step).toBe(2);
  });

  it("upgrades legacy snapshot without version to v1", () => {
    const legacy = {
      task_id: "legacy-1",
      task_name: "Legacy",
      step: 3,
      react_throw_ratio: 5000,
      input_df: [{ SKU: "A" }],
    };
    const migrated = migrateProjectData(legacy);
    expect(migrated.version).toBe(1);
    expect(migrated.task_id).toBe("legacy-1");
    expect(migrated.settings.throw_ratio).toBe(5000);
  });

  it("rejects invalid root", () => {
    expect(() => migrateProjectData(null)).toThrow(/无效/);
    expect(() => migrateProjectData("text")).toThrow(/无效/);
  });

  it("rejects newer version than software", () => {
    expect(() => migrateProjectData({ version: 99 })).toThrow(/高于当前软件/);
  });
});

describe("parseFboxText", () => {
  it("parses valid JSON through migration", () => {
    const project = {
      version: 1,
      task_id: "t1",
      task_name: "Demo",
      saved_at: "2026-06-25T00:00:00.000Z",
      grid_data: { task_id: "t1", task_name: "Demo", step: 1 },
      settings: {},
    };
    const parsed = parseFboxText(JSON.stringify(project));
    expect(parsed.task_id).toBe("t1");
  });

  it("throws on malformed JSON", () => {
    expect(() => parseFboxText("{")).toThrow(/不是有效的 JSON/);
  });
});

describe("serializeFboxProject", () => {
  it("round-trips through parse", () => {
    const project = migrateProjectData({
      version: 1,
      task_id: "t2",
      task_name: "Round",
      grid_data: { task_id: "t2", task_name: "Round", step: 1 },
      settings: {},
    });
    const text = serializeFboxProject(project);
    expect(JSON.parse(text).version).toBe(1);
    expect(parseFboxText(text).task_name).toBe("Round");
  });
});

describe("defaultFboxFileName", () => {
  it("appends .fbox extension", () => {
    expect(defaultFboxFileName("MyTask")).toMatch(/\.fbox$/);
    expect(defaultFboxFileName("already.fbox")).toBe("already.fbox");
  });

  it("sanitizes illegal filename characters", () => {
    expect(defaultFboxFileName('bad<>:"|?*name')).not.toMatch(/[<>:"/\\|?*]/);
  });
});

describe("isFboxFileName", () => {
  it("detects .fbox extension case-insensitively", () => {
    expect(isFboxFileName("task.FBOX")).toBe(true);
    expect(isFboxFileName("task.json")).toBe(false);
  });
});

describe("isFboxFileDrag", () => {
  it("returns true when dragged file ends with .fbox", () => {
    const file = new File(["{}"], "demo.fbox", { type: "application/json" });
    const dt = {
      types: ["Files"],
      items: [{ kind: "file", getAsFile: () => file }],
    } as unknown as DataTransfer;
    const event = { dataTransfer: dt } as DragEvent;
    expect(isFboxFileDrag(event)).toBe(true);
  });
});

describe("throttle", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("invokes at most once per window", () => {
    vi.useFakeTimers();
    const fn = vi.fn();
    const throttled = throttle(fn, 2000);
    throttled();
    throttled();
    throttled();
    expect(fn).not.toHaveBeenCalled();
    vi.advanceTimersByTime(2000);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("flush runs pending invocation immediately", () => {
    vi.useFakeTimers();
    const fn = vi.fn();
    const throttled = throttle(fn, 2000);
    throttled();
    throttled.flush();
    expect(fn).toHaveBeenCalledTimes(1);
  });
});
