# FPL Dashboard

Tools bantu bermain Fantasy Premier League (FPL) berbasis data publik resmi FPL API. Membantu Anda memilih kapten, menentukan transfer, dan mengoptimasi line-up setiap Gameweek.

## Fitur

- **Beranda** - Info Gameweek & deadline, rekomendasi kapten, tabel FDR (tingkat kesulitan lawan), top-10 proyeksi poin, ringkasan akurasi model
- **Player Explorer** - Jelajahi 600+ pemain, filter posisi/tim/harga/status, detail proyeksi + tren form 8 GW terakhir, kolom xGI/90 dan CS probability
- **Kapten & Transfer** - Kandidat kapten terbaik, value picks (poin per £1juta), fixture ticker (FDR 6 GW ke depan), differential picks, pemain berisiko cedera
- **Team Builder** - Masukkan skuad 15 pemain Anda (budget £100m), optimasi XI terbaik (tampilan lapangan) + kapten + saran transfer multi-GW + hit calculator
- **Chip Strategi** - Rekomendasi kapan memakai Triple Captain, Bench Boost, Wildcard, & Free Hit — termasuk chip sequence planner
- **Akurasi Model** - Evaluasi akurasi proyeksi vs skor aktual: MAE, RMSE, breakdown per posisi & FDR, saran penyesuaian bobot
- **Rencana 3 GW (Team Builder)** - Proyeksi & XI terbaik untuk 3 Gameweek ke depan; XI boleh dirotasi gratis, transfer diminimalkan
- **`python recommend.py`** - Optimasi otomatis skuad terbaik dalam budget (£100m) untuk GW berjalan (`--gws 3` untuk optimasi 3 GW sekaligus)
- **`python validate.py`** - Validasi menyeluruh: optimalitas solver vs brute-force, benchmark vs strategi pandit & 300 tim acak, sensitivitas proyeksi

## Cara Menjalankan

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Buka `http://localhost:8501` di browser.

## Cara Kerja Mesin Prediksi (Enhanced)

Proyeksi poin per pemain untuk GW berikutnya menggunakan model enhanced:

```
base = 0.45 × form + 0.25 × ppg + 0.30 × xGI_signal
cs_bonus = cs_probability × cs_points_per_pos × 0.15
threat_bonus = (threat_per_game / 40.0) × 0.10
base_adj = base + cs_bonus + threat_bonus
per_fixture = base_adj × FDR_mult × home_mult
final = (0.50 × sum(per_fixture) + 0.35 × ep_next + 0.15 × ep_next_safety) × peluang_bermain
```

- **xGI Signal**: Expected Goal Involvements per 90 menit, dinormalisasi ke skala form
- **CS Probability**: Probabilitas clean sheet berdasarkan rasio kekuatan defence vs attack lawan (range 5%–55%)
- **CS Points per Pos**: GK/DEF = 4 poin, MID = 1 poin, FWD = 0 poin
- **Threat Score**: Sinyal serangan pemain (shot-based), dinormalisasi per game
- **Faktor FDR**: 1.12 (lawan sangat mudah) s/d 0.85 (lawan sangat sulit)
- **Kandang** ×1.08, **tandang** ×0.93
- **DGW**: Jika tim main 2 laga, proyeksi dijumlah per fixture (bukan ×1.9 flat)
- **Peluang bermain**: dari `chance_of_playing_next_round` (pemain cedera/suspended otomatis dikeluarkan)
- **ep_next**: proyeksi poin resmi dari FPL itu sendiri
- Pemain yang timnya tidak bertanding (bye) tidak diproyeksikan

## Faktor Reliabilitas (Menit Bermain + Kepercayaan Komunitas)

Proyeksi pemain disesuaikan dengan **sinyal kepercayaan tertinggi** dari dua sumber, agar pemain baru berkualitas (mis. performa pramusim bagus, dilirik komunitas) tidak dihukum berlebihan, tetapi pemain "misterius" tetap diwaspadai:

1. **Riwayat menit musim lalu** (`history_past`): ≥2000 → ×1.0, 1500–1999 → ×0.95, 1000–1499 → ×0.88, 500–999 → ×0.72, <500 → ×0.5
2. **Kepercayaan komunitas** (`selected_by_percent`): 0.6 + 0.4 × (kepemilikan/20), maks ×1.0 — pemain dengan kepemilikan ≥20% mendapat kepercayaan hampir penuh

`faktor akhir = max(faktor menit, faktor komunitas)`. Label ditampilkan: "Mapan", "Cukup mapan", "Risiko menit", "Dipercaya komunitas", "Pemain baru / belum terbukti". Data di-cache di `data/reliability.json` (TTL 24 jam).

## Acuan Musim Lalu (history_past)

Setiap pemain kini memiliki statistik musim lalu (2025/26) sebagai acuan, diambil dari `element-summary/history_past` (cache `data/paststats.json`, TTL 24 jam):

- **Poin total, PPG, gol, assist, clean sheet, bonus** — tampil di detail Player Explorer, tabel explorer (sortir + filter "Bintang ≥200 poin"), dan Beranda.
- **Bintang Musim Lalu** (Beranda): top-10 poin musim lalu dengan proyeksi GW ini; badge **DOUBLE** = poin tinggi musim lalu + proyeksi tinggi sekarang.
- **Value Musim Lalu**: poin per £1 juta (harga ≤ £11.0m) — kandidat budget pick.
- **Kapten & Transfer**: section "Acuan Musim Lalu" — top poin & value picks.

Catatan: statistik musim lalu hanyalah acuan — kombinasi dengan proyeksi GW ini yang memberi sinyal terkuat.

## Strategi Chip (TC, BB, WC, FH)

- **Deteksi Double Gameweek (DGW)** & Blank GW (BGW) dari jadwal 38 GW di FPL API.
- **TC skor** = estimasi proyeksi kapten terbaik di GW itu (×1.9 bila timnya main 2 laga).
- **BB skor** = estimasi poin 4 cadangan (×1.8 bila pemainnya main 2 laga), dihitung dari skuad yang tersimpan.
- **WC skor** = value Wildcard berdasarkan fixture swing (laga mudah 3 GW), underperformers di skuad, dan peluang DGW.
- **FH skor** = value Free Hit berdasarkan jumlah tim yang tidak bermain (BGW) — semakin banyak tim blank, semakin berharga FH.
- **Chip Sequence Planner** = urutan optimal penggunaan semua chip sepanjang musim, menghindari konflik (TC & BB di GW sama).
- Faktor bonus: jumlah laga mudah (FDR ≤ 2) per GW.
- Estimasi GW mendatang memakai proyeksi pemain saat ini sebagai patokan — perbarui menjelang deadline.

## Transfer Intelligence

- **Multi-GW Transfers**: Saran transfer berdasarkan total gain 3 GW ke depan, bukan hanya 1 GW.
- **Hit Calculator**: Evaluasi apakah transfer -4 poin worth it (net gain setelah penalty > 0).
- **Fixture Ticker**: Tabel FDR 6 GW ke depan per tim, diurutkan dari run paling mudah — untuk keputusan transfer jangka panjang.
- **Differential Picks**: Pemain dengan kepemilikan < 5% tapi proyeksi tinggi — senjata rahasia untuk naik rank.
- **Fixture Swing Badge**: Indikator pemain yang akan menghadapi serangkaian lawan mudah.

## Akurasi Model (Accuracy Tracking)

- **Auto-save**: Proyeksi setiap pemain disimpan otomatis sebelum deadline GW.
- **Fetch Actuals**: Setelah GW selesai, skor aktual diambil dari FPL Live API (`/api/event/{id}/live/`).
- **Metrik**: MAE (Mean Absolute Error), RMSE, breakdown per posisi (GK/DEF/MID/FWD) dan per FDR (1-5).
- **Trend**: Chart akurasi sepanjang musim — apakah model semakin baik?
- **Weight Suggestions**: Setelah 3+ GW, sistem otomatis menyarankan penyesuaian bobot jika FDR terlalu agresif atau CS bonus terlalu tinggi.
- Data di `data/accuracy.json`.

## Rencana Multi-Gameweek (Minimalkan Transfer)

- **Proyeksi GW berikutnya**: kualitas pemain saat ini (form/ppg/xGI) × FDR lawan GW itu × kandang/tandang × CS bonus (DGW dijumlah per fixture).
- **`python recommend.py --gws 3`**: mengoptimasi skuad untuk TOTAL proyeksi 3 GW sekaligus, lengkap dengan rencana XI & kapten per GW.
- **Team Builder** menampilkan rencana 3 GW untuk skuad Anda: total poin per GW, formasi, kapten, dan pemain berisiko (proyeksi GW2+GW3 rendah = kandidat transfer).
- Prinsip: rotasi XI antar GW **gratis** (tidak memakai transfer); transfer hanya dibutuhkan jika pemain keluar dari 15 skuad.

## Sumber Data

Semua data dari FPL API publik (tanpa login):
- `https://fantasy.premierleague.com/api/bootstrap-static/`
- `https://fantasy.premierleague.com/api/fixtures/`
- `https://fantasy.premierleague.com/api/element-summary/{id}/`
- `https://fantasy.premierleague.com/api/event/{id}/live/` (untuk accuracy tracking)

Data di-cache lokal di `data/cache.json` (TTL 1 jam). Klik **"Segarkan Data"** di Beranda untuk update manual.

## Mengikuti Gameweek Secara Otomatis

- Dashboard mendeteksi pergantian Gameweek otomatis dari flag `is_next` API FPL — saat deadline lewat, seluruh halaman langsung menampilkan GW berikutnya.
- **Auto-refresh** default setiap 10 menit (atur di sidebar: 5/10/15/30 menit atau mati). Selama halaman terbuka, data dan proyeksi diperbarui sendiri.
- Batas realtime: FPL API sendiri memperbarui proyeksi (ep_next), harga, dan status pemain secara bertahap (bukan realtime per detik), dan cache file maksimal 1 jam agar tidak membebani API FPL.

## Catatan

- Tidak ada tools yang bisa menjamin poin tinggi; tools ini menyediakan keputusan berbasis data terbaik.
- Skuad Team Builder tersimpan lokal di `data/squad.json`.
- Accuracy tracking dimulai sejak GW pertama data disimpan; butuh 3-5 GW untuk analisis bermakna.
