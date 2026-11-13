# Prakiraan Dunia

Dashboard prakiraan ekonomi dan geopolitik dunia untuk investor yang memakai Rupiah: skenario 1 bulan sampai 5 tahun, siklus pasar (saham, emas, Bitcoin, suku bunga, dolar), matriks aset, dan simulasi Monte Carlo portofolio.

**Situs:** https://gabfx09.github.io/prakiraan-dunia/

## Pasang sebagai aplikasi

- **Android / Chrome / Edge:** buka situsnya, tekan tombol **⤓ Pasang aplikasi** di kanan atas (atau menu ⋮ → Instal aplikasi).
- **iPhone / iPad:** buka di Safari → tombol Bagikan → **Tambah ke Layar Utama**.
- **Komputer:** ikon pasang di ujung kanan bilah alamat Chrome/Edge.

Aplikasi tetap bisa dibuka saat offline dengan data terakhir yang tersimpan.

**Unduh kode:** [main.zip](https://github.com/GabFx09/prakiraan-dunia/archive/refs/heads/main.zip)

## Cara kerjanya

| Bagian | Sumber | Seberapa sering |
|---|---|---|
| Harga pasar (S&P 500, IHSG, emas, Brent, USD/IDR, obligasi AS 10 thn, Bitcoin) | Yahoo Finance, lewat GitHub Actions (`.github/workflows/market.yml`) → `data/market.json` | ±15 menit |
| Bitcoin live | CoinGecko, langsung dari browser pengunjung | tiap menit |
| Berita, indeks risiko, skenario, siklus, asumsi simulasi | Agen Claude terjadwal (Claude Code routine) → `data/snapshot.json`, divalidasi `scripts/validate_snapshot.py` | tiap jam; revisi besar sekali sehari |
| Simulasi Monte Carlo | Dihitung di browser pengunjung | saat halaman dibuka |

Semua berjalan di cloud (GitHub dan Anthropic). Komputer pemilik tidak perlu menyala.

## Struktur

```
index.html                     situs (satu file, tanpa build)
manifest.webmanifest, sw.js    aplikasi terpasang & mode offline
icons/                         ikon aplikasi
data/market.json               harga, ditulis GitHub Actions
data/snapshot.json             analisis, ditulis agen Claude
scripts/fetch_market.py        pengambil harga
scripts/validate_snapshot.py   penjaga format data agen
.github/workflows/             jadwal otomatis
claude-artifact/               versi untuk claude.ai
```

## Penafian

Bukan nasihat keuangan dan bukan ajakan membeli atau menjual. Prakiraan dan simulasi adalah skenario berbasis asumsi yang sebagian ditulis oleh AI dan bisa keliru. Situs ini tidak terdaftar atau diawasi OJK.
