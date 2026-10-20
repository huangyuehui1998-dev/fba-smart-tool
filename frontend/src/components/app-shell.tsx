import { useCallback, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";
import { toast } from "sonner";

import { AppHeader } from "@/components/app-header";

import { AppSidebar } from "@/components/app-sidebar";
import { ConfigErrorBanner } from "@/components/config-error-banner";

import { useWorkflow } from "@/context/workflow-context";

import {

  getSidebarOpenSnapshot,

  setSidebarOpen,

  subscribeSidebarOpen,

} from "@/lib/deepseek-settings";

import { APP_SIDEBAR_WIDTH_VAR, sidebarWidthCss } from "@/lib/layout";
import { canEnterStep, getStepBlockReason } from "@/lib/workflow-steps";



export function AppShell({ children }: { children: ReactNode }) {

  const {

    taskName,

    showRestoredToast,

    dismissRestoredToast,

    showArchivedToast,

    archivedTaskName,

    dismissArchivedToast,

    resetWorkflow,

    saveTaskToFile,

    step,

    setStep,

    inputRows,

    boxLocked,

    boxEditorApi,

    step4Ok,

    highestReachedStep,

    projectFileName,

    fboxSaveStatus,

    fboxWritable,

    staleness,

  } = useWorkflow();

  const [restarting, setRestarting] = useState(false);
  const [savingTask, setSavingTask] = useState(false);

  const stepGuard = useMemo(
    () => ({ inputRows, boxLocked, boxEditorApi, step4Ok, highestReachedStep }),
    [inputRows, boxLocked, boxEditorApi, step4Ok, highestReachedStep],
  );

  const handleStepChange = useCallback(
    (next: number) => {
      if (!canEnterStep(next, step, stepGuard)) {
        toast.error(getStepBlockReason(next, stepGuard) ?? "无法进入该步骤");
        return;
      }
      setStep(next);
    },
    [step, stepGuard, setStep],
  );

  const isSidebarOpenState = useSyncExternalStore(

    subscribeSidebarOpen,

    getSidebarOpenSnapshot,

    () => false,

  );



  const toggleSidebar = useCallback(() => {

    setSidebarOpen(!isSidebarOpenState);

  }, [isSidebarOpenState]);



  return (

    <div

      className="flex min-h-screen flex-col bg-background"

      style={{ [APP_SIDEBAR_WIDTH_VAR]: sidebarWidthCss(isSidebarOpenState) } as React.CSSProperties}

    >

      <AppHeader

        currentStep={step}

        taskName={taskName}

        showRestoredToast={showRestoredToast}

        onDismissRestored={dismissRestoredToast}

        showArchivedToast={showArchivedToast}

        archivedTaskName={archivedTaskName}

        onDismissArchived={dismissArchivedToast}

        onStepChange={handleStepChange}

        projectFileName={projectFileName}

        fboxSaveStatus={fboxSaveStatus}

        fboxWritable={fboxWritable}

        staleness={staleness}

        stepGuard={stepGuard}

        restarting={restarting}
        savingTask={savingTask}

        onSaveTask={async () => {
          setSavingTask(true);
          try {
            const fileName = await saveTaskToFile();
            toast.success("任务已保存", { description: fileName });
          } catch (err) {
            const msg = err instanceof Error ? err.message : "保存失败";
            if (msg !== "已取消保存") {
              toast.error(msg);
            }
          } finally {
            setSavingTask(false);
          }
        }}

        onRestart={async () => {

          setRestarting(true);

          try {

            await resetWorkflow();

          } finally {

            setRestarting(false);

          }

        }}

      />

      <ConfigErrorBanner />

      <div className="relative flex flex-1">

        <AppSidebar isOpen={isSidebarOpenState} onToggle={toggleSidebar} />

        <main className="relative z-0 min-w-0 flex-1 overflow-auto p-6 transition-[width] duration-300 ease-in-out">

          {children}

        </main>

      </div>

    </div>

  );

}

