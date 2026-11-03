import { useMemo, useState } from "react";
import { BookOpen, Search } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/primitives";
import { PageHeader } from "@/components/shared";

const TERMS: Array<[string, string]> = [
  ["Proyeksi / EV / xP", "Perkiraan poin rata-rata. Bukan jaminan; bisa meleset sekitar 1–2 poin."],
  ["p10–p90", "Rentang realistis. 80% hasil biasanya berada di antara dua angka ini."],
  ["Peluang main", "Kemungkinan pemain bermain, dari status resmi FPL."],
  ["Risiko blank", "Peluang pemain tidak bermain sama sekali."],
  ["Haul", "Ledakan poin, biasanya 10+ poin."],
  ["FDR", "Tingkat kesulitan lawan: 1 = mudah, 5 = sulit."],
  ["xGI", "Peluang terlibat gol (gol atau assist) per 90 menit."],
  ["DefCon", "Bonus +2 dari aksi bertahan (tackle, intercept, clearance, dll.)."],
  ["CS / Clean Sheet", "Peluang tim tidak kebobolan."],
  ["FT", "Free transfer / transfer gratis."],
  ["Hit", "Penalti -4 poin untuk transfer ekstra."],
  ["TC / BB / WC / FH", "Triple Captain / Bench Boost / Wildcard / Free Hit."],
  ["DGW / BGW", "Double Gameweek (2 laga) / Blank Gameweek (tidak bermain)."],
  ["MAE", "Rata-rata meleset berapa poin dari hasil aktual."],
  ["Top-K", "Akurasi untuk 10/20 pemain teratas — yang biasanya dipilih."],
  ["Kalibrasi", "Apakah model terlalu tinggi atau terlalu rendah secara sistematis."],
  ["Backtest", "Uji model memakai data Gameweek yang sudah selesai."],
  ["Mode Pemula", "Menyembunyikan angka teknis dan menampilkan keputusan + alasan."],
  ["Mode Analis", "Menampilkan semua metrik, grafik, dan alat eksperimen."],
];

export default function GlossaryPage() {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return TERMS;
    return TERMS.filter(([term, meaning]) => term.toLowerCase().includes(q) || meaning.toLowerCase().includes(q));
  }, [query]);

  return (
    <div className="space-y-6">
      <PageHeader title="Kamus FPL" description="Arti singkat setiap istilah dan angka yang muncul di dashboard.">
        <BookOpen className="h-5 w-5 text-muted-foreground" />
      </PageHeader>
      <div className="relative max-w-xl">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Cari istilah..." className="pl-9" />
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {filtered.map(([term, meaning]) => (
          <Card key={term}>
            <CardContent className="p-4">
              <div className="font-semibold text-primary">{term}</div>
              <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{meaning}</p>
            </CardContent>
          </Card>
        ))}
      </div>
      {!filtered.length ? <p className="py-10 text-center text-sm text-muted-foreground">Tidak ada istilah yang cocok.</p> : null}
      <Card className="bg-muted/40">
        <CardContent className="space-y-2 p-4 text-sm text-muted-foreground">
          <p><strong className="text-foreground">Cara membaca angka:</strong></p>
          <p>1. Angka besar biasanya perkiraan poin, bukan janji.</p>
          <p>2. Hijau = aman, kuning = perlu dipantau, merah = risiko.</p>
          <p>3. Keyakinan Tinggi berarti data lengkap dan model/simulator setuju.</p>
        </CardContent>
      </Card>
    </div>
  );
}
