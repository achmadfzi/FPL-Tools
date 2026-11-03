import { useMemo, useState } from "react";
import { Crown, Info, ShieldCheck, Sparkles, Target, TrendingUp } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/primitives";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ConfidenceBadge, MetricCard, PageHeader, PlayerAvatar, TeamBadge } from "@/components/shared";
import { useCaptain, useDashboard } from "@/lib/api";
import { fdrStyle, formatNumber, formatPct, formatPrice } from "@/lib/utils";
import type { CaptainCandidate } from "@/lib/types";

type Risk = "Proyeksi model" | "Seimbang" | "Aman" | "Agresif";

function score(c: CaptainCandidate, risk: Risk) {
  if (risk === "Proyeksi model") return c.proj;
  if (risk === "Aman") return c.ev_captain - c.ev_se;
  if (risk === "Agresif") return c.ev_captain + 2 * c.p_haul;
  return c.ev_captain;
}

export default function CaptainPage({ isBeginner }: { isBeginner: boolean }) {
  const { data: dashboard } = useDashboard();
  const { data, isLoading, error } = useCaptain();
  const [risk, setRisk] = useState<Risk>("Proyeksi model");

  const ranked = useMemo(() => {
    const list = [...(data?.candidates ?? [])];
    return list.sort((a, b) => score(b, risk) - score(a, risk));
  }, [data, risk]);

  if (isLoading) return <div className="py-20 text-center text-sm text-muted-foreground">Menjalankan simulasi kapten...</div>;
  if (error) return <div className="py-20 text-center text-sm text-destructive">Gagal memuat: {String(error)}</div>;
  if (!data || !dashboard) return null;

  const top = ranked[0];
  const modelVice = [...(data?.candidates ?? [])].sort((a, b) => b.proj - a.proj)[1];
  const safest = [...ranked].sort((a, b) => a.p_blank - b.p_blank)[0];
  const aggressive = [...ranked].sort((a, b) => b.p_haul - a.p_haul)[0];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Kapten & Transfer"
        description="Bandingkan kandidat kapten dan lihat rencana transfer. Keputusan utama tetap di Minggu Ini."
      >
        <Badge variant="secondary">Sumber: {data.source}</Badge>
      </PageHeader>

      <Tabs defaultValue="captain">
        <TabsList>
          <TabsTrigger value="captain">
            <Crown className="mr-2 h-4 w-4" /> Kapten
          </TabsTrigger>
          <TabsTrigger value="transfer">
            <TrendingUp className="mr-2 h-4 w-4" /> Transfer
          </TabsTrigger>
          <TabsTrigger value="market">
            <Target className="mr-2 h-4 w-4" /> Pasar
          </TabsTrigger>
        </TabsList>

        <TabsContent value="captain" className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 text-sm font-medium">
              <ShieldCheck className="h-4 w-4 text-primary" /> Profil risiko
            </div>
            <Select value={risk} onChange={(e) => setRisk(e.target.value as Risk)} className="w-52">
              <option value="Proyeksi model">Proyeksi model (default)</option>
              <option value="Seimbang">Seimbang (EV)</option>
              <option value="Aman">Aman (EV − varians)</option>
              <option value="Agresif">Agresif (EV + ceiling)</option>
            </Select>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Kapten rekomendasi" value={top.web_name} hint={`${top.team_short} · ${formatNumber(top.proj)} proyeksi${risk === "Proyeksi model" && modelVice ? ` · wakil ${modelVice.web_name}` : ""}`} icon={Crown} />
            <MetricCard label="Proyeksi kapten ×2" value={formatNumber(top.model_points ?? top.proj * 2)} hint="Dasar: proyeksi poin model" icon={Sparkles} accent="success" />
            <MetricCard label="Peluang main" value={formatPct(top.p_plays)} hint={`Blank ${formatPct(top.p_blank)}`} icon={ShieldCheck} />
            <MetricCard label="EV simulator" value={formatNumber(top.ev_captain)} hint="Pembanding, bukan penentu" icon={Target} accent="warning" />
          </div>

          <Card>
            <CardHeader className="flex-row items-center justify-between space-y-0">
              <div>
                <CardTitle>Kandidat kapten</CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">
                  {risk === "Proyeksi model"
                    ? "Urutan berdasarkan proyeksi poin model. Kapten = proyeksi tertinggi, wakil = proyeksi tertinggi kedua."
                    : risk === "Aman"
                      ? "Mengurangi kandidat dengan varians tinggi."
                      : risk === "Agresif"
                        ? "Memberi bobot lebih pada peluang haul besar."
                        : "Urutan berdasarkan EV simulator."}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  EV simulator ditampilkan sebagai pembanding risiko, bukan penentu kapten.
                </p>
              </div>
              <ConfidenceBadge level={top.p_plays >= 0.95 ? "Tinggi" : top.p_plays >= 0.75 ? "Sedang" : "Rendah"} />
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Pemain</TableHead>
                    <TableHead className="text-right">Proyeksi ×2</TableHead>
                    <TableHead className="text-right">EV sim</TableHead>
                    <TableHead className="text-right">Main</TableHead>
                    <TableHead className="text-right">Blank</TableHead>
                    <TableHead className="text-right">Haul</TableHead>
                    <TableHead className="text-right">Kepemilikan</TableHead>
                    {!isBeginner ? <TableHead className="text-right">p10–p90</TableHead> : null}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {ranked.map((c) => (
                    <TableRow key={c.id}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <PlayerAvatar name={c.web_name} team={c.team_short} size="sm" />
                          <div>
                            <div className="text-sm font-medium">{c.web_name}</div>
                            <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
                              <TeamBadge team={c.team_short} /> {formatNumber(c.proj)} proyeksi
                            </div>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell className="text-right font-semibold text-primary">{formatNumber(c.model_points ?? c.proj * 2)}</TableCell>
                      <TableCell className="text-right text-sm text-muted-foreground">{formatNumber(c.ev_captain)}</TableCell>
                      <TableCell className="text-right">{formatPct(c.p_plays)}</TableCell>
                      <TableCell className="text-right">{formatPct(c.p_blank)}</TableCell>
                      <TableCell className="text-right">{formatPct(c.p_haul)}</TableCell>
                      <TableCell className="text-right">{formatNumber(c.selected_by)}%</TableCell>
                      {!isBeginner ? <TableCell className="text-right text-xs text-muted-foreground">{c.p10}–{c.p90}</TableCell> : null}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <div className="grid gap-4 md:grid-cols-3">
            <Card>
              <CardHeader><CardTitle className="text-sm">Paling aman</CardTitle></CardHeader>
              <CardContent className="text-sm">
                <div className="font-semibold">{safest.web_name}</div>
                <p className="mt-1 text-muted-foreground">Blank {formatPct(safest.p_blank)} · main {formatPct(safest.p_plays)}</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className="text-sm">Paling agresif</CardTitle></CardHeader>
              <CardContent className="text-sm">
                <div className="font-semibold">{aggressive.web_name}</div>
                <p className="mt-1 text-muted-foreground">Peluang haul {formatPct(aggressive.p_haul)} · kepemilikan {formatNumber(aggressive.selected_by)}%</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className="text-sm">Catatan</CardTitle></CardHeader>
              <CardContent className="flex gap-2 text-sm text-muted-foreground">
                <Info className="mt-0.5 h-4 w-4 shrink-0" />
                Selisih EV di bawah ~2× standard error sebaiknya dianggap seri.
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="transfer" className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <MetricCard label="Gain rencana" value={`${formatNumber(dashboard.plan.gain)} poin`} hint={`Horizon ${dashboard.plan.horizon} GW`} icon={TrendingUp} accent="success" />
            <MetricCard label="Bank" value={`£${dashboard.squad.bank.toFixed(1)}m`} hint={`${dashboard.squad.free_transfers} FT tersedia`} />
            <MetricCard label="Total rencana" value={formatNumber(dashboard.plan.total_planned)} hint="Termasuk kapten" />
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Transfer karena cedera / peluang main</CardTitle>
              <p className="text-sm text-muted-foreground">Pemain masuk dengan peluang 0% tidak disarankan.</p>
            </CardHeader>
            <CardContent className="space-y-2">
              {dashboard.injury_suggestions?.length ? dashboard.injury_suggestions.map((s, i) => (
                <div key={`${s.player.id}-${i}`} className="rounded-lg border p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <PlayerAvatar name={s.player.name} team={s.player.team} size="sm" />
                      <div>
                        <div className="text-sm font-semibold">{s.player.name} <span className="text-muted-foreground">({s.player.team})</span></div>
                        <div className="text-[11px] text-muted-foreground">{s.availability?.label} · {s.availability?.pct}% main</div>
                      </div>
                    </div>
                    <Badge variant={s.action === "JUAL SEKARANG" ? "destructive" : "warning"}>{s.action}</Badge>
                  </div>
                  {s.replacement ? (
                    <div className="mt-2 flex items-center justify-between text-sm">
                      <span>Pengganti: <strong>{s.replacement.name}</strong> ({s.replacement.team})</span>
                      <span className="text-emerald-700">gain {formatNumber(s.gain)}</span>
                    </div>
                  ) : null}
                </div>
              )) : <p className="text-sm text-muted-foreground">Tidak ada pemain skuad dengan status cedera/diragukan.</p>}
            </CardContent>
          </Card>

          {dashboard.plan.plan.map((step) => (
            <Card key={step.gw}>
              <CardHeader className="flex-row items-center justify-between space-y-0">
                <CardTitle className="text-base">GW {step.gw}</CardTitle>
                {step.hits ? <Badge variant="destructive">Hit -{step.hits}</Badge> : <Badge variant="success">Tanpa hit</Badge>}
              </CardHeader>
              <CardContent>
                {step.transfers.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Tidak ada transfer.</p>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Jual</TableHead>
                        <TableHead>Beli</TableHead>
                        <TableHead className="text-right">Peluang main</TableHead>
                        <TableHead className="text-right">Harga</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {step.transfers.map((t, i) => (
                        <TableRow key={i}>
                          <TableCell className="text-sm">{t.out_name}</TableCell>
                          <TableCell className="text-sm font-medium">{t.in_name}</TableCell>
                          <TableCell className="text-right">{formatNumber(t.in_chance)}%</TableCell>
                          <TableCell className="text-right">{formatPrice(t.in_price)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          ))}
          <Button variant="outline" onClick={() => window.location.assign("/detail")}>Lihat detail lengkap</Button>
        </TabsContent>

        <TabsContent value="market" className="space-y-4">
          {(() => {
            const market = dashboard.market ?? {};
            const ticker = market.ticker ?? [];
            const tickerGw = market.ticker_gw ?? dashboard.gw.id;
            const gws = Array.from({ length: 6 }, (_, i) => tickerGw + i);
            return (
              <>
                <Card>
                  <CardHeader>
                    <CardTitle>Fixture ticker 6 GW</CardTitle>
                    <p className="text-sm text-muted-foreground">Angka = FDR lawan. ⚡ DGW.</p>
                  </CardHeader>
                  <CardContent className="overflow-x-auto p-0">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Tim</TableHead>
                          {gws.map((gw) => <TableHead key={gw} className="text-center">GW {gw}</TableHead>)}
                          <TableHead className="text-right">Avg</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {ticker.slice(0, 20).map((row: any) => (
                          <TableRow key={row.team_short}>
                            <TableCell className="font-medium">{row.team_short}</TableCell>
                            {gws.map((gw) => {
                              const cell = row[`gw_${gw}`] ?? {};
                              return (
                                <TableCell key={gw} className="text-center">
                                  <span
                                    className="inline-block rounded px-1.5 py-0.5 text-[11px] font-semibold"
                                    style={fdrStyle(cell.fdr)}
                                  >
                                    {cell.text ?? "-"}{cell.dgw ? " ⚡" : ""}
                                  </span>
                                </TableCell>
                              );
                            })}
                            <TableCell className="text-right text-sm font-semibold">{formatNumber(row.avg_fdr, 1)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>

                <div className="grid gap-4 lg:grid-cols-2">
                  <Card>
                    <CardHeader><CardTitle>Value picks</CardTitle><p className="text-sm text-muted-foreground">Poin per £1 juta.</p></CardHeader>
                    <CardContent className="space-y-3">
                      {(["GK", "DEF", "MID", "FWD"] as const).map((position) => {
                        const picks = (market.value_picks ?? []).filter((p) => p.pos === position).slice(0, 5);
                        if (!picks.length) return null;
                        return (
                          <div key={position}>
                            <div className="mb-1 text-xs font-semibold uppercase text-muted-foreground">{position}</div>
                            {picks.map((p) => (
                              <div key={p.id} className="flex items-center justify-between border-b py-1.5 text-sm last:border-0">
                                <span>{p.name} <span className="text-muted-foreground">({p.team})</span></span>
                                <span className="text-muted-foreground">{formatNumber(p.value, 2)} pts/£1jt</span>
                              </div>
                            ))}
                          </div>
                        );
                      })}
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader><CardTitle>Differential picks</CardTitle><p className="text-sm text-muted-foreground">Kepemilikan &lt;5%, proyeksi tinggi.</p></CardHeader>
                    <CardContent className="space-y-2">
                      {(market.differentials ?? []).map((p) => (
                        <div key={p.id} className="flex items-center justify-between rounded-lg border p-2 text-sm">
                          <span>{p.name} <span className="text-muted-foreground">({p.team}, {p.pos})</span></span>
                          <span className="text-primary">{formatNumber(p.proj)} · {formatNumber(p.selected_by)}%</span>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                </div>

                <div className="grid gap-4 lg:grid-cols-2">
                  <Card>
                    <CardHeader><CardTitle>Pemain berisiko</CardTitle></CardHeader>
                    <CardContent className="space-y-2">
                      {(market.risk_players ?? []).map((p) => (
                        <div key={p.id} className="flex items-center justify-between rounded-lg border p-2 text-sm">
                          <span>{p.name} <span className="text-muted-foreground">({p.team})</span></span>
                          <Badge variant="destructive">{formatNumber(p.chance, 0)}% main</Badge>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader><CardTitle>Mahal tapi proyeksi rendah</CardTitle></CardHeader>
                    <CardContent className="space-y-2">
                      {(market.overpriced ?? []).map((p) => (
                        <div key={p.id} className="flex items-center justify-between rounded-lg border p-2 text-sm">
                          <span>{p.name} <span className="text-muted-foreground">({p.team})</span></span>
                          <span>{formatPrice(p.price)} · {formatNumber(p.proj)} poin</span>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                </div>

                <div className="grid gap-4 lg:grid-cols-2">
                  <Card>
                    <CardHeader><CardTitle>Bintang musim lalu</CardTitle></CardHeader>
                    <CardContent className="space-y-2">
                      {dashboard.last_stars.map((p) => (
                        <div key={p.id} className="flex items-center justify-between rounded-lg border p-2 text-sm">
                          <span>{p.name} <span className="text-muted-foreground">({p.team})</span></span>
                          <span>{formatNumber(p.last_points, 0)} poin lalu · {formatNumber(p.proj)} proyeksi</span>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader><CardTitle>Value musim lalu</CardTitle></CardHeader>
                    <CardContent className="space-y-2">
                      {dashboard.last_value.map((p) => (
                        <div key={p.id} className="flex items-center justify-between rounded-lg border p-2 text-sm">
                          <span>{p.name} <span className="text-muted-foreground">({p.team})</span></span>
                          <span>{formatNumber(p.last_value, 2)} pts/£1jt</span>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                </div>
              </>
            );
          })()}
        </TabsContent>
      </Tabs>
    </div>
  );
}
