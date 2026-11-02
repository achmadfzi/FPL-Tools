import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatPrice(tenths?: number | null) {
  if (tenths === null || tenths === undefined) return "-";
  return `£${(tenths / 10).toFixed(1)}m`;
}

export function formatNumber(value?: number | null, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return value.toFixed(digits);
}

export function formatPct(value?: number | null, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${(value * 100).toFixed(digits)}%`;
}

// Official FPL fixture difficulty (FDR) palette, taken from the FPL site's
// design tokens (--ism-color-difficulty-*).
const FDR_PALETTE: Record<number, { bg: string; fg: string }> = {
  1: { bg: "#375523", fg: "#ffffff" },
  2: { bg: "#01fc7a", fg: "#37003c" },
  3: { bg: "#e7e7e7", fg: "#37003c" },
  4: { bg: "#ff1b54", fg: "#37003c" },
  5: { bg: "#80072d", fg: "#ffffff" },
};

/** Inline style for an FDR badge/cell using the official FPL colours. */
export function fdrStyle(fdr?: number | null) {
  const palette = fdr !== null && fdr !== undefined ? FDR_PALETTE[fdr] : undefined;
  if (!palette) return { backgroundColor: "#f1f5f9", color: "#64748b" };
  return { backgroundColor: palette.bg, color: palette.fg };
}

export function formatDate(iso?: string | null) {
  if (!iso) return "-";
  try {
    return new Intl.DateTimeFormat("id-ID", {
      weekday: "long",
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "Asia/Jakarta",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function relativeTime(unix?: number | null) {
  if (!unix) return "-";
  const seconds = Math.max(0, Math.floor(Date.now() / 1000 - unix));
  if (seconds < 60) return `${seconds} detik lalu`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} menit lalu`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} jam lalu`;
  return `${Math.floor(hours / 24)} hari lalu`;
}
