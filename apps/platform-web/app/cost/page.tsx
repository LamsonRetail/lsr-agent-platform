import { costSummary, costTimeseries } from "@/lib/platform";
import { QuotaForm, CheckAlertsButton } from "@/components/CostActions";

export const dynamic = "force-dynamic";

function money(n: number) {
  return "$" + (n || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function QuotaBar({ pct }: { pct: number | null }) {
  if (pct == null) return <span className="muted">—</span>;
  const kind = pct >= 100 ? "critical" : pct >= 80 ? "warn" : "good";
  const color = kind === "critical" ? "#d64545" : kind === "warn" ? "#c98a00" : "#2e9e5b";
  return (
    <div style={{ minWidth: 120 }}>
      <div style={{ background: "#eee", borderRadius: 4, height: 8, overflow: "hidden" }}>
        <div style={{ width: `${Math.min(100, pct)}%`, height: "100%", background: color }} />
      </div>
      <div className="muted" style={{ fontSize: 11 }}>{pct}%</div>
    </div>
  );
}

// Biểu đồ cột theo ngày (USD ước tính) — SVG nội tuyến, không thư viện ngoài.
function DailyChart({ series }: { series: { day: string; usd: number; tokens: number }[] }) {
  if (!series.length) return <p className="muted">Chưa có dữ liệu trong kỳ.</p>;
  const W = 720, H = 160, pad = 24;
  const max = Math.max(...series.map((s) => s.usd), 0.0001);
  const bw = (W - pad * 2) / series.length;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto" }} role="img">
      <line x1={pad} y1={H - pad} x2={W - pad} y2={H - pad} stroke="#ddd" />
      {series.map((s, i) => {
        const h = (s.usd / max) * (H - pad * 2);
        const x = pad + i * bw;
        const y = H - pad - h;
        return (
          <g key={s.day}>
            <rect x={x + 1} y={y} width={Math.max(1, bw - 2)} height={h} fill="#4a7edb" rx={1}>
              <title>{`${s.day}: ${money(s.usd)} · ${s.tokens.toLocaleString()} token`}</title>
            </rect>
            {i % Math.ceil(series.length / 10) === 0 && (
              <text x={x + bw / 2} y={H - pad + 12} fontSize={9} fill="#888" textAnchor="middle">
                {s.day.slice(8)}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

export default async function CostPage({ searchParams }: { searchParams: { period?: string } }) {
  const period = searchParams?.period;
  const [sum, ts] = await Promise.all([costSummary(period), costTimeseries(period)]);

  return (
    <>
      <h1>Chi phí &amp; Hạn mức</h1>
      <p className="lead">
        Chi phí <b>ước tính</b> (agent chạy bằng subscription của owner nên không có hoá đơn theo token —
        con số USD quy đổi theo giá API công khai để đo mức dùng &amp; đặt hạn mức). Kỳ: <b>{sum.period}</b>.
      </p>

      <div className="kpis">
        <div className="kpi"><div className="l">Chi phí ước tính (tháng)</div><div className="v">{money(sum.total_usd)}</div></div>
        <div className="kpi"><div className="l">Tổng token</div><div className="v">{(sum.total_tokens || 0).toLocaleString()}</div></div>
        <div className="kpi"><div className="l">Số lần chạy</div><div className="v">{(sum.total_runs || 0).toLocaleString()}</div></div>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Chi phí ước tính theo ngày</h3>
        <DailyChart series={ts.series} />
      </div>

      <div className="row" style={{ justifyContent: "space-between", alignItems: "center", margin: "16px 0 8px" }}>
        <h3 style={{ margin: 0 }}>Theo agent</h3>
        <CheckAlertsButton />
      </div>
      <table>
        <thead><tr>
          <th>Agent</th><th className="n">Runs</th><th className="n">Token</th>
          <th className="n">Ước tính</th><th>Hạn mức đã dùng</th><th>Đặt hạn mức (USD / token / %)</th>
        </tr></thead>
        <tbody>
          {sum.agents.length === 0 && <tr><td colSpan={6} className="muted">Chưa có dữ liệu trace trong kỳ.</td></tr>}
          {sum.agents.map((a: any) => (
            <tr key={a.agent_id}>
              <td>
                <b>{a.name || a.agent_id}</b>
                <div className="muted">{a.agent_id}{a.owner ? ` · ${a.owner}` : ""}</div>
                {a.models && Object.keys(a.models).length > 0 && (
                  <div className="muted" style={{ fontSize: 11 }}>
                    {Object.entries(a.models).map(([m, v]: any) => `${m}: ${money(v.usd)}`).join(" · ")}
                  </div>
                )}
              </td>
              <td className="n">{a.runs}</td>
              <td className="n">{a.tokens.toLocaleString()}</td>
              <td className="n">{money(a.usd)}</td>
              <td><QuotaBar pct={a.pct} /></td>
              <td><QuotaForm agentId={a.agent_id} usd={a.quota_usd} tokens={a.quota_tokens} alertPct={a.alert_pct} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted" style={{ fontSize: 12 }}>
        Cảnh báo tự chạy nền mỗi 30 phút; vượt ngưỡng (mặc định 80%) và 100% sẽ gửi Lark cho owner (1 lần/mức/tháng).
      </p>
    </>
  );
}
