# FPL Dashboard

Tools bantu bermain Fantasy Premier League (FPL) berbasis data publik resmi FPL API. Membantu Anda memilih kapten, menentukan transfer, dan mengoptimasi line-up setiap Gameweek.

## Fitur

- **🎯 Rencana Aksi (halaman baru)** - semua keputusan GW ini dalam satu layar: XI EV-optimal (aturan auto-sub persis), kapten & wakil EV, urutan bench, rencana transfer multi-GW (FT & hit), estimasi EV chip (TC/BB/FH/WC), dan peringatan status pemain
- **Beranda** - Info Gameweek & deadline, rekomendasi kapten (+ **EV Monte Carlo**), tabel FDR (tingkat kesulitan lawan), top-10 proyeksi poin, ringkasan akurasi model
- **Player Explorer** - Jelajahi 600+ pemain, filter posisi/tim/harga/status, detail proyeksi + tren form 8 GW terakhir, kolom xGI/90 dan CS probability
- **Kapten & Transfer** - Kandidat kapten terbaik (**+ simulasi Monte Carlo kapten/wakil berbasis EV & risiko blank**), value picks (poin per £1juta), fixture ticker (FDR 6 GW ke depan), differential picks, pemain berisiko cedera
- **Team Builder** - Masukkan skuad 15 pemain Anda (budget £100m), optimasi XI terbaik (tampilan lapangan) + kapten + saran transfer multi-GW + hit calculator
- **Chip Strategi** - Rekomendasi kapan memakai Triple Captain, Bench Boost, Wildcard, & Free Hit — termasuk chip sequence planner
- **Akurasi Model** - Evaluasi akurasi proyeksi vs skor aktual: MAE, RMSE, breakdown per posisi & FDR, saran penyesuaian bobot
- **Rencana 3 GW (Team Builder)** - Proyeksi & XI terbaik untuk 3 Gameweek ke depan; XI boleh dirotasi gratis, transfer diminimalkan
- **`python recommend.py`** - Optimasi otomatis skuad terbaik dalam budget (£100m) untuk GW berjalan (`--gws 3` untuk optimasi 3 GW sekaligus)
- **`python validate.py`** - Validasi menyeluruh: optimalitas solver vs brute-force, benchmark vs strategi pandit & 300 tim acak, sensitivitas proyeksi, legalitas rencana transfer planner, status kalibrasi
- **`python tests/test_core.py`** - Test inti: aturan auto-sub, batas probabilitas DefCon, harga jual, XI value vs brute-force, kalibrasi

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
- **DefCon (perpindahan terbaru)**: ekspektasi poin kontribusi defensif ditambahkan per laga (lihat bagian DefCon di bawah)
- **ep_next**: proyeksi poin resmi dari FPL itu sendiri
- Pemain yang timnya tidak bertanding (bye) tidak diproyeksikan

## Poin Kontribusi Defensif (DefCon) — Fitur 2026/27

Aturan resmi: **DEF 10+ CBIT** atau **MID/FWD 12+ CBIRT** dalam satu laga = **+2 poin** (maks 2 per laga; GK tidak eligible). Ini fitur tetap sejak 2025/26 dan sangat besar pengaruhnya (mis. Tarkowski ≈ 11 aksi/90 → ±60% peluang tiap laga).

- `fpl/defcon.py` memodelkan peluang kena threshold dengan **Gamma-Poisson (negative binomial)**:
  - memakai jumlah aksi per laga dari riwayat `element-summary` (`player_history`, cache 6 jam);
  - fallback ke rate musiman `defensive_contribution_per_90` dengan *shrinkage* ke rata-rata posisi (anti-noise sampel kecil);
  - dikalikan ekspektasi menit main → `p_hit` per laga.
- Terintegrasi di **model proyeksi** (`dc_bonus = 2 × p_hit`), **horizon 3-GW**, dan **simulator Monte Carlo** (event DefCon disimulasikan per laga).
- Tampil sebagai kolom **DC%** di Player Explorer dan di alasan proyeksi.
- Jalankan **backfill riwayat pemain** (tombol di halaman Rencana Aksi) agar estimasi berbasis aksi per laga; tanpa itu, fallback musiman tetap dipakai.

## Kekuatan Tim Dinamis (bukan Hanya FDR Statis)

Rating kesulitan FPL (`strength_*`) sering 0 di awal musim dan tidak mencerminkan
kekuatan aktual. Karena itu model memakai **indeks kekuatan rolling dari hasil
nyata** (`fpl/teamform.py`):

- Gol dicetak/dikemasukan per tim dari fixture yang sudah selesai, di-smooth ke
  rata-rata liga (anti-overreaction 1-2 laga), lalu dinormalisasi (rata-rata = 1.0).
- **Fixture multiplier dinamis**: rasio attack tim vs defence lawan → koreksi
  perkalian di sekitar multiplier FDR (bobot data aktual naik seiring jumlah laga).
- **CS probability terkali-brasi**: model `exp(-λ)` dengan λ = ekspektasi gol
  lawan (L kandang/tandang × attack lawan × kebocoran pertahanan tim), diskalakan
  ke clean-sheet rate aktual liga — menggantikan rasio linier lama.
- Degradasi aman: tanpa data cukup, semua kembali ke perilaku FDR lama.

## Simulasi Monte Carlo — Kapten, Wakil, XI & EV (Bukan Sekadar Proyeksi)

`fpl/simulator.py` (v2) mensimulasikan ribuan skenario Gameweek berikutnya:

- Gol per laga ~ Poisson(λ) dari kekuatan tim dinamis; **pencetak gol dialokasikan
  via share xG/90** (bukan xGI gabungan), **assist via share xA/90** (tanpa
  self-assist); **penalti** mengikuti `penalties_order` (konversi 78%, penalti
  gagal bisa jadi *save* — GK +5); **kartu kuning/merah** (probabilitas per
  posisi) dan **DefCon** ikut disimulasikan; menit main dari expected-minutes
  per pemain (`player_history`) dengan fallback musiman; clean sheet, saves &
  bonus (draw berbobot, ikut sinyal DefCon) disimulasikan.
- **Kapten & Wakil**: EV kapten = 2× poin bila kapten main; bila blank → 2× poin
  wakil (VC) yang otomatis menggantikannya.
- **XI & urutan bench EV-optimal dengan aturan auto-sub resmi**: setelah satu
  simulasi skuad, semua kombinasi formasi dievaluasi *setelah* auto-sub
  (GK↔GK, urutan bench 1-3, formasi tetap valid) — XI dipilih dari **EV**, bukan
  jumlah proyeksi (biasanya +1..4 poin/GW).
- Output: EV per kandidat kapten, peluang main/blank, rentang p10–p90, EV XI,
  EV tiap pemain bench.
- Ditampilkan di **Beranda** (ringkas), **Kapten & Transfer** (detail), dan
  **Rencana Aksi** (XI + bench + kapten final), memakai skuad tersimpan Anda.
- Rencana 3 GW (`horizon.py`) konsisten dengan model utama: bobot aktif
  (adaptive tuning) + multiplier dinamis + komponen sinyal yang sama +
  **mean-reversion form** per jarak GW (form panas/dingin mengarah balik ke PPG).

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

## Rencana Aksi — Halaman Keputusan Gameweek

Halaman **🎯 Rencana Aksi** (paling atas di sidebar) merangkum semua keputusan GW berikutnya:

1. **XI EV-optimal** dengan aturan auto-sub + formasi terbaik + **kapten & wakil berbasis EV** (termasuk risiko blank dan rentang p10–p90).
2. **Urutan bench** final (GK cadangan slot 4) beserta EV per pemain bench.
3. **Rencana transfer multi-GW** dengan FT, hit, harga jual, bank nyata dari tim tersinkron.
4. **Estimasi EV chip** (TC/BB/FH/WC) untuk GW ini + status chip 2 set (set-1 hangus di GW19).
5. **Peringatan** status cedera/diragukan dan bench berproyeksi tinggi.

Tombol **backfill riwayat pemain** juga ada di halaman ini (sekali jalan, ±200 pemain, cache 6 jam).

## Perencanaan Transfer (FT, Hit & Harga Jual)

`fpl/planner.py` menggantikan heuristik lama dengan keputusan legal & optimal:

- **State nyata tim Anda**: free transfer dihitung dari riwayat transfer musim ini
  (1/GW, rollover maks 5; GW chip tidak menambah FT — sesuai aturan resmi dan
  terverifikasi dari riwayat Anda), bank, serta **harga jual** tiap pemain
  (`beli + ½ profit`, dibulatkan ke bawah — dari endpoint transfers).
- **Beam search 4 GW**: kombinasi 0–2 transfer per GW dengan keputusan hit
  (−4/transfer ekstra), patuh limit **3 pemain/klub**, struktur **2/5/5/3**,
  dan budget nyata; output = rencana per GW + gain vs "tahan tanpa transfer".
- **Wildcard/skuad awal via MILP** (`scipy`): optimasi exact 15 pemain di bawah
  semua batasan FPL — dipakai untuk estimasi EV Wildcard & Free Hit.
- `fpl/transfer.py` (fallback lama) kini **sell-price aware** dan mengecek limit klub.

## Chip Berbasis EV (2 Set per Musim)

`fpl/chips_ev.py` menghitung nilai chip memakai simulator & planner:

- **TC** = EV poin ekstra dari 3× kapten alih-alih 2× (termasuk asuransi wakil).
- **BB** = EV total 15 pemain − EV XI auto-sub (persis poin tambahan dari bench).
- **FH** = XI terbaik pasar (MILP, budget harga jual + bank) − XI skuad sekarang.
- **WC** = total horizon skuad optimal − skuad sekarang (harga jual + bank).
- Aturan 2026/27: **2 set chip** (1 per paruh musim), **1 chip per GW**,
  set pertama hangus di deadline GW19.

## Kalibrasi Proyeksi & Anti-Overfit

`fpl/calibration.py` memeriksa apakah proyeksi model bias secara sistematis:

- Fit per posisi `aktual ≈ a + b × proyeksi` dengan shrinkage ke identitas
  (sampel kecil tidak bisa mendistorsi) — memakai **proyeksi mentah** sebagai
  input agar tidak ada umpan balik.
- Validasi **leave-one-Gameweek-out**: kalibrasi hanya AKTIF bila MAE
  out-of-sample membaik ≥ 0.5%. Selama belum terbukti, proyeksi mentah yang dipakai.
- Snapshot fitur lengkap (form, ppg, sinyal, DefCon, CS, menit, multiplier)
  disimpan di `data/accuracy.json` untuk tuning/analisis lanjutan.
- Status & tombol "Fit Kalibrasi" ada di halaman **Akurasi Model**.

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
