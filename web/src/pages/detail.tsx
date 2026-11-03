import { AlertTriangle, CalendarDays, Crown, Info, ListChecks, Puzzle, ShieldAlert, Users } from "lucide-react";
import { Alert } from "@/components/ui/primitives";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ConfidenceBadge, MetricCard, PageHeader, PlayerAvatar, SectionTitle, TeamBadge } from "@/components/shared";
import { Pitch } from "@/components/pitch";
import { useDashboard } from "@/lib/api";
import { formatNumber, formatPct, formatPrice } from "@/lib/utils";

export default function DetailPage({ isBeginner }: { isBeginner: boolean }) {
  const { data, isLoading, error } = useDashboard();

  if (isLoading) return <div className="py-20 text-center text-sm text-muted-foreground">Memuat rencana detail...</div>;
  if (error) return <Alert variant="destructive">Gagal memuat: {String(error)}</Alert>;
  if (!data) return null;

  const { captain, transfer, chip, alerts, plan, chip_calendar } = data;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Rencana Detail"
        description="Semua keputusan dan angka pendukung. Mulai dari ringkasan, lalu buka tab lain jika perlu."
      >
        <Badge variant="secondary">GW {data.gw.id}</Badge>
        <ButtonChip />
      </PageHeader>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Kapten" value={captain.name} hint={`Proyeksi ×2 ${formatNumber(captain.ev)} · wakil ${captain.vice ?? "-"}`} icon={Crown} />
        <MetricCard label="Transfer" value={transfer.headline} hint={transfer.meaning} icon={ListChecks} accent="warning" />
        <MetricCard label="Chip" value={chip.headline} hint={chip.meaning} icon={Puzzle} accent="success" />
        <MetricCard label="Peringatan" value={`${alerts.length} pemain`} hint={alerts[0]?.name ?? "Skuad aman"} icon={ShieldAlert} accent={alerts.length ? "destructive" : "muted"} />
      </div>

      <Tabs defaultValue="xi">
        <TabsList className="flex-wrap">
          <TabsTrigger value="xi"><Users className="mr-2 h-4 w-4" /> XI & Bench</TabsTrigger>
          <TabsTrigger value="transfer"><ListChecks className="mr-2 h-4 w-4" /> Transfer</TabsTrigger>
          <TabsTrigger value="chip"><Puzzle className="mr-2 h-4 w-4" /> Chip</TabsTrigger>
          <TabsTrigger value="alerts"><AlertTriangle className="mr-2 h-4 w-4" /> Peringatan</TabsTrigger>
        </TabsList>

        <TabsContent value="xi" className="space-y-4">
          <Pitch
            xi={data.xi}
            bench={data.bench}
            captainId={captain.id}
            viceName={captain.vice}
            formation={data.line.formation}
            ev={data.line.ev}
          />
          <Card>
            <CardHeader>
              <CardTitle>Starting XI</CardTitle>
              <p className="text-sm text-muted-foreground">Formasi {data.line.formation?.join("-")} · EV {formatNumber(data.line.ev)} · simulasi {data.line.n} skenario.</p>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Pemain</TableHead>
                    <TableHead>Posisi</TableHead>
                    <TableHead className="text-right">Peluang</TableHead>
                    <TableHead className="text-right">Proyeksi</TableHead>
                    {!isBeginner ? <TableHead className="text-right">EV</TableHead> : null}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.xi.map((p) => (
                    <TableRow key={p.id}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <PlayerAvatar name={p.name} team={p.team} size="sm" />
                          <div>
                            <div className="flex items-center gap-1.5 text-sm font-medium">
                              {p.name}
                              {p.id === captain.id ? <Badge> C</Badge> : null}
                              {p.name === captain.vice ? <Badge variant="warning">V</Badge> : null}
                            </div>
                            <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
                              <TeamBadge team={p.team} /> {p.pos} · {formatPrice(p.price)}
                            </div>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell><Badge variant="secondary">{p.pos}</Badge></TableCell>
                      <TableCell className="text-right">{formatPct(p.p_play)}</TableCell>
                      <TableCell className="text-right font-semibold text-primary">{formatNumber(p.proj)}</TableCell>
                      {!isBeginner ? <TableCell className="text-right">{formatNumber(p.ev)}</TableCell> : null}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Bench</CardTitle></CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow><TableHead>Slot</TableHead><TableHead>Pemain</TableHead><TableHead className="text-right">Proyeksi</TableHead></TableRow>
                </TableHeader>
                <TableBody>
                  {data.bench.map((p) => (
                    <TableRow key={p.id}>
                      <TableCell className="text-xs text-muted-foreground">{p.bench_slot ?? "-"}</TableCell>
                      <TableCell className="text-sm">{p.name} <span className="text-muted-foreground">({p.team})</span></TableCell>
                      <TableCell className="text-right">{formatNumber(p.proj)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="transfer" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Rencana transfer</CardTitle>
              <p className="text-sm text-muted-foreground">
                Horizon {plan.horizon} GW · total {formatNumber(plan.total_planned)} poin · tahan {formatNumber(plan.hold_total)} · gain {formatNumber(plan.gain)}.
              </p>
            </CardHeader>
            <CardContent className="space-y-4">
              {plan.plan.map((step) => (
                <div key={step.gw} className="rounded-lg border p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <div className="font-semibold">GW {step.gw}</div>
                    {step.hits ? <Badge variant="destructive">Hit -{step.hits}</Badge> : <Badge variant="success">Tanpa hit</Badge>}
                  </div>
                  {step.transfers.length ? (
                    <Table>
                      <TableHeader><TableRow><TableHead>Jual</TableHead><TableHead>Beli</TableHead><TableHead className="text-right">Peluang</TableHead><TableHead className="text-right">Harga</TableHead></TableRow></TableHeader>
                      <TableBody>
                        {step.transfers.map((t, i) => (
                          <TableRow key={i}>
                            <TableCell>{t.out_name}</TableCell>
                            <TableCell className="font-medium">{t.in_name}</TableCell>
                            <TableCell className="text-right">{formatNumber(t.in_chance)}%</TableCell>
                            <TableCell className="text-right">{formatPrice(t.in_price)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  ) : (
                    <p className="text-sm text-muted-foreground">Tidak ada transfer.</p>
                  )}
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="chip" className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {(["TC", "BB", "FH", "WC"] as const).map((key) => {
              const c = data.chips?.[key];
              return (
                <MetricCard
                  key={key}
                  label={{ TC: "Triple Captain", BB: "Bench Boost", FH: "Free Hit", WC: "Wildcard" }[key]}
                  value={c ? `+${formatNumber(c.gain)}` : "Dipakai"}
                  hint={c ? "estimasi gain" : "tidak tersedia"}
                  icon={Puzzle}
                  accent={c ? "success" : "muted"}
                />
              );
            })}
          </div>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><CalendarDays className="h-4 w-4" /> Kalender chip</CardTitle>
              <p className="text-sm text-muted-foreground">Rekomendasi 12 GW ke depan berdasarkan jadwal dan proyeksi.</p>
            </CardHeader>
            <CardContent>
              {(chip_calendar?.calendar ?? []).map((c) => (
                <div key={`${c.chip}-${c.gw}`} className="flex items-center justify-between border-b py-2 text-sm last:border-0">
                  <span><strong>{c.chip}</strong> → GW {c.gw}</span>
                  <Badge variant="outline">skor {formatNumber(c.score)}</Badge>
                </div>
              ))}
              {!chip_calendar?.calendar?.length ? <p className="text-sm text-muted-foreground">Belum ada rekomendasi.</p> : null}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="alerts" className="space-y-4">
          <Card>
            <CardHeader><CardTitle>Peringatan skuad</CardTitle></CardHeader>
            <CardContent>
              {alerts.length ? (
                <Table>
                  <TableHeader><TableRow><TableHead>Pemain</TableHead><TableHead>Status</TableHead><TableHead className="text-right">Peluang</TableHead><TableHead>Kabar</TableHead><TableHead>Saran</TableHead></TableRow></TableHeader>
                  <TableBody>
                    {alerts.map((a) => (
                      <TableRow key={a.id}>
                        <TableCell className="font-medium">{a.name} <span className="text-muted-foreground">({a.team})</span></TableCell>
                        <TableCell><Badge variant={a.is_out ? "destructive" : "warning"}>{a.label}</Badge></TableCell>
                        <TableCell className="text-right">{formatNumber(a.pct)}%</TableCell>
                        <TableCell className="max-w-xs truncate text-sm text-muted-foreground">{a.news || "-"}</TableCell>
                        <TableCell><Badge variant={a.is_out ? "destructive" : "warning"}>{a.action}</Badge></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <p className="text-sm text-emerald-700">Skuad aman. Tidak ada pemain cedera/diragukan.</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function ButtonChip() {
  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      <Info className="h-4 w-4" /> Angka EV/p10–p90 hanya di Mode Analis.
    </div>
  );
}
