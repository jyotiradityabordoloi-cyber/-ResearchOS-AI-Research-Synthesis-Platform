"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  BookOpenText,
  FileText,
  FolderKanban,
  LayoutDashboard,
  Lightbulb,
  Menu,
  MessagesSquare,
  Settings,
  Sparkles,
} from "lucide-react";
import { Suspense, useState } from "react";
import { cn } from "@/lib/utils";

import { api } from "@/lib/api";
import { ClientOnly } from "@/components/client-only";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/projects", label: "Research Projects", icon: FolderKanban },
  { href: "/interviews", label: "Interviews", icon: MessagesSquare },
  { href: "/insights", label: "Insights", icon: Lightbulb },
  { href: "/repository", label: "Research Repository", icon: BookOpenText },
  { href: "/reports", label: "Reports", icon: FileText },
  { href: "/settings", label: "Settings", icon: Settings },
];

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-2.5 px-2">
      <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
        <Sparkles className="size-4" />
      </span>
      <span className="text-[15px] font-semibold tracking-tight">ResearchOS</span>
    </Link>
  );
}

function ProviderPill() {
  return (
    <ClientOnly>
      <ProviderPillInner />
    </ClientOnly>
  );
}

function ProviderPillInner() {
  const { data } = useQuery({ queryKey: ["ai-settings"], queryFn: api.aiSettings, staleTime: 60_000 });
  if (!data) return null;
  const { llm } = data;
  return (
    <Link
      href="/settings"
      className="mx-2 flex items-center gap-2 rounded-lg border bg-background px-3 py-2 text-xs text-muted-foreground transition-colors hover:text-foreground"
    >
      <span
        className={cn(
          "size-2 rounded-full",
          !llm.available ? "bg-destructive" : llm.is_demo ? "bg-amber-500" : "bg-emerald-500",
        )}
      />
      <span className="truncate">
        {llm.is_demo ? "Local demo mode" : `${llm.name} · ${llm.model}`}
      </span>
    </Link>
  );
}

// usePathname() is runtime-only on dynamic routes, so it must stream inside Suspense.
function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <Suspense fallback={<NavList pathname={null} onNavigate={onNavigate} />}>
      <ActiveNavLinks onNavigate={onNavigate} />
    </Suspense>
  );
}

function ActiveNavLinks({ onNavigate }: { onNavigate?: () => void }) {
  return <NavList pathname={usePathname()} onNavigate={onNavigate} />;
}

function NavList({ pathname, onNavigate }: { pathname: string | null; onNavigate?: () => void }) {
  return (
    <nav className="flex flex-col gap-0.5">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = pathname !== null && isActive(pathname, href);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
              active
                ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
            )}
          >
            <Icon className="size-4 shrink-0" />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

export function AppSidebar() {
  return (
    <aside className="sticky top-0 hidden h-svh w-64 shrink-0 flex-col gap-6 border-r bg-sidebar px-3 py-5 lg:flex">
      <Brand />
      <NavLinks />
      <div className="mt-auto">
        <ProviderPill />
      </div>
    </aside>
  );
}

export function MobileTopBar() {
  const [open, setOpen] = useState(false);
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b bg-background/90 px-4 backdrop-blur lg:hidden">
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger asChild>
          <Button variant="ghost" size="icon" aria-label="Open navigation">
            <Menu className="size-5" />
          </Button>
        </SheetTrigger>
        <SheetContent side="left" className="w-72 gap-6 bg-sidebar px-3 py-5">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <Brand />
          <NavLinks onNavigate={() => setOpen(false)} />
          <div className="mt-auto">
            <ProviderPill />
          </div>
        </SheetContent>
      </Sheet>
      <Brand />
    </header>
  );
}
