import type { Metadata } from "next";

import { InsightsView } from "@/components/views/insights-view";

export const metadata: Metadata = { title: "Insight review" };

export default function Page() {
  return <InsightsView />;
}
