import { Activity, Brain, CalendarDays, FlaskConical, ShieldCheck } from "lucide-react";
import { Alert } from "@/components/ui/primitives";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { MetricCard, PageHeader } from "@/components/shared";
import { useLab } from "@/lib/api";
import { formatNumber } from "@/lib/utils";

export default function LabPage({ isBeginner }: { isBeginner: boolean }) {
  const { data, isLoading, error } = useLab();

  if (isLoading) return <div className="py-20 text-center text-sm text-muted-foreground">Memuat laboratorium model...</div>;
  if (error) return <Alert variant="destructive">Gagal memuat: {String(error)}</Alert>;
  if (!data) return null;

  const calibration = data.calibration;
  const ml = data.ml;
  const calendar = data.chip_calendar?.calendar ?? [];
  const rows = data.chip_calendar?.by_gw ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Lab & Chip"
        description="Kalender chip dan status eksperimen model. Angka di sini tidak dipakai untuk rekomendasi utama kecuali statusnya AKTIF."
      >
        <Badge variant="secondary">Mode {isBeginner ? "Pemula" : "Analis"}</Badge>
      </PageHeader>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Kalibrasi" value={calibration.enabled ? "Aktif" : "Nonaktif"} hint={calibration.method ? `metode ${calibration.method}` : "-"} icon={ShieldCheck} accent={calibration.enabled ? "success" : "muted"} />
        <MetricCard label="ML model" value={ml.enabled ? "Aktif" : "Eksperimental"} hint={ml.available ? `${ml.n_samples ?? 0} sampel` : "belum dilatih"} icon={Brain} accent={ml.enabled ? "success" : "warning"} />
        <MetricCard label="Chip calendar" value={`${calendar.length} rekomendasi`} hint={calendar[0] ? `${calendar[0].chip} → GW ${calendar[0].gw}` : "belum ada"} icon={CalendarDays} />
        <MetricCard label="History segar" value={`${data.data_health.history_fresh}/${data.data_health.history_total}`} hint="pemain dengan data per-GW" icon={Activity} accent="muted" />
      </div>

      <Tabs defaultValue="chip">
        <TabsList>
          <TabsTrigger value="chip"><FlaskConical className="mr-2 h-4 w-4" /> Chip</TabsTrigger>
          {!isBeginner ? <TabsTrigger value="model"><Brain className="mr-2 h-4 w-4" /> Model</TabsTrigger> : null}
        </TabsList>

        <TabsContent value="chip" className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {(["TC", "BB", "FH", "WC"] as const).map((key) => {
              const c = data.chips?.[key];
              return (
                <MetricCard
                  key={key}
                  label={{ TC: "Triple Captain", BB: "Bench Boost", FH: "Free Hit", WC: "Wildcard" }[key]}
                  value={c ? `+${formatNumber(c.gain)}` : "Dipakai"}
                  hint={c?.captain ? `kapten ${c.captain}` : c ? "estimasi gain GW ini" : "tidak tersedia"}
                  icon={FlaskConical}
                  accent={c ? "success" : "muted"}
                />
              );
            })}
          </div>

          <Card>
            <CardHeader><CardTitle>Rencana chip</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {calendar.map((c) => (
                <div key={`${c.chip}-${c.gw}`} className="flex items-center justify-between rounded-lg border p-3 text-sm">
                  <div>
                    <div className="font-semibold">{c.chip} → GW {c.gw}</div>
                    <div className="text-xs text-muted-foreground">
                      DGW: {c.dgw?.length ? c.dgw.join(", ") : "-"} · BGW: {c.bgw?.length ? c.bgw.join(", ") : "-"}
                    </div>
                  </div>
                  <Badge variant="outline">skor {formatNumber(c.score)}</Badge>
                </div>
              ))}
              {!calendar.length ? <p className="text-sm text-muted-foreground">Belum ada rekomendasi chip.</p> : null}
            </CardContent>
          </Card>

          {!isBeginner && rows.length ? (
            <Card>
              <CardHeader><CardTitle>Peluang chip per GW</CardTitle></CardHeader>
              <CardContent className="p-0">
                <Table>
                  <TableHeader><TableRow><TableHead>GW</TableHead><TableHead className="text-right">TC</TableHead><TableHead className="text-right">BB</TableHead><TableHead className="text-right">FH</TableHead><TableHead className="text-right">WC</TableHead><TableHead>DGW</TableHead><TableHead>BGW</TableHead></TableRow></TableHeader>
                  <TableBody>
                    {rows.map((r) => (
                      <TableRow key={r.gw}>
                        <TableCell className="font-medium">GW {r.gw}</TableCell>
                        <TableCell className="text-right">{formatNumber(r.tc)}</TableCell>
                        <TableCell className="text-right">{formatNumber(r.bb)}</TableCell>
                        <TableCell className="text-right">{formatNumber(r.fh)}</TableCell>
                        <TableCell className="text-right">{formatNumber(r.wc)}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{r.dgw?.length ? r.dgw.join(", ") : "-"}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{r.bgw?.length ? r.bgw.join(", ") : "-"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          ) : null}
        </TabsContent>

        {!isBeginner ? (
          <TabsContent value="model" className="space-y-4">
            <Card>
              <CardHeader><CardTitle>Kalibrasi proyeksi</CardTitle></CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between"><span className="text-muted-foreground">Status</span><Badge variant={calibration.enabled ? "success" : "muted"}>{calibration.enabled ? "AKTIF" : "nonaktif"}</Badge></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Metode</span><span>{calibration.method ?? "-"}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">MAE CV mentah → terkalibrasi</span><span>{formatNumber(calibration.raw_mae_cv, 3)} → {formatNumber(calibration.calibrated_mae_cv, 3)}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Perbaikan</span><span>{formatNumber(calibration.improvement_pct, 2)}%</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Sampel</span><span>{calibration.n ?? "-"}</span></div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle>Machine learning</CardTitle></CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between"><span className="text-muted-foreground">Status</span><Badge variant={ml.enabled ? "success" : "warning"}>{ml.enabled ? "AKTIF" : "eksperimental"}</Badge></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Sampel / GW</span><span>{ml.n_samples ?? "-"} / {ml.n_gws ?? "-"}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">GBR MAE vs formula</span><span>{formatNumber(ml.gbr_mae, 3)} vs {formatNumber(ml.formula_mae, 3)}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Improvement</span><span>{formatNumber(ml.improvement_pct, 1)}%</span></div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle>Adaptive weights</CardTitle></CardHeader>
              <CardContent className="text-sm text-muted-foreground">
                {data.adaptive?.metrics?.enabled
                  ? `Aktif · MAE ${formatNumber(data.adaptive.metrics.default_mae, 3)} → ${formatNumber(data.adaptive.metrics.tuned_mae, 3)}`
                  : "Nonaktif. Bobot default dipakai karena validasi holdout belum cukup baik."}
              </CardContent>
            </Card>
          </TabsContent>
        ) : null}
      </Tabs>
    </div>
  );
}
