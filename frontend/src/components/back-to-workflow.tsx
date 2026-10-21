import { useNavigate } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useWorkflow } from "@/context/workflow-context";
import { readReturnStep } from "@/lib/return-step";
import { cn } from "@/lib/utils";

export function BackToWorkflow({ className }: { className?: string }) {
  const navigate = useNavigate();
  const { setStep } = useWorkflow();

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      className={cn("gap-1.5", className)}
      data-testid="back-to-workflow"
      onClick={() => {
        const saved = readReturnStep();
        void navigate({ to: "/" }).then(() => {
          if (saved != null) setStep(saved);
        });
      }}
    >
      <ArrowLeft className="h-4 w-4" />
      返回工作流
    </Button>
  );
}
