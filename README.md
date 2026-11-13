# Prakiraan Dunia

Dashboard prakiraan ekonomi dan geopolitik dunia untuk investor yang memakai Rupiah: skenario 1 bulan sampai 5 tahun, siklus pasar (saham, emas, Bitcoin, suku bunga, dolar), matriks aset, dan simulasi Monte Carlo portofolio.

**Situs:** https://gabfx09.github.io/prakiraan-dunia/

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
data/market.json               harga, ditulis GitHub Actions
data/snapshot.json             analisis, ditulis agen Claude
scripts/fetch_market.py        pengambil harga
scripts/validate_snapshot.py   penjaga format data agen
.github/workflows/             jadwal otomatis
claude-artifact/               versi untuk claude.ai
```

## Penafian

Bukan nasihat keuangan dan bukan ajakan membeli atau menjual. Prakiraan dan simulasi adalah skenario berbasis asumsi yang sebagian ditulis oleh AI dan bisa keliru. Situs ini tidak terdaftar atau diawasi OJK.
