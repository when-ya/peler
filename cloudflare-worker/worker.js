/**
 * Cloudflare Worker - Proxy ke Backblaze B2 Bucket
 * ==================================================
 * Tujuan: biar link video bisa diakses lewat custom domain (enak.vexcrt.cc)
 * dan egress-nya GRATIS karena lewat Cloudflare (Bandwidth Alliance B2 <-> Cloudflare).
 *
 * Cara kerja:
 *   User akses -> https://enak.vexcrt.cc/asia/videosd.mp4
 *   Worker ini otomatis translate jadi   -> https://f005.backblazeb2.com/file/video-xx/asia/videosd.mp4
 *   Lalu stream balik response-nya ke user, TANPA user perlu tau endpoint asli B2.
 *
 * WAJIB DIISI sebelum deploy:
 *   - B2_ENDPOINT : endpoint bucket B2 kamu, contoh "f005.backblazeb2.com"
 *   - B2_BUCKET   : nama bucket B2 kamu, contoh "video-xx"
 */

const B2_ENDPOINT = "f005.backblazeb2.com"; // <-- GANTI sesuai endpoint bucket kamu
const B2_BUCKET = "video-xx";               // <-- GANTI sesuai nama bucket kamu

export default {
  async fetch(request) {
    const url = new URL(request.url);

    // Path yang diminta user, misal "/asia/videosd.mp4"
    const requestedPath = url.pathname;

    // Susun ulang jadi URL asli B2 dengan format wajib: /file/{bucket}/{path}
    const b2Url = `https://${B2_ENDPOINT}/file/${B2_BUCKET}${requestedPath}`;

    // Forward request ke B2, teruskan header penting (Range dipakai buat video streaming/seek)
    const b2Request = new Request(b2Url, {
      method: request.method,
      headers: {
        "Range": request.headers.get("Range") || "",
      },
    });

    const b2Response = await fetch(b2Request);

    // Kalau file gak ketemu, balikin 404 yang jelas
    if (b2Response.status === 404) {
      return new Response(
        JSON.stringify({ error: "File tidak ditemukan", path: requestedPath }),
        {
          status: 404,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    // Kloning response B2, tapi tambahin header yang bikin video bisa di-stream/seek
    // dan bisa diakses dari domain manapun (CORS)
    const newHeaders = new Headers(b2Response.headers);
    newHeaders.set("Accept-Ranges", "bytes");
    newHeaders.set("Access-Control-Allow-Origin", "*");
    newHeaders.set("Cache-Control", "public, max-age=86400"); // cache 1 hari di edge Cloudflare

    return new Response(b2Response.body, {
      status: b2Response.status,
      statusText: b2Response.statusText,
      headers: newHeaders,
    });
  },
};
