import { useEffect, useMemo, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  BookOpen,
  ChevronDown,
  ClipboardList,
  FlaskConical,
  History,
  Home,
  LineChart,
  Menu,
  RefreshCw,
  Search,
  Target,
  Trophy,
  Users,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Progress, Separator } from "@/components/ui/primitives";
import { useDashboard, useRefresh } from "@/lib/api";
import { cn, formatDate, relativeTime } from "@/lib/utils";
import type { Dashboard } from "@/lib/types";

const MAIN_NAV = [
  { to: "/", label: "Minggu Ini", icon: Home },
  { to: "/squad", label: "Skuad Saya", icon: Users },
  { to: "/players", label: "Cari Pemain", icon: Search },
  { to: "/performance", label: "Performa", icon: LineChart },
  { to: "/lab", label: "Lab & Chip", icon: FlaskConical },
];

const MORE_NAV = [
  { to: "/detail", label: "Rencana Detail", icon: ClipboardList },
  { to: "/captain", label: "Kapten & Transfer", icon: Target },
  { to: "/history", label: "Riwayat GW", icon: History },
  { to: "/glossary", label: "Kamus FPL", icon: BookOpen },
];

function useMode() {
  const [mode, setMode] = useState<"Pemula" | "Analis">(() => {
    return (localStorage.getItem("fpl-ui-mode-v3") as "Pemula" | "Analis") || "Analis";
  });
  useEffect(() => {
    localStorage.setItem("fpl-ui-mode-v3", mode);
  }, [mode]);
  return { mode, setMode, isBeginner: mode === "Pemula" };
}

function Countdown({ deadline }: { deadline?: string }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(t);
  }, []);
  const diff = deadline ? new Date(deadline).getTime() - now : 0;
  if (!deadline || diff <= 0) return <Badge variant="outline">Deadline lewat</Badge>;
  const days = Math.floor(diff / 86_400_000);
  const hours = Math.floor((diff % 86_400_000) / 3_600_000);
  const mins = Math.floor((diff % 3_600_000) / 60_000);
  return (
    <Badge variant="secondary" className="gap-1 font-mono">
      ⏳ {days}h {hours}j {mins}m
    </Badge>
  );
}

export function AppShell({
  children,
  mode,
  setMode,
}: {
  children: React.ReactNode;
  mode: "Pemula" | "Analis";
  setMode: (m: "Pemula" | "Analis") => void;
}) {
  const { data } = useDashboard();
  const refresh = useRefresh();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  const title = useMemo(() => {
    const all = [...MAIN_NAV, ...MORE_NAV];
    return all.find((n) => n.to === location.pathname)?.label ?? "Minggu Ini";
  }, [location.pathname]);

  const sidebar = (
    <div className="flex h-full flex-col gap-4 p-4">
      <div className="flex items-center gap-3 px-1">
        <div className="fpl-gradient flex h-10 w-10 items-center justify-center rounded-xl text-white shadow-sm">
          <Trophy className="h-5 w-5" />
        </div>
        <div>
          <div className="text-sm font-extrabold tracking-tight">FPL HQ</div>
          <div className="text-[11px] text-muted-foreground">Dashboard keputusan</div>
        </div>
      </div>

      <nav className="space-y-1">
        {MAIN_NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
              )
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>

      <button
        onClick={() => setMoreOpen((v) => !v)}
        className="flex items-center justify-between rounded-lg px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground hover:bg-accent"
      >
        Lainnya
        <ChevronDown className={cn("h-4 w-4 transition-transform", moreOpen && "rotate-180")} />
      </button>
      {moreOpen ? (
        <nav className="space-y-1">
          {MORE_NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-accent text-accent-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                )
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>
      ) : null}

      <div className="mt-auto space-y-3">
        <Card className="p-3">
          <div className="mb-2 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">Tampilan</div>
          <div className="grid grid-cols-2 gap-1 rounded-lg bg-muted p-1">
            {(["Pemula", "Analis"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={cn(
                  "rounded-md px-2 py-1.5 text-xs font-semibold transition-colors",
                  mode === m ? "bg-background text-foreground shadow-sm" : "text-muted-foreground",
                )}
              >
                {m}
              </button>
            ))}
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
            {mode === "Pemula"
              ? "Keputusan + alasan singkat. Angka teknis disembunyikan."
              : "Semua metrik: EV, p10–p90, xGI, DefCon, MAE."}
          </p>
        </Card>

        {data ? (
          <Card className="p-3">
            <div className="truncate text-sm font-bold">{data.squad.source}</div>
            <div className="mt-1 grid grid-cols-2 gap-1 text-[11px] text-muted-foreground">
              <span>Bank</span>
              <span className="text-right font-medium text-foreground">£{data.squad.bank.toFixed(1)}m</span>
              <span>FT</span>
              <span className="text-right font-medium text-foreground">{data.squad.free_transfers}</span>
            </div>
            <Separator className="my-2" />
            <div className="flex items-center justify-between text-[11px] text-muted-foreground">
              <span>Data</span>
              <span>{relativeTime(data.updated_at)}</span>
            </div>
          </Card>
        ) : null}
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-background">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 border-r bg-card lg:block">{sidebar}</aside>

      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 bg-card shadow-xl">
            <div className="flex justify-end p-2">
              <Button variant="ghost" size="icon" onClick={() => setMobileOpen(false)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
            {sidebar}
          </aside>
        </div>
      ) : null}

      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 border-b bg-background/85 backdrop-blur">
          <div className="flex h-16 items-center gap-3 px-4 sm:px-6">
            <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileOpen(true)}>
              <Menu className="h-5 w-5" />
            </Button>
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold">{title}</div>
              <div className="truncate text-[11px] text-muted-foreground">
                {data ? `GW ${data.gw.id} · ${formatDate(data.gw.deadline)}` : "Memuat..."}
              </div>
            </div>
            <div className="ml-auto flex shrink-0 items-center gap-2">
              {data ? (
                <div className="hidden sm:block">
                  <Countdown deadline={data.gw.deadline} />
                </div>
              ) : null}
              <Button
                variant="outline"
                size="sm"
                className="px-2 sm:px-4"
                onClick={() => refresh.mutate()}
                disabled={refresh.isPending}
              >
                <RefreshCw className={cn("h-4 w-4 sm:mr-2", refresh.isPending && "animate-spin")} />
                <span className="hidden sm:inline">Segarkan</span>
              </Button>
            </div>
          </div>
        </header>

        <main className="mx-auto min-w-0 max-w-7xl px-4 py-6 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}

export { useMode };
