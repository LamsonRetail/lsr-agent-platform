// Trang kết quả của luồng authorize C8. Cố tình tối giản: không hiển thị token, không
// đặt cookie — chỉ báo cho admin biết account nào vừa được nối và bước tiếp theo.
export default async function LarkUserPage({
  searchParams,
}: {
  searchParams: Promise<{ ok?: string; err?: string }>;
}) {
  const sp = await searchParams;
  const ok = sp.ok;
  const err = sp.err;
  return (
    <main style={{ maxWidth: 640, margin: "64px auto", padding: 24, lineHeight: 1.6 }}>
      <h1 style={{ fontSize: 20, marginBottom: 16 }}>Lark User Identity (broker)</h1>
      {ok && (
        <>
          <p>
            ✅ Đã nối account <b>{ok}</b>. Token do platform giữ (mã hoá), agent không
            thấy token.
          </p>
          <p style={{ opacity: 0.75 }}>
            Bước tiếp: admin cấp grant cho agent bằng <code>POST /v1/lark/user/grants</code>{" "}
            với <code>path_prefixes</code> hẹp nhất có thể.
          </p>
        </>
      )}
      {err && <p>❌ {err}</p>}
      {!ok && !err && <p>Trang này chỉ hiện kết quả sau khi bạn hoàn tất authorize trên Lark.</p>}
    </main>
  );
}
