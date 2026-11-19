import type { Metadata } from "next";

import { InterviewsView } from "@/components/views/interviews-view";

export const metadata: Metadata = { title: "Interview explorer" };

export default function Page() {
  return <InterviewsView />;
}
