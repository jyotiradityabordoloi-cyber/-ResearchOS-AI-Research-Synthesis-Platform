import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { AppSidebar, MobileTopBar } from "@/components/app-sidebar";
import { ClientOnly } from "@/components/client-only";
import { Copilot } from "@/components/copilot/copilot";
import { Providers } from "@/components/providers";
import { Skeleton } from "@/components/ui/skeleton";

function PageSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <Skeleton className="h-8 w-56" />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-28 rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-72 rounded-xl" />
    </div>
  );
}

const geistSans = Geist({ variable: "--font-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "ResearchOS", template: "%s · ResearchOS" },
  description: "AI-assisted user research synthesis for small product teams.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full bg-background antialiased [color-scheme:light]`}
    >
      <body className="min-h-full bg-background">
        <Providers>
          <div className="flex min-h-svh bg-muted/30">
            <AppSidebar />
            <div className="flex min-w-0 flex-1 flex-col">
              <MobileTopBar />
              <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
                <ClientOnly fallback={<PageSkeleton />}>{children}</ClientOnly>
              </main>
            </div>
          </div>
          <ClientOnly>
            <Copilot />
          </ClientOnly>
        </Providers>
      </body>
    </html>
  );
}
