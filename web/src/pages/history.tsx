import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip as ReTooltip, XAxis, YAxis, ReferenceLine } from "recharts";
import { Activity, Crown, Landmark, TrendingUp, Trophy } from "lucide-react";
import { Alert } from "@/components/ui/primitives";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MetricCard, PageHeader } from "@/components/shared";
import { useHistory } from "@/lib/api";
import { formatNumber } from "@/lib/utils";

export default function HistoryPage() {
  const { data, isLoading, error } = useHistory();

  if (isLoading) return <div className="py-20 text-center text-sm text-muted-foreground">Memuat riwayat...</div>;
  if (error) return <Alert variant="destructive">Gagal memuat: {String(error)}</Alert>;
  if (!data?.available) {
    return (
      <div className="space-y-4">
        <PageHeader title="Riwayat Gameweek" description="Rank, poin, chip, dan performa kapten sepanjang musim." />
        <Alert>{data?.message ?? "Tim FPL belum tersinkron."}</Alert>
      </div>
    );
  }

  const rows = [...(data.gw_results ?? [])].sort((a, b) => a.gw - b.gw);
  const rankData = rows.map((r) => ({ gw: `GW${r.gw}`, rank: r.overall_rank }));
  const pointsData = rows.map((r) => ({ gw: `GW${r.gw}`, points: r.points, average: r.average }));
  const beats = rows.filter((r) => r.points > r.average).length;

  return (
    <div className="space-y-6">
      <PageHeader title="Riwayat Gameweek" description={`${data.team_name ?? "Tim FPL"} · ${data.manager_name ?? ""}`}>
        <Badge variant="secondary">Rank #{formatNumber(data.overall_rank, 0)}</Badge>
      </PageHeader>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Total poin" value={data.overall_points ?? "-"} icon={Trophy} />
        <MetricCard label="Overall rank" value={`#${formatNumber(data.overall_rank, 0)}`} icon={TrendingUp} />
        <MetricCard label="Mengalahkan rata-rata" value={`${beats}/${rows.length} GW`} hint={`${Math.round((beats / Math.max(rows.length, 1)) * 100)}%`} icon={Activity} accent="success" />
        <MetricCard label="Total hit" value={`-${data.total_hits ?? 0}`} hint={`Bench ${data.total_bench_pts ?? 0} poin`} icon={Landmark} accent="warning" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Perjalanan rank</CardTitle><p className="text-sm text-muted-foreground">Semakin ke atas, semakin baik.</p></CardHeader>
          <CardContent className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rankData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis dataKey="gw" tick={{ fontSize: 11 }} />
                <YAxis reversed tick={{ fontSize: 11 }} />
                <ReTooltip />
                <Line type="monotone" dataKey="rank" stroke="#37003c" strokeWidth={3} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Poin per GW</CardTitle><p className="text-sm text-muted-foreground">Hijau/merah dibanding rata-rata global.</p></CardHeader>
          <CardContent className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={pointsData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis dataKey="gw" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <ReTooltip />
                <ReferenceLine y={pointsData[0]?.average ?? 0} stroke="#94a3b8" strokeDasharray="4 4" />
                <Bar dataKey="points" fill="#37003c" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Nilai tim</CardTitle><p className="text-sm text-muted-foreground">Perkembangan harga skuad.</p></CardHeader>
          <CardContent className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rows.map((r) => ({ gw: `GW${r.gw}`, value: r.team_value }))} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis dataKey="gw" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} domain={["auto", "auto"]} />
                <ReTooltip />
                <Line type="monotone" dataKey="value" stroke="#0f766e" strokeWidth={3} dot={{ r: 2 }} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Poin di bench</CardTitle><p className="text-sm text-muted-foreground">Semakin tinggi, semakin banyak poin terbuang.</p></CardHeader>
          <CardContent className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={rows.map((r) => ({ gw: `GW${r.gw}`, bench: r.points_on_bench }))} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis dataKey="gw" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <ReTooltip />
                <Bar dataKey="bench" fill="#d97706" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Aktivitas transfer</CardTitle><p className="text-sm text-muted-foreground">Jumlah transfer per GW; batang merah = ada hit -4.</p></CardHeader>
        <CardContent className="h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows.map((r) => ({ gw: `GW${r.gw}`, transfers: r.transfers_made, hit: r.transfers_cost }))} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
              <XAxis dataKey="gw" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
              <ReTooltip />
              <Bar dataKey="transfers" fill="#4f46e5" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Dampak chip</CardTitle></CardHeader>
        <CardContent>
          {data.chip_impact?.length ? (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {data.chip_impact.map((c) => (
                <div key={`${c.chip}-${c.gw}`} className="rounded-lg border p-3">
                  <div className="flex items-center gap-2 text-sm font-semibold"><Crown className="h-4 w-4 text-primary" /> {c.chip}</div>
                  <div className="mt-1 text-xs text-muted-foreground">GW {c.gw} · {c.points} poin</div>
                  <div className={c.gain >= 0 ? "mt-1 text-sm font-semibold text-emerald-700" : "mt-1 text-sm font-semibold text-red-700"}>
                    {c.gain >= 0 ? "+" : ""}{formatNumber(c.gain)} vs rata-rata
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Belum ada chip yang digunakan.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
