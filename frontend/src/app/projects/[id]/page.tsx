import { Suspense } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { ProjectDetailView } from "@/components/views/project-detail-view";

// Content is fetched client-side from the API (see ClientOnly in the root layout),
// so there is no server-rendered segment for instant-navigation validation to check.
export const instant = false;

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-64 w-full" />}>
      <ProjectDetailView />
    </Suspense>
  );
}
