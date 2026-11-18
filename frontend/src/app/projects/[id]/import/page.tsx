import type { Metadata } from "next";
import { Suspense } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { ImportView } from "@/components/views/import-view";

export const metadata: Metadata = { title: "Import interviews" };

// Content is fetched client-side from the API (see ClientOnly in the root layout).
export const instant = false;

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <ImportView />
    </Suspense>
  );
}
