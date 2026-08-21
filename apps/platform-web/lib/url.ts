import "server-only";

/** Gốc PUBLIC của console để redirect trình duyệt.
 *
 * KHÔNG dùng req.url: Next standalone trong Docker dựng nó từ hostname nội bộ
 * của container (vd http://0ac36ca4e9c1:3000) — trình duyệt không phân giải được.
 * Ưu tiên header do Caddy forward; nếu host trông như container id/cổng nội bộ
 * thì rơi về LSR_APP_PUBLIC.
 */
export function publicBase(req: Request): string {
  const proto = req.headers.get("x-forwarded-proto") || "https";
  const h = req.headers.get("x-forwarded-host") || req.headers.get("host") || "";
  const bare = h.split(":")[0];
  const looksInternal = !h || h.endsWith(":3000") || /^[0-9a-f]{12}$/.test(bare)
    || bare === "localhost" || bare === "web";
  if (!looksInternal) return `${proto}://${h}`;
  return process.env.LSR_APP_PUBLIC || "https://app.34-126-154-135.sslip.io";
}
