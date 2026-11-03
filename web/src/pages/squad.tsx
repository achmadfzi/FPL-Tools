import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, Check, ChevronDown, ChevronUp, Crown, Plus, Save, Search, Trash2, Users } from "lucide-react";
import { Alert } from "@/components/ui/primitives";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/primitives";
import { useDashboard, usePlayers, useSquadInsights, useSquadMutation } from "@/lib/api";
import { cn, formatNumber, formatPrice } from "@/lib/utils";
import { PlayerAvatar, PageHeader, SectionTitle, TeamBadge } from "@/components/shared";
import { Pitch } from "@/components/pitch";
import type { Player } from "@/lib/types";

const NEED: Record<string, number> = { GK: 2, DEF: 5, MID: 5, FWD: 3 };

export default function SquadPage({ isBeginner }: { isBeginner: boolean }) {
  const { data: dashboard, isLoading: dashLoading } = useDashboard();
  const { data: players, isLoading: playersLoading } = usePlayers();
  const { data: insights } = useSquadInsights();
  const mutation = useSquadMutation();
  const [ids, setIds] = useState<number[]>([]);
  const [query, setQuery] = useState("");
  const [pos, setPos] = useState("ALL");
  const [showSquad, setShowSquad] = useState(false);
  const [showAdd, setShowAdd] = useState(false);

  useEffect(() => {
    if (dashboard && ids.length === 0) setIds(dashboard.squad.ids);
  }, [dashboard, ids.length]);

  const byId = useMemo(() => new Map((players ?? []).map((p) => [p.id, p])), [players]);
  const selected = ids.map((id) => byId.get(id)).filter(Boolean) as Player[];
  const cost = selected.reduce((sum, p) => sum + (p.price ?? 0), 0);
  const budget = Math.max(1000, Math.round(((dashboard?.squad.team_value ?? 100) + (dashboard?.squad.bank ?? 0)) * 10));
  const xiProjection = (dashboard?.xi ?? []).reduce((sum, p) => sum + (p.proj ?? 0), 0);
  const captainProjection = dashboard?.captain?.proj ?? 0;
  const predictedXi = xiProjection + captainProjection; // captain gets 2x
  const benchProjection = (dashboard?.bench ?? []).reduce((sum, p) => sum + (p.proj ?? 0), 0);
  const counts = selected.reduce<Record<string, number>>((acc, p) => ({ ...acc, [p.pos]: (acc[p.pos] ?? 0) + 1 }), {});
  const clubCounts = selected.reduce<Record<string, number>>((acc, p) => ({ ...acc, [p.team]: (acc[p.team] ?? 0) + 1 }), {});
  const overClub = Object.values(clubCounts).some((n) => n > 3);
  const validCounts = Object.entries(NEED).every(([p, n]) => (counts[p] ?? 0) === n);
  const valid = selected.length === 15 && validCounts && cost <= budget && !overClub;

  const candidates = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (players ?? [])
      .filter((p) => !ids.includes(p.id))
      .filter((p) => (pos === "ALL" ? true : p.pos === pos))
      .filter((p) => (!q ? true : p.name.toLowerCase().includes(q) || p.team.toLowerCase().includes(q)))
      .slice(0, 40);
  }, [players, ids, query, pos]);

  if (dashLoading || playersLoading) {
    return <div className="py-20 text-center text-sm text-muted-foreground">Memuat skuad...</div>;
  }
  if (!dashboard) return null;

  const add = (p: Player) => {
    if (ids.includes(p.id)) return;
    if ((counts[p.pos] ?? 0) >= NEED[p.pos]) return;
    if ((clubCounts[p.team] ?? 0) >= 3) return;
    if (cost + p.price > budget) return;
    setIds([...ids, p.id]);
  };
  const remove = (id: number) => setIds(ids.filter((x) => x !== id));

  return (
    <div className="space-y-6">
      <PageHeader title="Skuad Saya" description="Susun 15 pemain, cek budget dan kuota, lalu simpan.">
        <Button asChild variant="outline" size="sm">
          <Link to="/captain"><Crown className="mr-2 h-4 w-4" /> Kapten & Transfer</Link>
        </Button>
      </PageHeader>

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-5">
        <Card className="border-primary/30 bg-primary/5 p-3 sm:p-4">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground sm:text-xs">Prediksi skor XI</div>
          <div className="mt-1 text-xl font-bold text-primary sm:text-2xl">{formatNumber(predictedXi)}</div>
          <div className="text-[10px] text-muted-foreground sm:text-xs">
            termasuk kapten ×2 · bench {formatNumber(benchProjection)} poin
          </div>
        </Card>
        <Card className="p-3 sm:p-4">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground sm:text-xs">Budget terpakai</div>
          <div className="mt-1 text-xl font-bold sm:text-2xl">£{(cost / 10).toFixed(1)}m</div>
          <div className="text-[10px] text-muted-foreground sm:text-xs">dari £{(budget / 10).toFixed(1)}m · sisa £{((budget - cost) / 10).toFixed(1)}m</div>
        </Card>
        <Card className="p-3 sm:p-4">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground sm:text-xs">Pemain</div>
          <div className="mt-1 text-xl font-bold sm:text-2xl">{selected.length}/15</div>
          <div className="text-[10px] text-muted-foreground sm:text-xs">2 GK · 5 DEF · 5 MID · 3 FWD</div>
        </Card>
        <Card className="p-3 sm:p-4">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground sm:text-xs">Free transfer</div>
          <div className="mt-1 text-xl font-bold sm:text-2xl">{dashboard.squad.free_transfers}</div>
          <div className="text-[10px] text-muted-foreground sm:text-xs">Bank £{dashboard.squad.bank.toFixed(1)}m</div>
        </Card>
        <Card className="p-3 sm:p-4">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground sm:text-xs">Status</div>
          <div className="mt-1 text-xl font-bold sm:text-2xl">{valid ? "Siap" : "Belum valid"}</div>
          <div className="text-[10px] text-muted-foreground sm:text-xs">{overClub ? "Maks 3 pemain per klub" : validCounts ? "Kuota posisi OK" : "Lengkapi kuota posisi"}</div>
        </Card>
      </div>

      <Pitch
        xi={dashboard.xi}
        bench={dashboard.bench}
        captainId={dashboard.captain.id}
        viceName={dashboard.captain.vice}
        formation={dashboard.line.formation}
        ev={dashboard.line.ev}
        title="Pitch XI — rekomendasi tersimpan"
      />

      <div className={cn("grid gap-4", showSquad && showAdd ? "lg:grid-cols-5" : "lg:grid-cols-1")}>
        <Card className={cn(showSquad && showAdd && "lg:col-span-3")}>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="flex items-center gap-2">
                15 pemain
                <Badge variant="secondary">{selected.length}/15</Badge>
              </CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">
                {showSquad ? "Klik × untuk mengeluarkan pemain." : "Diringkas — klik panah untuk membuka."}
              </p>
            </div>
            <div className="flex items-center gap-1">
              <Button size="sm" disabled={!valid || mutation.isPending} onClick={() => mutation.mutate({ ids, budget })}>
                {mutation.isPending ? "Menyimpan..." : <><Save className="mr-2 h-4 w-4" /> Simpan Tim</>}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setShowSquad((v) => !v)}
                aria-label={showSquad ? "Minimize 15 pemain" : "Buka 15 pemain"}
                title={showSquad ? "Minimize" : "Buka"}
              >
                {showSquad ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </Button>
            </div>
          </CardHeader>
          {showSquad ? <CardContent className="space-y-4">
            {(["GK", "DEF", "MID", "FWD"] as const).map((position) => (
              <div key={position}>
                <div className="mb-2 flex items-center justify-between">
                  <div className="text-sm font-semibold">{position}</div>
                  <div className="text-xs text-muted-foreground">{(counts[position] ?? 0)}/{NEED[position]}</div>
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  {(selected.filter((p) => p.pos === position)).map((p) => (
                    <div key={p.id} className="flex items-center gap-2 rounded-lg border p-2">
                      <PlayerAvatar name={p.name} team={p.team} size="sm" />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5 text-sm font-medium">
                          <span
                            className={cn(
                              "h-1.5 w-1.5 shrink-0 rounded-full",
                              p.status === "a" ? "bg-emerald-500" : p.status === "d" ? "bg-amber-500" : "bg-red-500",
                            )}
                            title={p.status === "a" ? "Tersedia" : p.status === "d" ? "Diragukan" : "Tidak tersedia"}
                          />
                          <span className="truncate">{p.name}</span>
                        </div>
                        <div className="flex flex-wrap items-center gap-1 text-[11px] text-muted-foreground">
                          <TeamBadge team={p.team} /> {formatPrice(p.price)} · {formatNumber(p.proj)} poin ·{" "}
                          {formatNumber(p.chance, 0)}% main · {p.opponent ?? "-"} FDR {p.fdr ?? "-"}
                        </div>
                      </div>
                      <Button variant="ghost" size="icon" onClick={() => remove(p.id)} aria-label={`Hapus ${p.name}`}>
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  ))}
                  {Array.from({ length: Math.max(0, NEED[position] - (counts[position] ?? 0)) }).map((_, i) => (
                    <div key={`empty-${position}-${i}`} className="flex h-[58px] items-center justify-center rounded-lg border border-dashed text-xs text-muted-foreground">
                      Slot kosong
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </CardContent> : null}
        </Card>

        <Card className={cn(showSquad && showAdd && "lg:col-span-2")}>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="flex items-center gap-2">
                Tambah pemain
                <Badge variant="secondary">{candidates.length}</Badge>
              </CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">
                {showAdd ? "Cari lalu klik +. Kuota dan budget otomatis dicek." : "Diringkas — klik panah untuk membuka."}
              </p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setShowAdd((v) => !v)}
              aria-label={showAdd ? "Minimize tambah pemain" : "Buka tambah pemain"}
              title={showAdd ? "Minimize" : "Buka"}
            >
              {showAdd ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </Button>
          </CardHeader>
          {showAdd ? <CardContent className="space-y-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Cari nama / tim..." className="pl-9" />
            </div>
            <Select value={pos} onChange={(e) => setPos(e.target.value)}>
              <option value="ALL">Semua posisi</option>
              {["GK", "DEF", "MID", "FWD"].map((p) => <option key={p}>{p}</option>)}
            </Select>
            <div className="max-h-[520px] space-y-2 overflow-auto pr-1">
              {candidates.map((p) => {
                const disabled =
                  (counts[p.pos] ?? 0) >= NEED[p.pos] ||
                  (clubCounts[p.team] ?? 0) >= 3 ||
                  cost + p.price > budget ||
                  Boolean(p.availability?.is_out);
                return (
                  <div key={p.id} className="flex items-center gap-2 rounded-lg border p-2">
                    <PlayerAvatar name={p.name} team={p.team} size="sm" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 text-sm font-medium">
                        <span
                          className={cn(
                            "h-1.5 w-1.5 shrink-0 rounded-full",
                            p.status === "a" ? "bg-emerald-500" : p.status === "d" ? "bg-amber-500" : "bg-red-500",
                          )}
                        />
                        <span className="truncate">{p.name}</span>
                      </div>
                      <div className="flex flex-wrap items-center gap-1 text-[11px] text-muted-foreground">
                        <TeamBadge team={p.team} /> {p.pos} · {formatPrice(p.price)} · {formatNumber(p.proj)} poin ·{" "}
                        {formatNumber(p.chance, 0)}% main
                      </div>
                    </div>
                    <Button size="icon" variant={disabled ? "secondary" : "outline"} disabled={disabled} onClick={() => add(p)}>
                      <Plus className="h-4 w-4" />
                    </Button>
                  </div>
                );
              })}
              {!candidates.length ? <p className="py-6 text-center text-sm text-muted-foreground">Tidak ada pemain yang cocok.</p> : null}
            </div>
          </CardContent> : null}
        </Card>
      </div>

      {insights?.available ? (
        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Saran transfer multi-GW</CardTitle>
                <p className="text-sm text-muted-foreground">Dinilai dari total gain 3 GW, sudah memperhitungkan harga jual.</p>
              </CardHeader>
              <CardContent className="space-y-2">
                {(insights.multi ?? []).length ? (insights.multi ?? []).map((s, i) => {
                  const out = s.player;
                  const rep = s.reps?.[0];
                  return (
                    <div key={i} className="rounded-lg border p-3 text-sm">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <span className="font-medium">{out?.web_name}</span>
                          <span className="text-muted-foreground"> → </span>
                          <span className="font-medium text-primary">{rep?.web_name ?? "-"}</span>
                        </div>
                        <Badge variant="success">gain {formatNumber(s.gain)}</Badge>
                      </div>
                      <div className="mt-1 text-[11px] text-muted-foreground">
                        {out?.team_short} · {formatPrice(rep?.price ?? 0)} · {formatNumber(rep?.proj)} proyeksi · {formatNumber(rep?.chance, 0)}% main
                      </div>
                    </div>
                  );
                }) : <p className="text-sm text-muted-foreground">Tidak ada transfer yang cukup menguntungkan.</p>}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Saran transfer 1 GW</CardTitle>
                <p className="text-sm text-muted-foreground">Fokus jangka pendek untuk Gameweek berikutnya.</p>
              </CardHeader>
              <CardContent className="space-y-2">
                {(insights.single ?? []).length ? (insights.single ?? []).map((s, i) => {
                  const out = s.player;
                  const rep = s.reps?.[0];
                  return (
                    <div key={i} className="flex items-center justify-between rounded-lg border p-3 text-sm">
                      <span>{out?.web_name} → <strong>{rep?.web_name ?? "-"}</strong></span>
                      <span className="text-primary">+{formatNumber(s.gain)}</span>
                    </div>
                  );
                }) : <p className="text-sm text-muted-foreground">Tidak ada transfer 1 GW yang menguntungkan.</p>}
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Rencana 3 GW</CardTitle>
                <p className="text-sm text-muted-foreground">XI terbaik per GW tanpa transfer; rotasi gratis.</p>
              </CardHeader>
              <CardContent className="space-y-2">
                {(insights.plans ?? []).map((p, i) => (
                  <div key={i} className="flex items-center justify-between rounded-lg border p-3 text-sm">
                    <div>
                      <span className="font-semibold">GW {dashboard.gw.id + i}</span>
                      <span className="text-muted-foreground"> · formasi {p.formation?.join("-")}</span>
                    </div>
                    <div className="text-right">
                      <div className="font-bold text-primary">{formatNumber(p.total)}</div>
                      <div className="text-[10px] text-muted-foreground">kapten {p.captain?.web_name ?? "-"}</div>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Pemain berisiko (3 GW)</CardTitle>
                <p className="text-sm text-muted-foreground">Proyeksi GW2–GW3 rendah = kandidat transfer.</p>
              </CardHeader>
              <CardContent className="space-y-2">
                {(insights.risky ?? []).map((r, i) => (
                  <div key={i} className="flex items-center justify-between rounded-lg border p-2 text-sm">
                    <span>{r.player?.name} <span className="text-muted-foreground">({r.player?.team})</span></span>
                    <Badge variant="warning">{formatNumber(r.future)} poin</Badge>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>
        </div>
      ) : null}

      {mutation.isError ? <Alert variant="destructive">{String(mutation.error)}</Alert> : null}
      {mutation.isSuccess ? <Alert className="border-emerald-200 bg-emerald-50 text-emerald-900"><Check className="mr-2 inline h-4 w-4" /> Skuad tersimpan.</Alert> : null}
      {!valid && selected.length === 15 ? (
        <Alert variant="warning"><AlertCircle className="mr-2 inline h-4 w-4" /> Skuad belum valid. Cek kuota posisi, maksimal 3 per klub, dan budget.</Alert>
      ) : null}
    </div>
  );
}
