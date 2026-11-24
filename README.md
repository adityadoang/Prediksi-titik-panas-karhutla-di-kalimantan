# Prediksi Intensitas Kebakaran Hutan Kalimantan (Fire Radiative Power) Menggunakan Jaringan Syaraf Tiruan (JST)

## 1. Latar Belakang & Konteks Berita Terkini
Topik ini diangkat berdasarkan rentetan peristiwa dan berita nasional terpanas di Indonesia saat ini:
- Terjadinya eskalasi kebakaran hutan dan lahan (karhutla) hebat di berbagai wilayah Kalimantan (Kalimantan Tengah, Barat, dan Selatan).
- Bencana kabut asap pekat lintas daerah yang mengganggu kesehatan masyarakat dan aktivitas penerbangan.
- Peristiwa jatuhnya helikopter Mi-17 penanganan karhutla di wilayah Seruyan, Kalimantan Tengah, yang menewaskan prajurit TNI saat menjalankan misi pemadaman.

Projek ini bertujuan membangun model Jaringan Syaraf Tiruan yang mampu memprediksi dan memetakan **intensitas pelepasan daya termal kebakaran** (*Fire Radiative Power* / FRP dalam satuan MegaWatt) dari titik api yang terdeteksi, sehingga mitigasi dan alokasi armada pemadam dapat diprioritaskan pada titik api yang paling berbahaya.

---

## 2. Sumber Data & Validitas
- **Sumber Data**: Data diambil langsung dari **API resmi NASA FIRMS** (bukan dari dataset Kaggle).
- **URL Endpoint API**: `https://firms.modaps.eosdis.nasa.gov/api/area/csv/` (menggunakan MAP_KEY publik yang tersedia di dokumentasi).
- **Sensor & Satelit**: VIIRS (*Visible Infrared Imaging Radiometer Suite*) 375m pada satelit Suomi-NPP (NOAA / S-NPP).
- **Lisensi Penggunaan**: CC0 Public Domain (kredit NASA FIRMS wajib dicantumkan).
- **Wilayah Cakupan**: Pulau Kalimantan (Bounding Box koordinat: 108.5°BT s/d 119.5°BT, -4.5°LS s/d 4.5°LU).
- **Periode Pengambilan Data**: 18 Oktober – 01 November 2026 (**15 hari** puncak musim kebakaran) — data ditarik per hari via `day_range=1`.
- **Jumlah Data Riil**: **35.826 sampel titik api** (terdeteksi satelit VIIRS), diambil langsung dari API real-time NASA (live satelit).
- **File Data Mentah**: `nasa_viirs_kalimantan_raw.csv` (35.827 baris; satu baris FRP 529,28 MW dibuang saat *cleaning* sebagai outlier).
- **File Data Bersih Siap Pakai**: `data_karhutla_kalimantan_cleaned.csv`

---

## 3. Fitur Dataset (Variabel JST)

Model memakai **23 fitur masukan**: 8 fitur sensor mentah + 15 fitur turunan hasil rekayasa fitur.

### 3.1 Fitur Sensor Dasar (8)
1. `latitude`: Koordinat garis lintang titik api.
2. `longitude`: Koordinat garis bujur titik api.
3. `bright_ti4`: Suhu kecerahan kanal termal I-4 (Kelvin) – mendeteksi radiasi api aktif.
4. `scan`: Resolusi spasial piksel searah pemindaian satelit.
5. `track`: Resolusi spasial piksel tegak lurus pemindaian satelit.
6. `bright_ti5`: Suhu kecerahan kanal termal I-5 (Kelvin) – reflektansi latar belakang.
7. `is_day`: Waktu deteksi satelit (`1` = Siang, `0` = Malam).
8. `confidence_score`: Tingkat keyakinan algoritma satelit (`1` = Low, `2` = Nominal, `3` = High).

### 3.2 Fitur Turunan Termal & Geometris (7)
| Fitur | Rumus | Alasan |
|---|---|---|
| `delta_t` | `bright_ti4 - bright_ti5` | Kontras suhu api terhadap latar (proksi energi radiasi) |
| `pixel_area` | `scan * track` | Luas piksel; FRP adalah energi per satuan luas |
| `ti4_day` | `bright_ti4 * is_day` | Interaksi suhu–waktu |
| `ti4_ti5_ratio` | `bright_ti4 / bright_ti5` | Kontras relatif terhadap kondisi latar |
| `delta_t_day` | `delta_t * is_day` | Kontras termal terkoreksi siang/malam |
| `conf_high` | `confidence_score == 3` | One-hot keyakinan deteksi tinggi |
| `conf_nominal` | `confidence_score == 2` | One-hot keyakinan nominal |

### 3.3 Fitur Temporal (4)
| Fitur | Alasan |
|---|---|
| `hour_frac` | Fraksi waktu akuisisi dalam sehari (siklus diurnal memengaruhi radiasi terdeteksi) |
| `hour_sin`, `hour_cos` | Encoding siklik agar jam 23:59 dan 00:01 berdekatan |
| `day_idx` | Indeks hari dalam periode; menangkap eskalasi/defusi episodik karhutla |

### 3.4 Fitur Kerapatan Hotspot (4)
Dihitung dari koordinat dan waktu saja (**tidak memakai target**, sehingga bebas *leakage*):
| Fitur | Alasan |
|---|---|
| `cell_density` | Jumlah hotspot di sel grid 0,5° pada hari yang sama |
| `neigh_density` | Jumlah hotspot blok 3×3 sel (klaster kebakaran besar) |
| `day_total` | Total hotspot se-Kalimantan pada hari tersebut (intensitas episode) |
| `neigh_density_norm` | Rasio klaster terhadap total harian |

### Target Variable ($y$)
- `frp` (*Fire Radiative Power*): Daya pancar radiasi panas api dalam satuan MegaWatt (MW). Saat pelatihan ditransformasi menjadi `log1p(frp)`.

---

## 4. Eksplorasi Data & Matriks Korelasi

![Matriks Korelasi Fitur](matriks_korelasi_fitur.png)

### Deskripsi Grafik Matriks Korelasi:
Heatmap **Korelasi Pearson** di atas menunjukkan kekuatan hubungan linier antar variabel (skala -1 hingga +1):
1. **`bright_ti4` vs `frp` (0.45)**: Korelasi positif cukup kuat. Suhu kecerahan kanal termal I-4 adalah indikator utama daya api (FRP).
2. **`is_day` vs `frp` (0.38)**: Deteksi siang hari cenderung memiliki intensitas daya api lebih tinggi (radiasi matahari + suhu permukaan lebih panas).
3. **`bright_ti5` vs `frp` (0.32)**: Kanal termal I-5 juga berkontribusi, meski tidak sekuat I-4.
4. **Variabel Spasial (`latitude`, `longitude`)**: Korelasi mendekati nol terhadap `frp` — intensitas kebakaran tidak ditentukan lokasi geografis semata, melainkan kondisi termal yang dideteksi sensor.

### Distribusi Target (dasar perbaikan model)
- **Median FRP 3,69 MW**, **mean 7,36 MW**, **maksimum 319,51 MW** → distribusi sangat *right-skewed*.
- Hanya **±1,4% sampel dengan error terbesar menyumbang 64% nilai MSE** pada model final.
- Segmen **CRITICAL (≥ 20 MW)** hanya **7,6%** dari data uji.

Implikasi: loss MSE pada skala asli didominasi segelintir titik api ekstrem, sehingga model cenderung *underestimate* pada titik api besar.

---

## 5. Metode & Arsitektur JST

### Framework & Akselerasi:
- **Framework**: **PyTorch** (`torch`, `torch.nn`, `torch.optim`)
- **Akselerasi**: **CUDA GPU** (NVIDIA GeForce RTX 5050 Laptop, 7.96 GB VRAM)

### Jenis Jaringan:
**Deep Multilayer Perceptron (MLP)** dengan algoritma pelatihan **Backpropagation**, dilengkapi `BatchNorm1d`.

### Struktur Lapisan (Network Architecture):
- **Input Layer**: 23 Neuron (8 fitur sensor + 15 fitur turunan, distandarisasi dengan `StandardScaler`).
- **Hidden Layer 1**: 256 Neuron → `BatchNorm1d` → `GELU` → Dropout `0.2`.
- **Hidden Layer 2**: 128 Neuron → `BatchNorm1d` → `GELU` → Dropout `0.1`.
- **Hidden Layer 3**: 64 Neuron → `BatchNorm1d` → `GELU` → Dropout `0.05`.
- **Output Layer**: 1 Neuron `Linear` → memprediksi `log1p(FRP)`.
- **Total parameter terlatih**: 48.257 bobot & bias.

### Hyperparameter Pelatihan:
- **Optimizer**: AdamW (`learning_rate = 0.001`, `weight_decay = 1e-4`).
- **Loss Function**: *Mean Squared Error* pada ruang `log1p(FRP)`.
- **Learning Rate Scheduler**: `ReduceLROnPlateau` (faktor 0.5, patience 10).
- **Early Stopping**: patience 30 epoch, maksimum 300 epoch → berhenti di **epoch 132**.
- **Batch Size**: 128.
- **Data Splitting**: 80% Data Latih & Validasi (22.928 latih, 5.732 validasi), 20% Data Uji Independen (7.166 sampel uji).

### Dua Teknik Kunci yang Menaikkan Skor:
1. **Target `log1p(FRP)`** — menstabilkan loss pada distribusi sangat menceng.
2. **Kalibrasi isotonic** — fungsi monotonik yang di-*fit* pada data **validasi** untuk mengoreksi bias `expm1` (prediksi mean terlalu rendah pada distribusi log-normal). Tanpa kalibrasi, MSE validasi JST mencapai 2.458; setelah kalibrasi menjadi **78,24**.

---

## 6. Metrik & Hasil Evaluasi Model

Model dievaluasi pada data uji independen (*Hold-out Test Set*) berisi **7.166 sampel** yang tidak pernah dilihat saat pelatihan maupun kalibrasi.

### 6.1 Hasil JST (Model Utama)

| Metrik Evaluasi | Baseline (8 fitur, raw MSE) | **JST Improved** | Perubahan |
|---|---|---|---|
| **Mean Squared Error (MSE)** | 73.2752 | **64.8233** | **−8,4519 (−11,5%)** |
| **Root Mean Squared Error (RMSE)** | 8.5601 MW | **8.0513 MW** | −0,5088 MW (−5,9%) |
| **Mean Absolute Error (MAE)** | 3.5324 MW | **3.4910 MW** | −0,0414 MW (−1,2%) |
| **R² Score** | 0.4658 | **0.5274** | **+0,0616** |

Median error absolut model final hanya **1,33 MW**, dengan rata-rata prediksi 7,347 MW vs rata-rata aktual 7,330 MW (bias hampir nol).

### 6.2 Benchmark Model Tree-Based (XGBoost) & Ensemble

Sebagai pembanding, pipeline identik dilatih dengan **XGBoost `reg:tweedie`** (cocok untuk target non-negatif yang sangat menceng). Bobot ensemble dipilih pada data **validasi**, bukan test.

| Model | MSE | RMSE | MAE | R² |
|---|---|---|---|---|
| Baseline (8 fitur, raw MSE) | 73.2752 | 8.5601 | 3.5324 | 0.4658 |
| **JST Improved + kalibrasi isotonic** | **64.8233** | **8.0513** | **3.4910** | **0.5274** |
| XGBoost (tweedie) | 55.9556 | 7.4803 | 3.0824 | 0.5920 |
| Ensemble JST 0.35 + XGB 0.65 | 56.1572 | 7.4938 | 3.1376 | 0.5906 |

**Interpretasi**: JST improved menurunkan MSE 11,5% dan menaikkan R² dari 0,466 → 0,527. Model tree-based masih lebih unggul (MSE 55,96; R² 0,592) — pola umum pada data tabular — sedangkan ensemble praktis setara dengan XGBoost (selisih 0,2 MSE). Model final dipilih berdasarkan MSE validasi terkecil, yaitu **ensemble JST 0.35 + XGB 0.65** (MSE validasi 72,52).

### 6.3 Performa per Band Intensitas FRP (Model Final)

| Band FRP | n Sampel | Proporsi | MAE (MW) | RMSE (MW) | Bias (MW) |
|---|---|---|---|---|---|
| LOW (< 8 MW) | 5.394 | 75,3% | 1,452 | 2,390 | +1,001 |
| MODERATE (8–20 MW) | 1.224 | 17,1% | 4,498 | 6,094 | +0,148 |
| CRITICAL (≥ 20 MW) | 548 | 7,6% | 16,691 | 24,396 | −13,634 |
| **Seluruh test** | **7.166** | **100%** | **3,138** | **7,494** | **−0,264** |

- **Akurasi status mitigasi** (LOW/MODERATE/CRITICAL): **81,61%**
- **Recall kelas CRITICAL (≥ 20 MW)**: **49,45%**

Model sangat akurat pada titik api ringan (MAE 1,45 MW) dan masih *underestimate* pada kelas CRITICAL (bias −13,6 MW) karena populasinya hanya 7,6% dan variasinya ekstrem.

---

## 7. Visualisasi & Inferensi Lapangan

![Hasil Evaluasi Model JST](hasil_evaluasi_jst.png)

Grafik evaluasi model tersimpan di `hasil_evaluasi_jst.png`, memuat:
1. **Kurva Loss Pelatihan & Validasi JST**: konvergensi stabil; LR diturunkan otomatis 4 kali hingga early stopping di epoch 132.
2. **Scatter Plot FRP Aktual vs Prediksi**: keselarasan terhadap garis ideal $y = x$ (R² = 0,5274).
3. **Distribusi Residual Error**: terpusat di sekitar nol (median residual ≈ 0).
4. **Error per Band Intensitas FRP**: MAE & RMSE untuk segmen LOW/MODERATE/CRITICAL.

Notebook juga dilengkapi modul simulasi pengambilan keputusan mitigasi untuk titik api baru, mengkategorikan potensi bahaya menjadi:
- **CRITICAL / TINGGI** ($\ge 20$ MW): prioritas operasi *water-bombing* helikopter.
- **MODERATE / SEDANG** ($8 - 20$ MW): penugasan regu darat Manggala Agni.
- **LOW / RINGAN** ($< 8$ MW): pemantauan satelit berkala.

Contoh keluaran simulasi (model final):

| Lokasi | `bright_ti4` | Prediksi FRP | Rekomendasi |
|---|---|---|---|
| Katingan (Hutan Gambut Pekat) | 365,2 K | 17,03 MW | MODERATE — Tim Manggala Agni Darat |
| Seruyan (Dekat Pemukiman) | 342,1 K | 9,92 MW | MODERATE — Tim Manggala Agni Darat |
| Ketapang (Titik Api Malam) | 324,6 K | 8,25 MW | MODERATE — Tim Manggala Agni Darat |

---

## 8. Struktur Berkas di Direktori
```text
C:/vibing/
├── data_karhutla_kalimantan_cleaned.csv  # Dataset riil bersih NASA FIRMS (35.826 baris)
├── nasa_viirs_kalimantan_raw.csv         # Data mentah langsung dari satelit (35.827 baris)
├── projek_jst_karhutla.ipynb             # Notebook Jupyter lengkap (semua sel tereksekusi)
├── hasil_evaluasi_jst.png                # Visualisasi Loss, Scatter, Residual, & Error per Band
├── matriks_korelasi_fitur.png            # Heatmap korelasi antar fitur
├── README.md                             # Dokumentasi resmi dan laporan teknis
└── experiments/                          # Skrip eksperimen pembanding (baseline, XGBoost, ablasi fitur)
```

---

## 9. Cara Menjalankan
Buka dan jalankan berkas notebook:
```bash
jupyter notebook projek_jst_karhutla.ipynb
```
Atau buka langsung file [`projek_jst_karhutla.ipynb`](file:///c:/vibing/projek_jst_karhutla.ipynb) di VS Code / Antigravity dan klik **Run All**. Seluruh sel sudah teruji bebas error dan output hasil eksekusi lengkap sudah tersimpan di dalam file notebook.

**Prasyarat**: `torch` (CUDA), `pandas`, `numpy`, `scikit-learn`, `matplotlib`, `seaborn`, dan `xgboost` (opsional — hanya untuk benchmark; jika tidak terpasang, sel benchmark otomatis dilewati).

---

## 10. Kesimpulan Hasil Pelatihan Model

Model dilatih selama 132 epoch (dari maksimum 300, early stopping) dengan arsitektur Deep MLP 23-256-128-64-1 (BatchNorm + GELU) pada PyTorch + CUDA GPU.

### Performa pada Data Uji (7.166 sampel independen):
- **Mean Squared Error (MSE)**: 64,82 (baseline 73,28 → **−11,5%**)
- **Root Mean Squared Error (RMSE)**: 8,05 MW
- **Mean Absolute Error (MAE)**: 3,49 MW (median error absolut 1,33 MW)
- **R² Score**: 0,5274 (baseline 0,4658 → **+0,062**)

### Interpretasi:
1. **Kalibrasi isotonic** adalah penyumbang terbesar: model JST cenderung mengembalikan prediksi ekstrem yang bias, dan kalibrasi monotonik pada data validasi menurunkannya menjadi galat wajar.
2. **Fitur temporal & kerapatan hotspot** memberi konteks episodik (jam akuisisi, klaster kebakaran) yang tidak ada pada 8 fitur sensor mentah; pada benchmark XGBoost, penambahan fitur ini menurunkan MSE dari 61,03 → 55,96.
3. **Log-transform target** membuat model tidak "mengorbankan" titik api kecil demi mengejar segelintir nilai ekstrem.
4. **R² 0,53** berarti model menjelaskan sekitar **53% variansi FRP**. Sisanya dipengaruhi faktor di luar fitur piksel tunggal: jenis vegetasi, kelembapan gambut, angin, dan histori kebakaran.
5. **Bias hampir nol secara agregat** (prediksi 7,347 MW vs aktual 7,330 MW), namun **CRITICAL masih *underestimate*** (bias −13,6 MW) — keterbatasan yang wajar karena kelas ini hanya 7,6% dan variansinya sangat ekstrem.

### Rekomendasi Deployment:
Model dapat diimplementasikan sebagai **sistem early warning** dan **decision support tool** untuk:
- Prioritas alokasi unit pemadam (helikopter water-bombing vs. regu darat).
- Estimasi kebutuhan sumber daya pemadaman berdasarkan prediksi intensitas FRP.
- Identifikasi hotspot kritis untuk pengerahan satelit pemantau resolusi tinggi.

### Batasan & Arah Pengembangan:
- **Data eksternal**: meteorologi real-time (suhu udara, kelembapan relatif, kecepatan angin), tutupan lahan/NDVI, dan kedalaman gambut.
- **Data temporal lebih panjang**: periode saat ini hanya 15 hari pada satu musim, sehingga pola musiman belum terwakili.
- **Komponen spasial–temporal eksplisit**: deret waktu per sel grid atau arsitektur CNN-LSTM untuk menangkap penyebaran api gambut.
- **Penanganan kelas ekstrem**: re-sampling atau *cost-sensitive loss* khusus untuk segmen CRITICAL (≥ 20 MW) bila prioritas operasional adalah recall kelas bahaya tinggi.
