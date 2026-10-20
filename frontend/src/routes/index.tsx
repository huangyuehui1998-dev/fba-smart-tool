import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/app-shell";
import { FboxDropOverlay } from "@/components/fbox-drop-overlay";
import { Step1Workspace } from "@/components/step1-workspace";
import { Step2Workspace } from "@/components/step2-workspace";
import { Step3Workspace } from "@/components/step3-workspace";
import { Step35RoutingWorkspace } from "@/components/step3-5-routing-workspace";
import { Step4Workspace } from "@/components/step4-workspace";
import { Step45Workspace } from "@/components/step45-workspace";
import { Step5Workspace } from "@/components/step5-workspace";
import { useWorkflow } from "@/context/workflow-context";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "亚马逊 FBA 智能装箱与货件处理工具" },
      {
        name: "description",
        content: "企业级 FBA 装箱、排箱、导出、回传校验与发票一体化处理系统。",
      },
      { property: "og:title", content: "亚马逊 FBA 智能装箱与货件处理工具" },
      {
        property: "og:description",
        content: "企业级 FBA 装箱、排箱、导出、回传校验与发票一体化处理系统。",
      },
    ],
  }),
  component: Index,
});

function Index() {
  return (
    <>
      <FboxDropOverlay />
      <WorkflowApp />
    </>
  );
}

function WorkflowApp() {
  const { step, setStep, step4Ok, shipments } = useWorkflow();
  const showInvoiceSteps = step4Ok || shipments.length > 0;

  return (
    <AppShell>
      <div className={step === 1 ? "h-full" : "hidden"} aria-hidden={step !== 1}>
        <Step1Workspace onNext={() => setStep(2)} />
      </div>
      <div className={step === 2 ? "h-full" : "hidden"} aria-hidden={step !== 2}>
        <Step2Workspace onPrev={() => setStep(1)} onNext={() => setStep(3)} />
      </div>
      <div className={step === 3 ? "h-full" : "hidden"} aria-hidden={step !== 3}>
        <Step3Workspace onPrev={() => setStep(2)} onNext={() => setStep(4)} />
      </div>
      <div className={step === 3.5 ? "h-full" : "hidden"} aria-hidden={step !== 3.5}>
        <Step35RoutingWorkspace />
      </div>
      <div className={step === 4 ? "h-full" : "hidden"} aria-hidden={step !== 4}>
        <Step4Workspace onPrev={() => setStep(3)} onNext={() => setStep(4.5)} />
      </div>
      {showInvoiceSteps && (
        <>
          <div className={step === 4.5 ? "h-full" : "hidden"} aria-hidden={step !== 4.5}>
            <Step45Workspace onPrev={() => setStep(4)} onNext={() => setStep(5)} />
          </div>
          <div className={step === 5 ? "h-full" : "hidden"} aria-hidden={step !== 5}>
            <Step5Workspace onPrev={() => setStep(4.5)} />
          </div>
        </>
      )}
      {step !== 1 && step !== 2 && step !== 3 && step !== 3.5 && step !== 4 && step !== 4.5 && step !== 5 && (
        <div className="flex h-full min-h-[60vh] items-center justify-center rounded-xl border border-dashed border-border bg-card shadow-sm">
          <p className="text-sm text-muted-foreground">Step {step} 尚未实现</p>
        </div>
      )}
    </AppShell>
  );
}
