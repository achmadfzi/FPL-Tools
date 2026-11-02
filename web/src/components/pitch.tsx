import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Jersey, PlayerAvatar, TeamBadge } from "@/components/shared";
import { fdrStyle, formatNumber, formatPct } from "@/lib/utils";
import type { XiPlayer } from "@/lib/types";

// GK at the top, attackers at the bottom (reverse of the old orientation).
const ORDER = ["GK", "DEF", "MID", "FWD"] as const;

function PlayerChip({
  player,
  captainId,
  viceName,
}: {
  player: XiPlayer;
  captainId?: number | null;
  viceName?: string | null;
}) {
  const isCaptain = player.id === captainId;
  const isVice = player.name === viceName;
  const fixtures = (player.next_fixtures ?? []).slice(0, 3);
  return (
    <div className="flex w-[70px] flex-col items-center gap-0.5 sm:w-[94px] sm:gap-1">
      <div className="relative">
        <Jersey name={player.name} team={player.team} size="pitch" />
        {isCaptain ? (
          <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[9px] font-bold text-primary-foreground shadow sm:h-5 sm:w-5 sm:text-[10px]">
            C
          </span>
        ) : null}
        {isVice ? (
          <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-amber-500 text-[9px] font-bold text-white shadow sm:h-5 sm:w-5 sm:text-[10px]">
            V
          </span>
        ) : null}
      </div>
      <div
        className="w-full rounded-md bg-white/95 px-1 py-1 text-center shadow-sm"
        title={`${player.name} · ${formatNumber(player.proj)} poin · main ${formatPct(player.p_play)} · ${fixtures.map((f) => `${f.opponent} FDR ${f.fdr}`).join(" · ")}`}
      >
        <div className="truncate text-[8px] font-bold leading-tight text-slate-900 sm:text-[9px]">{player.name}</div>
        <div className="mt-0.5 flex items-center justify-center gap-0.5 text-[7px] sm:gap-1 sm:text-[8px]">
          <TeamBadge team={player.team} className="h-3 min-w-5 px-0.5 text-[7px] sm:h-3.5 sm:min-w-6 sm:text-[8px]" />
          <span className="font-semibold text-primary">{formatNumber(player.proj)}</span>
          <span className="text-slate-500">{formatPct(player.p_play)}</span>
        </div>
        <div className="mt-1 grid grid-cols-3 gap-[2px]">
          {fixtures.map((f) => (
            <div
              key={`${f.event}-${f.opponent}`}
              className="rounded-[2px] py-[1px] leading-tight"
              style={fdrStyle(f.fdr)}
              title={`GW${f.event} vs ${f.opponent} · FDR ${f.fdr ?? "-"}`}
            >
              <div className="truncate text-[6px] font-semibold sm:text-[7px]">{f.opponent}</div>
              <div className="text-[6px] font-bold sm:text-[7px]">{f.fdr ?? "-"}</div>
            </div>
          ))}
          {fixtures.length < 3
            ? Array.from({ length: 3 - fixtures.length }).map((_, i) => (
                <div key={`empty-${i}`} className="rounded-[2px] bg-slate-100 py-[1px] text-[6px] text-slate-400">
                  -
                </div>
              ))
            : null}
        </div>
      </div>
    </div>
  );
}

function Row({
  players,
  captainId,
  viceName,
}: {
  players: XiPlayer[];
  captainId?: number | null;
  viceName?: string | null;
}) {
  return (
    <div className="flex items-start justify-around gap-0.5 sm:gap-2">
      {players.map((p) => (
        <PlayerChip key={p.id} player={p} captainId={captainId} viceName={viceName} />
      ))}
    </div>
  );
}

export function Pitch({
  xi,
  bench,
  captainId,
  viceName,
  formation,
  ev,
  title = "Pitch XI",
}: {
  xi: XiPlayer[];
  bench?: XiPlayer[];
  captainId?: number | null;
  viceName?: string | null;
  formation?: number[];
  ev?: number;
  title?: string;
}) {
  const groups = ORDER.reduce<Record<string, XiPlayer[]>>((acc, pos) => {
    acc[pos] = xi.filter((p) => p.pos === pos);
    return acc;
  }, {});

  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex-row items-center justify-between space-y-0 p-3 pb-1 sm:p-5 sm:pb-2">
        <div>
          <CardTitle className="text-sm sm:text-base">{title}</CardTitle>
          <p className="mt-0.5 text-[11px] text-muted-foreground sm:mt-1 sm:text-sm">
            Formasi {formation?.join("-") ?? "-"} · EV {formatNumber(ev)}
          </p>
        </div>
        <Badge variant="success">Auto XI</Badge>
      </CardHeader>
      <CardContent className="p-2 sm:p-4">
        <div className="mx-auto w-full max-w-3xl">
          <div className="relative overflow-hidden rounded-xl border-2 border-emerald-950/20 bg-emerald-700 p-1.5 shadow-inner sm:rounded-2xl sm:border-4 sm:p-3">
            <div
              className="pointer-events-none absolute inset-0 opacity-25"
              style={{
                backgroundImage:
                  "repeating-linear-gradient(0deg, transparent, transparent 30px, rgba(255,255,255,.10) 30px, rgba(255,255,255,.10) 60px)",
              }}
            />
            <div className="pointer-events-none absolute left-1/2 top-1/2 h-12 w-12 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white/35 sm:h-20 sm:w-20" />
            <div className="pointer-events-none absolute left-1/2 top-0 h-10 w-24 -translate-x-1/2 border-x-2 border-b-2 border-white/35 sm:h-16 sm:w-44" />
            <div className="pointer-events-none absolute bottom-0 left-1/2 h-10 w-24 -translate-x-1/2 border-x-2 border-t-2 border-white/35 sm:h-16 sm:w-44" />
            <div className="relative z-10 flex min-h-[340px] flex-col justify-between gap-1 py-2 sm:min-h-[480px] sm:gap-2 sm:py-4">
              {ORDER.map((pos) => (
                <Row key={pos} players={groups[pos] ?? []} captainId={captainId} viceName={viceName} />
              ))}
            </div>
          </div>

          <p className="mt-2 text-[10px] text-muted-foreground">
            Kotak kecil = 3 laga berikutnya (lawan + FDR). Hijau = mudah, merah = sulit.
          </p>

          {bench?.length ? (
            <div className="mt-3">
              <div className="mb-1.5 flex items-center justify-between">
                <span className="text-xs font-semibold sm:text-sm">Bench</span>
                <span className="text-[10px] text-muted-foreground">Auto-sub 1 → 2 → 3 · GK slot 4</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {bench.map((p) => (
                  <div key={p.id} className="flex items-center gap-1.5 rounded-md border bg-card px-1.5 py-1">
                    <PlayerAvatar name={p.name} team={p.team} size="sm" />
                    <div>
                      <div className="text-[10px] font-semibold sm:text-xs">{p.name}</div>
                      <div className="text-[9px] text-muted-foreground sm:text-[10px]">
                        {p.bench_slot ?? "-"} · {formatNumber(p.proj)} poin · {formatPct(p.p_play)} main
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
