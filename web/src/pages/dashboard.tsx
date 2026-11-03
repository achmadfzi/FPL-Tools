import { AlertTriangle, ArrowRight, ArrowRightLeft, CheckCircle2, Crown, Info, Puzzle, Target, TrendingUp } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Alert } from "@/components/ui/primitives";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/primitives";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ActionCard, ConfidenceBadge, PageHeader, PlayerAvatar, SectionTitle, TeamBadge } from "@/components/shared";
import { Pitch } from "@/components/pitch";
import { useDashboard } from "@/lib/api";
import { formatNumber, formatPct, formatPrice, formatDate, relativeTime, fdrStyle } from "@/lib/utils";
import type { XiPlayer } from "@/lib/types";

function XiTable({ players, captainId, viceName }: { players: XiPlayer[]; captainId?: number | null; viceName?: string | null }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Pemain</TableHead>
          <TableHead>Posisi</TableHead>
          <TableHead className="text-right">Peluang</TableHead>
          <TableHead className="text-right">Proyeksi</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {players.map((p) => (
          <TableRow key={p.id}>
            <TableCell>
              <div className="flex items-center gap-2">
                <PlayerAvatar name={p.name} team={p.team} size="sm" />
                <div>
                  <div className="flex items-center gap-1.5 text-sm font-medium">
                    {p.name}
                    {p.id === captainId ? <Badge variant="default">C</Badge> : null}
                    {p.name === viceName ? <Badge variant="warning">V</Badge> : null}
                  </div>
                  <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    <TeamBadge team={p.team} /> {p.pos} · {formatPrice(p.price)}
                  </div>
                </div>
              </div>
            </TableCell>
            <TableCell>
              <Badge variant="secondary">{p.pos}</Badge>
            </TableCell>
            <TableCell className="text-right text-sm">{formatPct(p.p_play)}</TableCell>
            <TableCell className="text-right font-semibold text-primary">{formatNumber(p.proj)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function BenchTable({ players }: { players: XiPlayer[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Slot</TableHead>
          <TableHead>Pemain</TableHead>
          <TableHead className="text-right">Proyeksi</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {players.map((p) => (
          <TableRow key={p.id}>
            <TableCell className="text-xs text-muted-foreground">{p.bench_slot ?? "-"}</TableCell>
            <TableCell>
              <div className="flex items-center gap-2">
                <PlayerAvatar name={p.name} team={p.team} size="sm" />
                <div>
                  <div className="text-sm font-medium">{p.name}</div>
                  <div className="text-[11px] text-muted-foreground">{p.team} · {p.pos}</div>
                </div>
              </div>
            </TableCell>
            <TableCell className="text-right font-medium">{formatNumber(p.proj)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function Loading() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-28 w-full rounded-xl" />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-56 rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-80 w-full rounded-xl" />
    </div>
  );
}

export default function DashboardPage({ isBeginner }: { isBeginner: boolean }) {
  const { data, isLoading, error } = useDashboard();
  const navigate = useNavigate();

  if (isLoading) return <Loading />;
  if (error) {
    return (
      <Alert variant="destructive">
        <div className="flex items-center gap-2 font-semibold">
          <AlertTriangle className="h-4 w-4" /> Gagal memuat dashboard
        </div>
        <p className="mt-1 text-sm">{String(error)}</p>
      </Alert>
    );
  }
  if (!data) return null;

  const { captain, transfer, chip, alerts } = data;
  const firstAlert = alerts[0];

  return (
    <div className="space-y-6">
      <div className="fpl-gradient relative overflow-hidden rounded-2xl p-6 text-white shadow-sm sm:p-8">
        <div className="relative z-10 max-w-3xl">
          <div className="text-xs font-bold uppercase tracking-[0.18em] text-purple-200">
            FPL HQ · Gameweek {data.gw.id}
          </div>
          <h1 className="mt-2 text-2xl font-extrabold tracking-tight sm:text-4xl">
            Keputusan Minggu Ini
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-purple-100">
            Kapten <strong>{captain.name}</strong>. {transfer.headline}. {chip.headline}. Semua angka adalah
            perkiraan, bukan jaminan.
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
            <Badge className="border-white/20 bg-white/10 text-white hover:bg-white/15">
              Deadline: {formatDate(data.gw.deadline)}
            </Badge>
            <Badge className="border-white/20 bg-white/10 text-white hover:bg-white/15">
              Data: {relativeTime(data.updated_at)}
            </Badge>
            <Badge className="border-white/20 bg-white/10 text-white hover:bg-white/15">
              Sumber: {data.source}
            </Badge>
          </div>
        </div>
        <div className="pointer-events-none absolute -right-10 -top-10 h-56 w-56 rounded-full bg-white/5 blur-2xl" />
        <div className="pointer-events-none absolute -bottom-16 right-24 h-48 w-48 rounded-full bg-fuchsia-400/10 blur-3xl" />
      </div>

      <PageHeader
        title="4 keputusan utama"
        description="Cukup baca kartu ini. Detail angka ada di halaman masing-masing."
      >
        {!isBeginner ? (
          <Badge variant="info">
            EV XI: {formatNumber(data.line.ev)} · formasi {data.line.formation?.join("-")}
          </Badge>
        ) : null}
      </PageHeader>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <ActionCard
          title="Kapten"
          icon={Crown}
          headline={captain.name}
          metric={formatNumber(captain.ev)}
          metricLabel="proyeksi poin ×2"
          meaning={`Dasar: proyeksi model ${formatNumber(captain.proj)} · peluang main ${formatPct(captain.p_play)} · wakil ${captain.vice ?? "-"}.`}
          confidence={captain.confidence}
          tone="info"
          footer={`EV simulator ${formatNumber(captain.sim_ev)} hanya pembanding.`}
          actionLabel="Bandingkan kandidat"
          onAction={() => navigate("/captain")}
        />
        <ActionCard
          title="Transfer"
          icon={ArrowRightLeft}
          headline={transfer.headline}
          metric={transfer.first_gw ? `${transfer.transfers.length} transfer` : `${data.squad.free_transfers} FT`}
          meaning={transfer.meaning}
          confidence={transfer.confidence}
          tone={transfer.hits > 0 ? "warn" : "good"}
          footer={`Bank £${data.squad.bank.toFixed(1)}m · gain ${formatNumber(transfer.gain)} poin`}
          actionLabel="Lihat rencana"
          onAction={() => navigate("/detail")}
        />
        <ActionCard
          title="Chip"
          icon={Puzzle}
          headline={chip.headline}
          metric={chip.metric}
          meaning={chip.meaning}
          confidence={chip.confidence}
          tone={chip.tone}
          footer="Satu chip per Gameweek."
          actionLabel="Kalender chip"
          onAction={() => navigate("/lab")}
        />
        <ActionCard
          title="Peringatan"
          icon={AlertTriangle}
          headline={firstAlert ? `${firstAlert.name} — ${firstAlert.label}` : "Skuad aman"}
          metric={alerts.length ? `${alerts.length} pemain` : "0 pemain"}
          meaning={firstAlert?.news || "Semua pemain di skuad berstatus tersedia penuh."}
          confidence={firstAlert?.is_out ? "Rendah" : "Tinggi"}
          tone={firstAlert?.is_out ? "bad" : firstAlert ? "warn" : "good"}
          footer="Cek berita resmi sebelum deadline."
          actionLabel="Lihat peringatan"
          onAction={() => navigate("/detail")}
        />
      </div>

      <Pitch
        xi={data.xi}
        bench={data.bench}
        captainId={captain.id}
        viceName={captain.vice}
        formation={data.line.formation}
        ev={data.line.ev}
        title="Starting XI — rekomendasi"
      />

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Info className="h-4 w-4 text-primary" /> Kenapa kapten ini?
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm leading-relaxed text-muted-foreground">
            Kombinasi proyeksi poin, peluang main, dan potensi haul. Wakil{" "}
            <strong className="text-foreground">{captain.vice}</strong> otomatis menggantikan kalau kapten tidak main.
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-emerald-600" /> Kenapa transfer ini?
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm leading-relaxed text-muted-foreground">
            {transfer.meaning} Kalau gain tidak cukup aman, lebih baik simpan FT.
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-amber-600" /> Checklist
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="list-decimal space-y-1.5 pl-4 text-sm text-muted-foreground">
              <li>Pasang kapten & wakil.</li>
              <li>Cek berita cedera terakhir.</li>
              <li>Pastikan urutan bench.</li>
              <li>Jangan transfer karena panik.</li>
            </ol>
          </CardContent>
        </Card>
      </div>

      <div>
        <SectionTitle
          title="Top 10 proyeksi"
          description="Pemain dengan perkiraan poin tertinggi minggu ini."
          action={
            <Button variant="outline" size="sm" onClick={() => navigate("/players")}>
              Cari pemain <ArrowRight className="ml-1 h-4 w-4" />
            </Button>
          }
        />
        <Card>
          <CardContent className="pt-4">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Pemain</TableHead>
                  <TableHead>Lawan</TableHead>
                  <TableHead className="text-right">Main</TableHead>
                  <TableHead className="text-right">Proyeksi</TableHead>
                  {!isBeginner ? <TableHead className="text-right">xGI/90</TableHead> : null}
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.top_players.slice(0, 10).map((p) => (
                  <TableRow key={p.id}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <PlayerAvatar name={p.name} team={p.team} size="sm" />
                        <div>
                          <div className="text-sm font-medium">{p.name}</div>
                          <div className="text-[11px] text-muted-foreground">{p.team} · {p.pos}</div>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {p.opponent ?? "-"} {p.is_home ? "(H)" : p.is_home === false ? "(A)" : ""} · FDR {p.fdr ?? "-"}
                    </TableCell>
                    <TableCell className="text-right text-sm">{formatNumber(p.chance, 0)}%</TableCell>
                    <TableCell className="text-right font-bold text-primary">{formatNumber(p.proj)}</TableCell>
                    {!isBeginner ? <TableCell className="text-right text-sm">{formatNumber(p.xgi90, 2)}</TableCell> : null}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      <div>
        <SectionTitle
          title="Tingkat kesulitan lawan (FDR)"
          description="1 = mudah, 5 = sulit. Semakin hijau, semakin ringan jadwalnya."
        />
        <Card>
          <CardContent className="grid grid-cols-2 gap-2 pt-4 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5">
            {data.fdr_grid.map((row) => (
              <div key={row.team} className="flex items-center justify-between rounded-lg border px-3 py-2">
                <div>
                  <div className="text-sm font-semibold">{row.team}</div>
                  <div className="text-[11px] text-muted-foreground">
                    vs {row.opponent} {row.is_home ? "(H)" : "(A)"}
                  </div>
                </div>
                <span
                  className="rounded-md px-2 py-1 text-xs font-bold"
                  style={fdrStyle(row.fdr)}
                >
                  {row.fdr ?? "-"}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Pemain dengan lawan mudah (FDR 1–2)</CardTitle>
            <p className="text-sm text-muted-foreground">Peluang main minimal 75%.</p>
          </CardHeader>
          <CardContent className="space-y-2">
            {data.easy_players.map((p) => (
              <div key={p.id} className="flex items-center justify-between rounded-lg border p-2">
                <div className="flex items-center gap-2">
                  <PlayerAvatar name={p.name} team={p.team} size="sm" />
                  <div>
                    <div className="text-sm font-medium">{p.name}</div>
                    <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
                      <TeamBadge team={p.team} /> vs {p.opponent} · {formatNumber(p.chance, 0)}% main
                    </div>
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-bold text-primary">{formatNumber(p.proj)}</div>
                  <div className="text-[10px] text-muted-foreground">FDR {p.fdr}</div>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Bintang musim lalu</CardTitle>
            <p className="text-sm text-muted-foreground">Poin musim lalu + proyeksi sekarang.</p>
          </CardHeader>
          <CardContent className="space-y-2">
            {data.last_stars.map((p) => (
              <div key={p.id} className="flex items-center justify-between rounded-lg border p-2">
                <div className="flex items-center gap-2">
                  <PlayerAvatar name={p.name} team={p.team} size="sm" />
                  <div>
                    <div className="text-sm font-medium">{p.name}</div>
                    <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
                      <TeamBadge team={p.team} /> {formatNumber(p.last_points, 0)} poin lalu · PPG {formatNumber(p.last_ppg, 2)}
                    </div>
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-bold text-primary">{formatNumber(p.proj)}</div>
                  <div className="text-[10px] text-muted-foreground">proyeksi</div>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Peringatan risiko rotasi</CardTitle>
            <p className="text-sm text-muted-foreground">Pemain dengan menit main tidak konsisten atau status diragukan.</p>
          </CardHeader>
          <CardContent className="space-y-2">
            {data.rotation_risks.length ? data.rotation_risks.map((r) => (
              <div key={`${r.name}-${r.team}`} className="rounded-lg border p-2">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium">{r.name} <span className="text-muted-foreground">({r.team}, {r.pos})</span></div>
                  <Badge variant={r.severity === "high" ? "destructive" : "warning"}>{r.severity}</Badge>
                </div>
                <div className="mt-1 text-[11px] text-muted-foreground">{r.reasons.join(" · ")}</div>
              </div>
            )) : <p className="text-sm text-emerald-700">Tidak ada risiko rotasi tinggi.</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Ringkasan akurasi model</CardTitle>
            <p className="text-sm text-muted-foreground">Seberapa jauh proyeksi meleset dari hasil aktual.</p>
          </CardHeader>
          <CardContent>
            {data.accuracy_summary ? (
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-lg border p-3">
                  <div className="text-[11px] uppercase text-muted-foreground">MAE GW {data.accuracy_summary.gw}</div>
                  <div className="mt-1 text-xl font-bold">{formatNumber(data.accuracy_summary.mae, 2)} poin</div>
                </div>
                <div className="rounded-lg border p-3">
                  <div className="text-[11px] uppercase text-muted-foreground">RMSE</div>
                  <div className="mt-1 text-xl font-bold">{formatNumber(data.accuracy_summary.rmse, 2)}</div>
                </div>
                <div className="rounded-lg border p-3">
                  <div className="text-[11px] uppercase text-muted-foreground">Bias</div>
                  <div className="mt-1 text-xl font-bold">{formatNumber(data.accuracy_summary.bias, 2)}</div>
                </div>
                <div className="rounded-lg border p-3">
                  <div className="text-[11px] uppercase text-muted-foreground">Top-10 MAE</div>
                  <div className="mt-1 text-xl font-bold">{formatNumber(data.accuracy_summary.top10?.mae, 2)}</div>
                </div>
                <p className="col-span-2 text-xs text-muted-foreground">
                  Dari {data.accuracy_summary.n_gws} GW. Semakin kecil, semakin akurat.
                </p>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Belum ada data akurasi.</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="bg-muted/40">
        <CardContent className="flex flex-col gap-2 p-4 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <span>
            Data history: {data.data_health.history_fresh}/{data.data_health.history_total} pemain segar ·{" "}
            {data.data_health.snapshot_available
              ? `snapshot ${formatNumber(data.data_health.snapshot_age_minutes, 0)} menit lalu`
              : "snapshot belum tersedia"}
          </span>
          <span className="flex items-center gap-2">
            <Info className="h-3.5 w-3.5" />
            Angka besar = perkiraan poin. Bukan jaminan.
          </span>
        </CardContent>
      </Card>
    </div>
  );
}
