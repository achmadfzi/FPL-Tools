export const TEAM_COLORS: Record<string, string> = {
  ARS: "#EF0107",
  AVL: "#670E36",
  BOU: "#DA291C",
  BRE: "#e30613",
  BHA: "#0057B8",
  CHE: "#034694",
  CRY: "#1B458F",
  EVE: "#003399",
  FUL: "#111827",
  IPS: "#0000FF",
  LEE: "#1D428A",
  LIV: "#C8102E",
  MCI: "#6CABDD",
  MUN: "#DA291C",
  NEW: "#241F20",
  NFO: "#DD0000",
  SUN: "#EB172B",
  TOT: "#132257",
  WHU: "#7A263A",
  WOL: "#FDB913",
  COV: "#0092D4",
  HUL: "#F5A12D",
};

export function teamColor(team?: string | null) {
  return TEAM_COLORS[team ?? ""] ?? "#37003c";
}
