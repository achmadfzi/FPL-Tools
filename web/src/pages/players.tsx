import { useMemo, useState } from "react";
import { Search, SlidersHorizontal } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, Input, Select } from "@/components/ui/primitives";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader, PlayerAvatar, TeamBadge } from "@/components/shared";
import { usePlayers } from "@/lib/api";
import { fdrStyle, formatNumber, formatPct, formatPrice } from "@/lib/utils";
import type { Player } from "@/lib/types";

const STATUS: Record<string, string> = {
  a: "Tersedia",
  d: "Diragukan",
  i: "Cedera",
  s: "Suspended",
  u: "Tidak tersedia",
  n: "Tidak masuk skuad",
};

export default function PlayersPage({ isBeginner }: { isBeginner: boolean }) {
  const { data, isLoading, error } = usePlayers();
  const [query, setQuery] = useState("");
  const [pos, setPos] = useState("ALL");
  const [team, setTeam] = useState("ALL");
  const [sort, setSort] = useState("proj");
  const [lastFilter, setLastFilter] = useState("ALL");
  const [detail, setDetail] = useState<Player | null>(null);

  const teams = useMemo(() => Array.from(new Set((data ?? []).map((p) => p.team))).sort(), [data]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return [...(data ?? [])]
      .filter((p) => (pos === "ALL" ? true : p.pos === pos))
      .filter((p) => (team === "ALL" ? true : p.team === team))
      .filter((p) => {
        if (lastFilter === "ALL") return true;
        const pts = p.last_points ?? 0;
        if (lastFilter === "200") return pts >= 200;
        if (lastFilter === "150") return pts >= 150;
        if (lastFilter === "100") return pts >= 100;
        return pts <= 0;
      })
      .filter((p) => (!q ? true : p.name.toLowerCase().includes(q) || (p.team_name ?? "").toLowerCase().includes(q)))
      .sort((a, b) => {
        const key = sort as keyof Player;
        const av = Number(a[key] ?? 0);
        const bv = Number(b[key] ?? 0);
        return bv - av;
      });
  }, [data, query, pos, team, sort, lastFilter]);

  if (isLoading) return <div className="py-20 text-center text-sm text-muted-foreground">Memuat pemain...</div>;
  if (error) return <div className="py-20 text-center text-sm text-destructive">Gagal memuat: {String(error)}</div>;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Cari Pemain"
        description="Filter pemain, bandingkan proyeksi, lalu klik satu pemain untuk detail."
      >
        <Badge variant="secondary">{filtered.length} pemain</Badge>
      </PageHeader>

      <Card>
        <CardContent className="flex flex-col gap-3 p-4 lg:flex-row lg:items-center">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Cari nama pemain atau tim..."
              className="pl-9"
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Select value={pos} onChange={(e) => setPos(e.target.value)} className="w-28">
              <option value="ALL">Semua posisi</option>
              {["GK", "DEF", "MID", "FWD"].map((p) => <option key={p}>{p}</option>)}
            </Select>
            <Select value={team} onChange={(e) => setTeam(e.target.value)} className="w-32">
              <option value="ALL">Semua tim</option>
              {teams.map((t) => <option key={t}>{t}</option>)}
            </Select>
            <Select value={lastFilter} onChange={(e) => setLastFilter(e.target.value)} className="w-40">
              <option value="ALL">Musim lalu: semua</option>
              <option value="200">Bintang ≥200</option>
              <option value="150">Sangat baik ≥150</option>
              <option value="100">Baik ≥100</option>
              <option value="NONE">Tanpa riwayat</option>
            </Select>
            <Select value={sort} onChange={(e) => setSort(e.target.value)} className="w-40">
              <option value="proj">Proyeksi</option>
              <option value="ep_next">Prediksi FPL</option>
              <option value="xgi90">xGI/90</option>
              <option value="form">Form</option>
              <option value="ppg">PPG</option>
              <option value="price">Harga</option>
              <option value="selected_by">Kepemilikan</option>
              <option value="last_points">Poin musim lalu</option>
              <option value="last_value">Value musim lalu</option>
              <option value="last_ppg">PPG musim lalu</option>
            </Select>
            <Button variant="outline" size="icon" aria-label="Filter">
              <SlidersHorizontal className="h-4 w-4" />
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Pemain</TableHead>
                <TableHead>Pos</TableHead>
                <TableHead className="text-right">Harga</TableHead>
                <TableHead className="text-right">Proyeksi</TableHead>
                <TableHead className="text-right">Prediksi FPL</TableHead>
                <TableHead className="text-right">Main</TableHead>
                <TableHead>Lawan</TableHead>
                {!isBeginner ? (
                  <>
                    <TableHead className="text-right">xGI/90</TableHead>
                    <TableHead className="text-right">DC%</TableHead>
                    <TableHead className="text-right">CS%</TableHead>
                    <TableHead className="text-right">Poin Lalu</TableHead>
                    <TableHead className="text-right">PPG Lalu</TableHead>
                    <TableHead className="text-right">Form</TableHead>
                    <TableHead className="text-right">PPG</TableHead>
                    <TableHead className="text-right">Kepemilikan</TableHead>
                  </>
                ) : null}
                <TableHead className="text-right">FDR</TableHead>
                <TableHead className="text-right">Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.slice(0, 300).map((p) => (
                <TableRow key={p.id} className="cursor-pointer" onClick={() => setDetail(p)}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <PlayerAvatar name={p.name} team={p.team} size="sm" />
                      <div>
                        <div className="text-sm font-medium">{p.name}</div>
                        <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
                          <TeamBadge team={p.team} /> {p.team_name}
                        </div>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell><Badge variant="secondary">{p.pos}</Badge></TableCell>
                  <TableCell className="text-right text-sm">{formatPrice(p.price)}</TableCell>
                  <TableCell className="text-right font-bold text-primary">{formatNumber(p.proj)}</TableCell>
                  <TableCell className="text-right text-sm">{formatNumber(p.ep_next)}</TableCell>
                  <TableCell className="text-right text-sm">{formatNumber(p.chance, 0)}%</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {p.opponent ?? "-"} {p.is_home ? "(H)" : p.is_home === false ? "(A)" : ""}
                  </TableCell>
                  {!isBeginner ? (
                    <>
                      <TableCell className="text-right text-sm">{formatNumber(p.xgi90, 2)}</TableCell>
                      <TableCell className="text-right text-sm">{formatPct(p.dc_prob)}</TableCell>
                      <TableCell className="text-right text-sm">{formatPct(p.cs_prob)}</TableCell>
                      <TableCell className="text-right text-sm">{formatNumber(p.last_points, 0)}</TableCell>
                      <TableCell className="text-right text-sm">{formatNumber(p.last_ppg, 2)}</TableCell>
                      <TableCell className="text-right text-sm">{formatNumber(p.form, 2)}</TableCell>
                      <TableCell className="text-right text-sm">{formatNumber(p.ppg, 2)}</TableCell>
                      <TableCell className="text-right text-sm">{formatNumber(p.selected_by)}%</TableCell>
                    </>
                  ) : null}
                  <TableCell className="text-right">
                    <span
                      className="inline-block min-w-6 rounded px-1.5 py-0.5 text-xs font-bold"
                      style={fdrStyle(p.fdr)}
                    >
                      {p.fdr ?? "-"}
                    </span>
                  </TableCell>
                  <TableCell className="text-right">
                    <Badge variant={p.status === "a" ? "success" : p.status === "d" ? "warning" : "destructive"}>
                      {STATUS[p.status ?? "a"] ?? p.status}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {filtered.length > 300 ? (
            <div className="border-t p-3 text-center text-xs text-muted-foreground">
              Menampilkan 300 dari {filtered.length} pemain. Persempit filter untuk melihat sisanya.
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Dialog open={!!detail} onOpenChange={(open) => !open && setDetail(null)}>
        <DialogContent>
          {detail ? (
            <>
              <DialogHeader>
                <div className="flex items-center gap-3">
                  <PlayerAvatar name={detail.name} team={detail.team} size="lg" />
                  <div>
                    <DialogTitle>{detail.name}</DialogTitle>
                    <DialogDescription>
                      {detail.team_name} · {detail.pos} · {formatPrice(detail.price)}
                    </DialogDescription>
                  </div>
                </div>
              </DialogHeader>
              <div className="grid grid-cols-2 gap-3">
                <Stat label="Perkiraan poin" value={formatNumber(detail.proj)} />
                <Stat label="Prediksi FPL" value={formatNumber(detail.ep_next)} />
                <Stat label="Peluang main" value={`${formatNumber(detail.chance, 0)}%`} />
                <Stat label="Lawan" value={`${detail.opponent ?? "-"} (${detail.is_home ? "H" : detail.is_home === false ? "A" : "-"}) · FDR ${detail.fdr ?? "-"}`} />
                <Stat label="Status" value={STATUS[detail.status ?? "a"] ?? detail.status ?? "-"} />
                {!isBeginner ? (
                  <>
                    <Stat label="xGI/90" value={formatNumber(detail.xgi90, 2)} />
                    <Stat label="DefCon chance" value={formatPct(detail.dc_prob)} />
                    <Stat label="CS chance" value={formatPct(detail.cs_prob)} />
                    <Stat label="Kepemilikan" value={`${formatNumber(detail.selected_by)}%`} />
                    <Stat label="Form" value={formatNumber(detail.form, 2)} />
                    <Stat label="PPG" value={formatNumber(detail.ppg, 2)} />
                    <Stat label="Poin musim lalu" value={formatNumber(detail.last_points, 0)} />
                    <Stat label="PPG musim lalu" value={formatNumber(detail.last_ppg, 2)} />
                  </>
                ) : null}
              </div>
              <p className="text-sm leading-relaxed text-muted-foreground">
                Proyeksi adalah perkiraan poin rata-rata, bukan jaminan. Cek berita cedera dan peluang main sebelum memilih.
              </p>
              {detail.news ? (
                <div className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{detail.news}</div>
              ) : null}
            </>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-lg border p-3">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 font-semibold">{value}</div>
    </div>
  );
}
