"use client";

import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";

import { TooltipProvider } from "@/components/ui/tooltip";

let browserQueryClient: QueryClient | undefined;

function makeClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { staleTime: 10_000, retry: 1, refetchOnWindowFocus: false },
    },
  });
}

function getQueryClient() {
  if (typeof window === "undefined") return makeClient();
  browserQueryClient ??= makeClient();
  return browserQueryClient;
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={getQueryClient()}>
      <TooltipProvider delayDuration={200}>
        {children}
        {/* Raised so toasts never cover the copilot launcher in the same corner. */}
        <Toaster position="bottom-right" richColors closeButton offset={{ bottom: 76, right: 20 }} mobileOffset={{ bottom: 76 }} />
      </TooltipProvider>
    </QueryClientProvider>
  );
}
