import type { LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { teamColor } from "@/lib/teams";
import type { Confidence } from "@/lib/types";

export function ConfidenceBadge({ level }: { level?: Confidence | string | null }) {
  const value = level ?? "Sedang";
  const variant =
    value === "Tinggi" ? "success" : value === "Rendah" ? "destructive" : "warning";
  return (
    <Badge variant={variant as any} className="gap-1">
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />
      Keyakinan: {value}
    </Badge>
  );
}

export function TeamBadge({ team, className }: { team?: string | null; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-6 min-w-8 items-center justify-center rounded-md px-1.5 text-[10px] font-bold text-white",
        className,
      )}
      style={{ backgroundColor: teamColor(team) }}
      title={team ?? ""}
    >
      {team ?? "—"}
    </span>
  );
}

function _hexToRgb(hex: string) {
  const raw = hex.replace("#", "");
  const normalized = raw.length === 3 ? raw.split("").map((c) => c + c).join("") : raw;
  const n = parseInt(normalized, 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

function _isLight(hex: string) {
  const { r, g, b } = _hexToRgb(hex);
  // Relative luminance, good enough for choosing dark/light trim.
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 > 0.62;
}

export function Jersey({
  name,
  team,
  size = "md",
  className,
}: {
  name?: string;
  team?: string;
  size?: "xs" | "sm" | "md" | "lg" | "pitch";
  className?: string;
}) {
  const initials = (name ?? "?")
    .split(" ")
    .filter(Boolean)
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  const primary = teamColor(team);
  const trim = _isLight(primary) ? "#0f172a" : "#ffffff";
  const dims = {
    xs: "h-7 w-6",
    sm: "h-9 w-8",
    md: "h-11 w-10",
    lg: "h-16 w-14",
    // Larger, responsive jersey used on the pitch.
    pitch: "h-10 w-9 sm:h-14 sm:w-12",
  }[size];
  const textSize = { xs: 22, sm: 20, md: 18, lg: 16, pitch: 18 }[size];

  return (
    <span className={cn("inline-flex shrink-0 items-center justify-center drop-shadow-sm", dims, className)} title={`${name ?? ""} · ${team ?? ""}`}>
      <svg viewBox="0 0 100 120" className="h-full w-full" aria-label={`${name ?? "Pemain"} jersey ${team ?? ""}`}>
        <path
          d="M30 10 L8 36 L24 48 L24 112 L76 112 L76 48 L92 36 L70 10 C60 22 40 22 30 10 Z"
          fill={primary}
          stroke={trim}
          strokeWidth="4"
          strokeLinejoin="round"
        />
        <path d="M30 10 L8 36 L24 48 L30 26 Z" fill={trim} opacity="0.18" />
        <path d="M70 10 L92 36 L76 48 L70 26 Z" fill={trim} opacity="0.18" />
        <path d="M36 12 Q50 25 64 12" fill="none" stroke={trim} strokeWidth="4" strokeLinecap="round" />
        <text
          x="50"
          y="78"
          textAnchor="middle"
          fontSize={textSize}
          fontWeight="700"
          fill={trim}
          fontFamily="Inter, sans-serif"
        >
          {initials}
        </text>
      </svg>
    </span>
  );
}

export function PlayerAvatar({ name, team, size = "md" }: { name?: string; team?: string; size?: "sm" | "md" | "lg" }) {
  return <Jersey name={name} team={team} size={size} />;
}

export function PageHeader({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 pb-2 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1>
        {description ? <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {children ? <div className="flex flex-wrap items-center gap-2">{children}</div> : null}
    </div>
  );
}

export function MetricCard({
  label,
  value,
  hint,
  icon: Icon,
  accent = "primary",
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  icon?: LucideIcon;
  accent?: "primary" | "success" | "warning" | "destructive" | "muted";
}) {
  const accentClass = {
    primary: "bg-primary/10 text-primary",
    success: "bg-emerald-100 text-emerald-700",
    warning: "bg-amber-100 text-amber-700",
    destructive: "bg-red-100 text-red-700",
    muted: "bg-muted text-muted-foreground",
  }[accent];
  return (
    <Card className="animate-fade-in">
      <CardContent className="flex items-start justify-between gap-3 p-5">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
          <div className="mt-1 text-2xl font-bold tracking-tight">{value}</div>
          {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
        </div>
        {Icon ? (
          <div className={cn("rounded-lg p-2", accentClass)}>
            <Icon className="h-5 w-5" />
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function ActionCard({
  title,
  icon: Icon,
  headline,
  metric,
  metricLabel,
  meaning,
  confidence,
  tone = "info",
  footer,
  actionLabel,
  onAction,
}: {
  title: string;
  icon: LucideIcon;
  headline: string;
  metric?: string;
  metricLabel?: string;
  meaning: string;
  confidence?: Confidence | string | null;
  tone?: "good" | "warn" | "bad" | "info";
  footer?: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  const border = {
    good: "border-l-emerald-500",
    warn: "border-l-amber-500",
    bad: "border-l-red-500",
    info: "border-l-primary",
  }[tone];
  const iconBg = {
    good: "bg-emerald-100 text-emerald-700",
    warn: "bg-amber-100 text-amber-700",
    bad: "bg-red-100 text-red-700",
    info: "bg-primary/10 text-primary",
  }[tone];
  return (
    <Card className={cn("h-full animate-fade-in border-l-4", border)}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className={cn("rounded-lg p-2", iconBg)}>
              <Icon className="h-4 w-4" />
            </div>
            <CardTitle className="text-sm uppercase tracking-wide text-muted-foreground">{title}</CardTitle>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex h-[calc(100%-4.5rem)] flex-col">
        <div className="text-lg font-bold leading-tight">{headline}</div>
        {metric ? (
          <div className="mt-1 text-3xl font-extrabold tracking-tight text-primary">
            {metric} {metricLabel ? <span className="text-xs font-medium text-muted-foreground">{metricLabel}</span> : null}
          </div>
        ) : null}
        <p className="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">{meaning}</p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <ConfidenceBadge level={confidence} />
        </div>
        {actionLabel ? (
          <Button variant="outline" size="sm" className="mt-3 w-full" onClick={onAction}>
            {actionLabel}
          </Button>
        ) : null}
        {footer ? <p className="mt-2 text-[11px] text-muted-foreground">{footer}</p> : null}
      </CardContent>
    </Card>
  );
}

export function SectionTitle({ title, description, action }: { title: string; description?: string; action?: React.ReactNode }) {
  return (
    <div className="mb-3 flex items-end justify-between gap-3">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
        {description ? <p className="mt-0.5 text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center justify-center gap-2 py-12 text-center">
        <div className="text-sm font-semibold">{title}</div>
        {description ? <p className="max-w-md text-sm text-muted-foreground">{description}</p> : null}
      </CardContent>
    </Card>
  );
}
