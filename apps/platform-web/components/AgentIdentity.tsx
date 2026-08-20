// C8 — panel "danh tính Lark" trên trang agent.
//
// Vì sao cần: người xem trang agent phải phân biệt được HAI tầng, trước đây console chỉ
// hiện tầng 1 nên đã có lần đọc nhầm (20/08: AG-LEGAL đã chuyển sang bot riêng mà console
// vẫn ghi tên bot cũ, lại càng khó biết agent đang hành động dưới danh nghĩa ai).
//   1. Bot  — app Lark nhận/gửi tin trong nhóm.
//   2. Danh tính người — user token, chỉ dùng cho API Lark bắt buộc user token (Approval).
// Panel này là tầng 2. Không bao giờ hiển thị token; platform cũng không trả token ra API.

function fmt(d?: string | null) {
  return d ? new Date(d).toLocaleString("vi-VN") : "—";
}

export default function AgentIdentity({ data }: { data: any }) {
  const ids = data?.identities || [];
  const calls = data?.calls_7d || {};
  const warnDays = data?.warn_days ?? 2;

  if (ids.length === 0) {
    return (
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Danh tính Lark (hành động dưới danh nghĩa người)</h3>
        <span className="muted">
          Agent này <b>không</b> hành động dưới danh nghĩa account nào — chỉ dùng bot của
          nó. Cần khi agent phải gọi API Lark bắt buộc user token (vd Approval): admin
          chạy <code>/v1/lark/user/authorize/start</code> rồi cấp grant. Xem{" "}
          <a href="https://github.com/LamsonRetail/lsr-agent-platform/blob/main/docs/LARK_USER_BROKER.md"
             target="_blank" rel="noreferrer">docs/LARK_USER_BROKER.md ↗</a>.
        </span>
      </div>
    );
  }

  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>Danh tính Lark (hành động dưới danh nghĩa người)</h3>
      <p className="muted" style={{ fontSize: 12.5, marginTop: 0 }}>
        Token do <b>platform</b> giữ (mã hoá) và tự gia hạn — <b>agent không thấy token</b>,
        chỉ gọi được đúng các path được liệt kê. Mọi lời gọi đều vào audit.
        {(calls.ok_7d || calls.fail_7d) ? (
          <> · 7 ngày qua: <b>{calls.ok_7d || 0}</b> lời gọi OK, {calls.fail_7d || 0} lỗi
          · gần nhất {fmt(calls.last_call)}</>
        ) : <> · 7 ngày qua chưa có lời gọi nào.</>}
      </p>

      <table>
        <thead>
          <tr>
            <th>Account</th><th>Phạm vi được cấp</th><th>Trạng thái</th>
            <th>Refresh</th><th>Dùng gần nhất</th>
          </tr>
        </thead>
        <tbody>
          {ids.map((i: any) => {
            const days = i.refresh_days_left;
            const dead = !i.active || days <= 0;
            const warn = !dead && days <= warnDays;
            return (
              <tr key={i.subject_email}>
                <td>
                  <b>{i.name || i.subject_email}</b>
                  <div className="muted" style={{ fontSize: 12 }}>{i.subject_email}</div>
                </td>
                <td style={{ fontSize: 12 }}>
                  {(i.path_prefixes || []).map((p: string) => <div key={p}><code>{p}</code></div>)}
                  <div className="muted">{(i.methods || []).join(", ")}</div>
                </td>
                <td>
                  {i.active
                    ? <span className="b b-good">đang bật</span>
                    : <span className="b b-critical">đã thu hồi</span>}
                  <div className="muted" style={{ fontSize: 12 }}>
                    cấp bởi {i.granted_by} · {fmt(i.granted_at)}
                  </div>
                </td>
                <td>
                  {dead
                    ? <span className="b b-critical">hết hạn</span>
                    : warn
                      ? <span className="b b-warn">còn {days} ngày</span>
                      : <>còn {days} ngày</>}
                  <div className="muted" style={{ fontSize: 12 }}>{fmt(i.refresh_expires_at)}</div>
                </td>
                <td className="muted" style={{ fontSize: 12 }}>{fmt(i.last_used_at)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {ids.some((i: any) => i.active && i.refresh_days_left <= warnDays) && (
        <p className="err" style={{ fontSize: 12.5 }}>
          Refresh token sắp hết hạn. Hết là agent mất quyền gọi các API cần user token, và
          <b> bắt buộc phải có người authorize lại</b> — không tự khôi phục được. AG-OPS đã
          nhắc admin; nếu gấp, nhờ admin tạo link authorize mới.
        </p>
      )}
    </div>
  );
}
