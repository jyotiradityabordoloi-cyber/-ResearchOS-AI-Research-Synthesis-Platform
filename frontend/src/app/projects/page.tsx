import type { Metadata } from "next";

import { ProjectsView } from "@/components/views/projects-view";

export const metadata: Metadata = { title: "Research projects" };

export default function Page() {
  return <ProjectsView />;
}
