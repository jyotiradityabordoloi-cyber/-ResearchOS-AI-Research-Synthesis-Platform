import type { Metadata } from "next";

import { RepositoryView } from "@/components/views/repository-view";

export const metadata: Metadata = { title: "Research repository" };

export default function Page() {
  return <RepositoryView />;
}
