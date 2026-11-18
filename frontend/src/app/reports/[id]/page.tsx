import type { Metadata } from "next";
import { Suspense } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { ReportView } from "@/components/views/report-view";

export const metadata: Metadata = { title: "Report" };

// Content is fetched client-side from the API (see ClientOnly in the root layout).
export const instant = false;

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-[70svh] w-full" />}>
      <ReportView />
    </Suspense>
  );
}
