"""Dashboard LIVE — đọc dữ liệu thật từ Platform API + Collector (không dùng sample).

Chỉ phụ thuộc ``requests`` (qua PlatformClient/CollectorClient), không import phần
pydantic — để chạy được ngay trên VM cạnh các service (127.0.0.1).

Chạy trên VM:
  LSR_PLATFORM_URL=http://localhost:8090 LSR_COLLECTOR=http://localhost:8081 \\
  python3 -m rating_agent.reporting.live_dashboard
"""

from __future__ import annotations

import html
from pathlib import Path

from ..platform_client import CollectorClient, PlatformClient

_STATUS = {"active": "good", "registered": "neutral", "deactivated": "critical",
           "draft": "neutral", "in_review": "warning"}


def _esc(v) -> str:
    return html.escape(str(v if v is not None else ""))


def _badge(text, kind) -> str:
    return f'<span class="b b-{kind}">{_esc(text)}</span>'


def _bar(v) -> str:
    pct = max(0.0, min(100.0, float(v or 0)))
    return f'<div class="bar"><div class="fill" style="width:{pct:.0f}%"></div><span>{pct:.0f}</span></div>'


def render_html(agents, stats, tests, attempts, training) -> str:
    smap = {s.get("agent_id"): s for s in (stats or [])}

    arows = "".join(
        f"<tr><td><b>{_esc(a.get('name') or a.get('agent_id'))}</b>"
        f"<div class='m'>{_esc(a.get('agent_id'))}</div></td>"
        f"<td>{_esc(a.get('squad'))}</td><td>{_esc(a.get('owner'))}</td>"
        f"<td>{_badge(a.get('status'), _STATUS.get(a.get('status'),'neutral'))}</td>"
        f"<td class='n'>{(smap.get(a.get('agent_id')) or {}).get('total_tokens') or 0:,}</td>"
        f"<td class='n'>{(smap.get(a.get('agent_id')) or {}).get('runs') or 0}</td></tr>"
        for a in (agents or [])
    ) or "<tr><td colspan='6' class='m'>chưa có agent</td></tr>"

    trows = "".join(
        f"<tr><td><b>{_esc(t.get('title'))}</b><div class='m'>{_esc(t.get('test_id'))}</div></td>"
        f"<td>{_badge(t.get('source'),'neutral')}</td>"
        f"<td>{_badge(t.get('status'), _STATUS.get(t.get('status'),'neutral'))}</td>"
        f"<td class='n'>{t.get('num_questions') or 0}</td>"
        f"<td>{_esc(t.get('reviewed_by') or '—')}</td></tr>"
        for t in (tests or [])
    ) or "<tr><td colspan='5' class='m'>chưa có bài test</td></tr>"

    atrows = "".join(
        f"<tr><td><b>{_esc(a.get('taker_id'))}</b></td>"
        f"<td>{_badge(a.get('taker_type'),'neutral')}</td><td>{_esc(a.get('test_id'))}</td>"
        f"<td>{_bar(round((a.get('score') or 0)*100))}</td>"
        f"<td>{_badge('pass' if a.get('passed') else 'fail','good' if a.get('passed') else 'critical')}</td></tr>"
        for a in (attempts or [])
    ) or "<tr><td colspan='5' class='m'>chưa có lượt làm bài</td></tr>"

    mrows = "".join(
        f"<tr><td><b>{_esc(m.get('title'))}</b></td>"
        f"<td>{_esc(', '.join(m.get('tags') or []))}</td>"
        f"<td>{_esc(m.get('provided_by'))}</td><td class='m'>{_esc(m.get('source_file'))}</td></tr>"
        for m in (training or [])
    ) or "<tr><td colspan='4' class='m'>chưa có tài liệu</td></tr>"

    total_tokens = sum((s.get("total_tokens") or 0) for s in (stats or []))
    return _TPL.format(
        n_agents=len(agents or []), n_tests=len(tests or []),
        n_attempts=len(attempts or []), total_tokens=f"{total_tokens:,}",
        arows=arows, trows=trows, atrows=atrows, mrows=mrows,
    )


def build_live(output: Path | str = "live_dashboard.html",
               platform: PlatformClient | None = None,
               collector: CollectorClient | None = None) -> Path:
    p = platform or PlatformClient()
    c = collector or CollectorClient()

    def _safe(fn, default):
        try:
            return fn()
        except Exception:
            return default

    html_str = render_html(
        _safe(p.list_agents, []), _safe(c.token_stats, []),
        _safe(p.list_tests, []), _safe(p.list_attempts, []), _safe(p.list_training, []),
    )
    out = Path(output)
    out.write_text(html_str, encoding="utf-8")
    return out


_TPL = """<!doctype html><html lang="vi"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>LSR Platform — LIVE</title><style>
:root{{color-scheme:light dark}}
body{{margin:0;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:14px;
  background:#f9f9f7;color:#0b0b0b;padding:24px}}
@media(prefers-color-scheme:dark){{body{{background:#0d0d0d;color:#fff}}
  .card,table{{background:#1a1a19!important;border-color:rgba(255,255,255,.12)!important}}
  th{{color:#898781!important}} .m{{color:#898781!important}}}}
h1{{font-size:22px;margin:0 0 2px}} h3{{margin:22px 0 8px;font-size:15px}}
.lead{{color:#52514e;margin:0 0 16px}} .m{{color:#898781;font-size:12px}}
.kpis{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px}}
.card{{background:#fff;border:1px solid rgba(11,11,11,.1);border-radius:12px;padding:12px 15px;min-width:120px}}
.card .v{{font-size:24px;font-weight:700}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid rgba(11,11,11,.1);
  border-radius:12px;overflow:hidden}}
th,td{{text-align:left;padding:9px 13px;border-bottom:1px solid rgba(11,11,11,.07)}}
th{{font-size:11px;text-transform:uppercase;letter-spacing:.03em;color:#898781}}
tr:last-child td{{border-bottom:0}} td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums}}
.b{{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;border:1px solid rgba(127,127,127,.3)}}
.b-good{{color:#0ca30c}} .b-warning{{color:#c98500}} .b-critical{{color:#d03b3b}} .b-neutral{{color:#898781}}
.bar{{position:relative;height:20px;background:rgba(127,127,127,.2);border-radius:6px;min-width:110px;overflow:hidden}}
.fill{{position:absolute;inset:0 auto 0 0;background:#2a78d6;border-radius:6px}}
.bar span{{position:absolute;right:6px;top:0;line-height:20px;font-size:11px}}
</style></head><body>
<h1>LSR Agent Platform — LIVE</h1>
<p class="lead">Dữ liệu thật từ Platform API + Collector (không phải sample).</p>
<div class="kpis">
  <div class="card"><div class="m">Agent</div><div class="v">{n_agents}</div></div>
  <div class="card"><div class="m">Bài test</div><div class="v">{n_tests}</div></div>
  <div class="card"><div class="m">Lượt làm bài</div><div class="v">{n_attempts}</div></div>
  <div class="card"><div class="m">Tổng token</div><div class="v">{total_tokens}</div></div>
</div>
<h3>Agents (token/runs từ collector)</h3>
<table><thead><tr><th>Agent</th><th>Squad</th><th>Owner</th><th>Status</th><th class="n">Token</th><th class="n">Runs</th></tr></thead><tbody>{arows}</tbody></table>
<h3>Bài test (Test &amp; Learn)</h3>
<table><thead><tr><th>Bài test</th><th>Nguồn</th><th>Trạng thái</th><th class="n">Số câu</th><th>Người duyệt</th></tr></thead><tbody>{trows}</tbody></table>
<h3>Lượt làm bài</h3>
<table><thead><tr><th>Người làm</th><th>Loại</th><th>Bài</th><th>Điểm</th><th>Kết quả</th></tr></thead><tbody>{atrows}</tbody></table>
<h3>Training (HR)</h3>
<table><thead><tr><th>Tài liệu</th><th>Tags</th><th>Nguồn</th><th>File</th></tr></thead><tbody>{mrows}</tbody></table>
</body></html>"""


def main() -> None:  # pragma: no cover
    print("Đã sinh dashboard LIVE:", build_live())


if __name__ == "__main__":  # pragma: no cover
    main()
