import { useMemo } from "react";
import { Activity, ArrowRightLeft, BarChart3, Crown, ListChecks, Target, TrendingDown } from "lucide-react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip as ReTooltip, XAxis, YAxis, Bar, BarChart, ReferenceLine } from "recharts";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { MetricCard, PageHeader, SectionTitle } from "@/components/shared";
import { usePerformance } from "@/lib/api";
import { formatNumber } from "@/lib/utils";

function captainResultBadge(result: "haul" | "return" | "blank") {
  if (result === "haul") return <Badge variant="success">Haul</Badge>;
  if (result === "return") return <Badge variant="warning">Return</Badge>;
  return <Badge variant="destructive">Blank</Badge>;
}

function transferResultBadge(result?: "win" | "loss" | "tie") {
  if (result === "win") return <Badge variant="success">Win</Badge>;
  if (result === "loss") return <Badge variant="destructive">Loss</Badge>;
  if (result === "tie") return <Badge variant="muted">Tie</Badge>;
  return <Badge variant="warning">Menunggu</Badge>;
}

export default function PerformancePage({ isBeginner }: { isBeginner: boolean }) {
  const { data, isLoading, error } = usePerformance();

  const completed = useMemo(() => (data?.history ?? []).filter((h) => h.metrics), [data]);
  const chartData = useMemo(
    () => completed.map((h) => ({ gw: `GW${h.gw}`, mae: h.metrics?.mae, rmse: h.metrics?.rmse })),
    [completed],
  );
  const latest = completed[completed.length - 1];
  const avgMae = completed.length ? completed.reduce((s, h) => s + (h.metrics?.mae ?? 0), 0) / completed.length : null;
  const top10 = latest?.metrics?.top_k?.["10"];
  const decisions = data?.decisions;
  const captain = decisions?.captain;
  const transfer = decisions?.transfer;

  if (isLoading) return <div className="py-20 text-center text-sm text-muted-foreground">Memuat performa model...</div>;
  if (error) return <div className="py-20 text-center text-sm text-destructive">Gagal memuat: {String(error)}</div>;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Performa & Akurasi"
        description="Seberapa sering model meleset, dan apakah model membaik sepanjang musim."
      >
        <Badge variant="secondary">{completed.length} GW terevaluasi</Badge>
      </PageHeader>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Rata-rata meleset" value={avgMae ? `${formatNumber(avgMae, 2)} poin` : "-"} hint="MAE seluruh pemain" icon={TrendingDown} />
        <MetricCard label="Meleset GW terakhir" value={latest?.metrics ? `${formatNumber(latest.metrics.mae, 2)} poin` : "-"} hint={latest ? `GW ${latest.gw}` : "-"} icon={Activity} />
        <MetricCard label="Top-10 meleset" value={top10 ? `${formatNumber(top10.mae, 2)} poin` : "-"} hint={top10 ? `bias ${formatNumber(top10.bias, 2)}` : "-"} icon={Target} accent="warning" />
        <MetricCard label="Bias keseluruhan" value={latest?.metrics?.bias !== undefined ? `${formatNumber(latest.metrics.bias, 2)} poin` : "-"} hint="Positif = aktual lebih tinggi" icon={BarChart3} accent="muted" />
      </div>

      <SectionTitle
        title="Akurasi keputusan"
        description="Apakah rekomendasi kapten dan transfer benar-benar menghasilkan poin — bukan hanya proyeksi yang dekat."
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Kapten return"
          value={captain ? `${formatNumber(captain.return_rate, 0)}%` : "-"}
          hint={captain ? `${captain.n_gws} GW · ≥4 poin` : "Belum ada data"}
          icon={Crown}
          accent="warning"
        />
        <MetricCard
          label="Poin kapten"
          value={captain ? formatNumber(captain.avg_points, 1) : "-"}
          hint={captain ? `field ${formatNumber(captain.avg_field_points, 1)} · ${formatNumber(captain.lift, 2)}× lipat` : "-"}
          icon={Target}
        />
        <MetricCard
          label="Top-10 return"
          value={captain ? `${formatNumber(captain.top10.return_rate, 0)}%` : "-"}
          hint={captain ? `${captain.top10.n_players} pemain · ≥4 poin` : "-"}
          icon={ListChecks}
          accent="muted"
        />
        <MetricCard
          label="Transfer win rate"
          value={transfer && transfer.n ? `${formatNumber(transfer.win_rate, 0)}%` : "-"}
          hint={transfer && transfer.n ? `${transfer.wins}W · ${transfer.losses}L · ${transfer.ties}T` : "Belum ada transfer dievaluasi"}
          icon={ArrowRightLeft}
          accent="muted"
        />
      </div>

      {!isBeginner ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Kapten per GW</CardTitle>
              <p className="text-sm text-muted-foreground">
                Proxy = proyeksi tertinggi (historis). Rekomendasi = kapten EV dari simulator.
              </p>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>GW</TableHead>
                    <TableHead>Kapten</TableHead>
                    <TableHead className="text-right">Proj</TableHead>
                    <TableHead className="text-right">Aktual</TableHead>
                    <TableHead>Hasil</TableHead>
                    <TableHead className="text-right">Field</TableHead>
                    <TableHead className="text-right">Regret</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {[...(captain?.by_gw ?? [])].reverse().map((r) => (
                    <TableRow key={r.gw}>
                      <TableCell className="font-medium whitespace-nowrap">GW {r.gw}</TableCell>
                      <TableCell className="text-sm">
                        {r.captain} <span className="text-muted-foreground">({r.team})</span>
                        {r.source === "proxy" ? <span className="ml-1 text-[10px] text-muted-foreground">proxy</span> : null}
                      </TableCell>
                      <TableCell className="text-right">{formatNumber(r.proj, 2)}</TableCell>
                      <TableCell className="text-right font-semibold">{r.actual}</TableCell>
                      <TableCell>{captainResultBadge(r.result)}</TableCell>
                      <TableCell className="text-right">{formatNumber(r.field_avg, 2)}</TableCell>
                      <TableCell className="text-right text-muted-foreground">{r.regret}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Transfer per GW</CardTitle>
              <p className="text-sm text-muted-foreground">
                Net = poin pemain masuk − poin pemain keluar − biaya hit.
              </p>
            </CardHeader>
            <CardContent className="p-0">
              {transfer && transfer.by_gw.length ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>GW</TableHead>
                      <TableHead>Transfer</TableHead>
                      <TableHead className="text-right">Out</TableHead>
                      <TableHead className="text-right">In</TableHead>
                      <TableHead className="text-right">Net</TableHead>
                      <TableHead>Hasil</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {[...transfer.by_gw].reverse().map((r) => (
                      <TableRow key={r.gw}>
                        <TableCell className="font-medium whitespace-nowrap">GW {r.gw}</TableCell>
                        <TableCell className="text-sm">
                          {r.transfers.map((t) => `${t.out_name} → ${t.in_name}`).join(", ")}
                        </TableCell>
                        <TableCell className="text-right">{r.status === "done" ? r.out_points : "-"}</TableCell>
                        <TableCell className="text-right">{r.status === "done" ? r.in_points : "-"}</TableCell>
                        <TableCell className="text-right font-semibold">
                          {r.status === "done" && r.net !== undefined ? `${r.net > 0 ? "+" : ""}${r.net}` : "-"}
                        </TableCell>
                        <TableCell>{transferResultBadge(r.result)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <div className="p-4 text-sm text-muted-foreground">
                  Belum ada rekomendasi transfer yang dievaluasi. Rekomendasi dicatat otomatis mulai GW berjalan dan dinilai setelah GW selesai.
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}

      {decisions?.notes?.length ? (
        <Card className="bg-muted/40">
          <CardContent className="space-y-1 p-4 text-xs text-muted-foreground">
            {decisions.notes.map((note) => (
              <p key={note}>• {note}</p>
            ))}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Tren error</CardTitle>
          <p className="text-sm text-muted-foreground">MAE = rata-rata meleset. RMSE lebih menghukum error besar.</p>
        </CardHeader>
        <CardContent className="h-[320px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
              <XAxis dataKey="gw" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <ReTooltip />
              <Line type="monotone" dataKey="mae" stroke="#37003c" strokeWidth={3} dot={{ r: 3 }} name="MAE" />
              <Line type="monotone" dataKey="rmse" stroke="#d97706" strokeWidth={2} strokeDasharray="5 3" dot={false} name="RMSE" />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Detail per Gameweek</CardTitle></CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader><TableRow><TableHead>GW</TableHead><TableHead className="text-right">MAE</TableHead><TableHead className="text-right">RMSE</TableHead><TableHead className="text-right">Bias</TableHead><TableHead className="text-right">N</TableHead></TableRow></TableHeader>
              <TableBody>
                {[...completed].reverse().map((h) => (
                  <TableRow key={h.gw}>
                    <TableCell className="font-medium">GW {h.gw}</TableCell>
                    <TableCell className="text-right">{formatNumber(h.metrics?.mae, 2)}</TableCell>
                    <TableCell className="text-right">{formatNumber(h.metrics?.rmse, 2)}</TableCell>
                    <TableCell className="text-right">{formatNumber(h.metrics?.bias, 2)}</TableCell>
                    <TableCell className="text-right text-muted-foreground">{h.metrics?.n}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Backtest baseline</CardTitle></CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader><TableRow><TableHead>Model</TableHead><TableHead className="text-right">MAE</TableHead><TableHead className="text-right">Top-10 MAE</TableHead><TableHead className="text-right">Bias</TableHead></TableRow></TableHeader>
              <TableBody>
                {data.baselines.map((b) => (
                  <TableRow key={b.model}>
                    <TableCell className="text-sm">{b.model}</TableCell>
                    <TableCell className="text-right">{formatNumber(b.mae, 2)}</TableCell>
                    <TableCell className="text-right">{formatNumber(b.top10?.mae, 2)}</TableCell>
                    <TableCell className="text-right">{formatNumber(b.bias, 2)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
          <p className="border-t px-4 py-2 text-[11px] text-muted-foreground">
            Baseline form/PPG/ep_next FPL muncul otomatis setelah data fitur tersimpan (mulai GW9 ke depan).
          </p>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>MAE per posisi</CardTitle></CardHeader>
          <CardContent className="grid grid-cols-2 gap-3">
            {Object.entries(latest?.metrics?.by_pos ?? {}).map(([pos, mae]) => (
              <div key={pos} className="rounded-lg border p-3">
                <div className="text-xs uppercase text-muted-foreground">{pos}</div>
                <div className="mt-1 text-xl font-bold">{formatNumber(mae, 2)}</div>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>MAE per FDR</CardTitle></CardHeader>
          <CardContent className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {Object.entries(latest?.metrics?.by_fdr ?? {}).map(([fdr, mae]) => (
              <div key={fdr} className="rounded-lg border p-3">
                <div className="text-xs uppercase text-muted-foreground">FDR {fdr}</div>
                <div className="mt-1 text-xl font-bold">{formatNumber(mae, 2)}</div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      {!isBeginner ? (
        <>
          <SectionTitle title="Kalibrasi desil" description="Apakah model terlalu tinggi/rendah di tiap kelompok proyeksi." />
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardContent className="h-[300px] pt-5">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={latest?.metrics?.deciles ?? []} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                    <XAxis dataKey="decile" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <ReTooltip />
                    <ReferenceLine y={0} stroke="#94a3b8" />
                    <Bar dataKey="bias" fill="#37003c" radius={[4, 4, 0, 0]} name="Bias" />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Top-K</CardTitle></CardHeader>
              <CardContent className="p-0">
                <Table>
                  <TableHeader><TableRow><TableHead>Kelompok</TableHead><TableHead className="text-right">MAE</TableHead><TableHead className="text-right">Bias</TableHead><TableHead className="text-right">Proyeksi</TableHead><TableHead className="text-right">Aktual</TableHead></TableRow></TableHeader>
                  <TableBody>
                    {Object.entries(latest?.metrics?.top_k ?? {}).map(([k, v]) => (
                      <TableRow key={k}>
                        <TableCell>Top {k}</TableCell>
                        <TableCell className="text-right">{formatNumber(v.mae, 2)}</TableCell>
                        <TableCell className="text-right">{formatNumber(v.bias, 2)}</TableCell>
                        <TableCell className="text-right">{formatNumber(v.mean_proj, 2)}</TableCell>
                        <TableCell className="text-right">{formatNumber(v.mean_actual, 2)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader><CardTitle>Kesalahan terbesar GW terakhir</CardTitle></CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2">
              <div>
                <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-red-700">Terlalu tinggi</div>
                {(latest?.metrics?.top_overestimate ?? []).map((e) => (
                  <div key={e.name} className="flex justify-between border-b py-1.5 text-sm last:border-0">
                    <span>{e.name} <span className="text-muted-foreground">({e.pos})</span></span>
                    <span className="text-red-700">{formatNumber(e.error, 2)}</span>
                  </div>
                ))}
              </div>
              <div>
                <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-emerald-700">Terlalu rendah</div>
                {(latest?.metrics?.top_underestimate ?? []).map((e) => (
                  <div key={e.name} className="flex justify-between border-b py-1.5 text-sm last:border-0">
                    <span>{e.name} <span className="text-muted-foreground">({e.pos})</span></span>
                    <span className="text-emerald-700">+{formatNumber(e.error, 2)}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </>
      ) : (
        <Card className="bg-muted/40">
          <CardContent className="p-4 text-sm text-muted-foreground">
            Detail top-K, kalibrasi desil, dan kesalahan terbesar tersedia di Mode Analis.
          </CardContent>
        </Card>
      )}
    </div>
  );
}
