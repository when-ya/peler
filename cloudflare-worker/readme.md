# Cloudflare Worker - Proxy B2 buat Custom Domain

Worker ini bikin link video bisa diakses lewat `enak.vexcrt.cc/path/file.mp4`
tanpa perlu nyebut nama bucket, dan **egress gratis** karena traffic B2 -> Cloudflare
gak kena biaya (Bandwidth Alliance).

## Cara Deploy

### 1. Cek Endpoint Bucket B2 kamu

Login ke Backblaze B2 -> buka bucket `video-xx` -> lihat di bagian info bucket,
catat **Endpoint**-nya (contoh: `f005.backblazeb2.com`). Endpoint ini beda-beda
tiap akun/region, jangan asal sama dengan punya orang lain.

### 2. Edit `worker.js`

Buka file `worker.js`, ganti 2 baris ini sesuai punya kamu:

```js
const B2_ENDPOINT = "f005.backblazeb2.com"; // ganti sesuai endpoint bucket kamu
const B2_BUCKET = "video-xx";               // ganti sesuai nama bucket kamu
```

### 3. Bikin Worker Baru di Cloudflare

1. Buka [Cloudflare Dashboard](https://dash.cloudflare.com) -> **Workers & Pages**
2. Klik **Create** -> **Create Worker**
3. Kasih nama (misal `video-proxy`)
4. Klik **Deploy** dulu (pakai kode default), nanti kita ganti isinya
5. Klik **Edit Code**
6. Hapus semua kode default, paste isi `worker.js` yang udah diedit tadi
7. Klik **Deploy** lagi

### 4. Hubungkan ke Custom Domain

1. Di halaman Worker -> tab **Settings** -> **Triggers**
2. Bagian **Custom Domains** -> **Add Custom Domain**
3. Masukin domain kamu, misal `enak.vexcrt.cc`
4. Cloudflare otomatis bikin DNS record & SSL certificate-nya (tunggu beberapa menit)

### 5. Bucket Harus Public

**PENTING**: cara ini cuma jalan kalau bucket B2-nya **Public**. Kalau Private,
Worker perlu logic tambahan buat auth (generate token dulu ke B2 API) -- kabarin
kalau bucket kamu ternyata Private, nanti Worker-nya perlu disesuaikan.

Cek/ubah settingnya di B2 -> Bucket Settings -> **Bucket Type** -> pastikan **Public**.

### 6. Test

Buka `https://enak.vexcrt.cc/asia/videosd.mp4` (ganti sesuai path file yang beneran
ada di bucket kamu). Kalau video kebuka/kedownload, berarti sukses.

### 7. Update Bot

Setelah domain jalan, di Railway -> Variables -> isi:

```
CUSTOM_DOMAIN=enak.vexcrt.cc
```

Bot otomatis pakai domain ini buat semua link video yang di-generate setelahnya
(link video lama yang udah tercatat di Sheets gak otomatis berubah, tapi kalau formatnya
sama tetep bisa diakses lewat domain baru juga).
