import { Link } from "@tanstack/react-router";
import { AlertTriangle } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { masterDataGapBannerText, type MasterDataGap } from "@/lib/master-data-gap";

export function MasterDataGapBanner({ gaps }: { gaps: MasterDataGap[] }) {
  const text = masterDataGapBannerText(gaps);
  if (!text) return null;
  return (
    <Alert className="border-amber-300 bg-amber-50 text-amber-950">
      <AlertTriangle className="h-4 w-4 !text-amber-600" />
      <AlertTitle className="text-sm font-semibold">主数据库未齐</AlertTitle>
      <AlertDescription className="text-xs">
        <p data-testid="master-gap-banner">{text}</p>
        <div className="mt-2 flex flex-wrap gap-2">
          <Button asChild size="sm" variant="outline">
            <Link to="/master-data" search={{ import: "product-info" }}>
              导入产品信息表
            </Link>
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link to="/master-data" hash="lingxing-sync">
              领星同步
            </Link>
          </Button>
        </div>
      </AlertDescription>
    </Alert>
  );
}
