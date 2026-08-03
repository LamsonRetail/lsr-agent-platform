"""Sinh prototype dashboard HTML self-contained gồm 6 màn hình đánh giá.

Dữ liệu điểm lấy từ scorer thật (SquadScorer/AgentScorer trên dữ liệu mẫu), phần
"hiện vật" (link, registry, lịch sử test, usage) lấy từ :mod:`.sample`.

Chạy:  python -m rating_agent.reporting.dashboard  ->  output/dashboard.html
Bảng màu theo skill dataviz (status: good/warning/critical; series-1 blue).
"""

from __future__ import annotations

import html
from pathlib import Path

from ..config import load_scoring_config, load_settings
from ..evaluation import AgentScorer, SquadScorer, rank_agents, rank_squads
from ..pipeline import build_sample_agents, build_sample_squads
from . import sample

# ----------------------------- Helpers UI -----------------------------

_GRADE_KIND = {"A": "good", "B": "series", "C": "warning", "D": "critical"}
_REC_KIND = {"keep_active": "good", "watch": "warning", "deactivate": "critical"}
_REC_LABEL = {"keep_active": "Giữ active", "watch": "Cảnh báo", "deactivate": "Deactivate"}
_REC_ICON = {"good": "✓", "warning": "!", "critical": "✕", "series": "●", "neutral": "•"}
_STATUS_KIND = {"active": "good", "registered": "neutral", "testing": "series",
                "deactivated": "critical", "draft": "neutral", "pass": "good",
                "fail": "critical", "-": "neutral"}


def _esc(v) -> str:
    return html.escape(str(v))


def badge(text: str, kind: str) -> str:
    icon = _REC_ICON.get(kind, "•")
    return (f'<span class="badge badge-{kind}"><span class="badge-i">{icon}</span>'
            f'{_esc(text)}</span>')


def grade_badge(grade: str) -> str:
    letter = grade.strip()[0] if grade.strip() else "?"
    kind = _GRADE_KIND.get(letter, "neutral")
    return f'<span class="badge badge-{kind}">{_esc(grade)}</span>'


def bar(value: float, *, maxv: float = 100.0) -> str:
    pct = max(0.0, min(100.0, value / maxv * 100.0))
    return (f'<div class="bar"><div class="bar-fill" style="width:{pct:.1f}%"></div>'
            f'<span class="bar-val">{value:.0f}</span></div>')


def progress(actual: float, target: float) -> str:
    pct = 0.0 if target <= 0 else min(100.0, actual / target * 100.0)
    over = target > 0 and actual >= target
    cls = "bar-fill good" if over else "bar-fill"
    return (f'<div class="bar"><div class="{cls}" style="width:{pct:.1f}%"></div>'
            f'<span class="bar-val">{actual:g}/{target:g}</span></div>')


def kpi(label: str, value: str, sub: str = "") -> str:
    sub_html = f'<div class="kpi-sub">{_esc(sub)}</div>' if sub else ""
    return (f'<div class="kpi"><div class="kpi-label">{_esc(label)}</div>'
            f'<div class="kpi-val">{_esc(value)}</div>{sub_html}</div>')


def sparkline(values: list[int], width: int = 160, height: int = 40) -> str:
    if not values:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    step = width / (len(values) - 1) if len(values) > 1 else width
    pts = [
        (i * step, height - 4 - (v - lo) / span * (height - 8))
        for i, v in enumerate(values)
    ]
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    last_x, last_y = pts[-1]
    return (
        f'<svg class="spark" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'preserveAspectRatio="none" aria-hidden="true">'
        f'<polyline fill="none" stroke="var(--series-1)" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round" points="{path}"/>'
        f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="3.5" fill="var(--series-1)"/>'
        f'</svg>'
    )


def test_dots(history: list[tuple[str, bool]]) -> str:
    cells = []
    for date, ok in history:
        kind = "good" if ok else "critical"
        icon = "✓" if ok else "✕"
        cells.append(f'<span class="dot dot-{kind}" title="{_esc(date)}">{icon}</span>')
    return '<div class="dots">' + "".join(cells) + "</div>"


def links_row(links: dict[str, str]) -> str:
    items = [f'<a class="link-chip" href="{_esc(u)}" target="_blank" rel="noopener">'
             f'{_esc(name)}</a>' for name, u in links.items()]
    return '<div class="chips">' + "".join(items) + "</div>"


def chips(values: list[str]) -> str:
    return '<div class="chips">' + "".join(
        f'<span class="chip">{_esc(v)}</span>' for v in values) + "</div>"


# ----------------------------- Màn hình -----------------------------


def screen_squad_scoreboard(squad_evals) -> str:
    ranking = rank_squads(squad_evals)
    by_id = {e.squad_id: e for e in squad_evals}
    avg = sum(e.total_score for e in squad_evals) / len(squad_evals)
    top = ranking[0]
    rows = ""
    for r in ranking:
        e = by_id[r.item_id]
        rows += (f"<tr><td class='rank'>{r.rank}</td><td><b>{_esc(e.squad_name)}</b>"
                 f"<div class='muted'>{_esc(e.squad_id)}</div></td>"
                 f"<td>{bar(e.objective_score)}</td><td>{bar(e.on_time_score)}</td>"
                 f"<td class='num'><b>{e.total_score:.1f}</b></td>"
                 f"<td>{grade_badge(e.grade)}</td></tr>")
    return f"""
    <h2>Squad Scoreboard</h2>
    <p class="lead">Xếp hạng squad theo <b>hiệu quả mục tiêu</b> (Key Result achievement + đúng tiến độ).</p>
    <div class="kpis">
      {kpi("Số squad", str(len(squad_evals)))}
      {kpi("Điểm trung bình", f"{avg:.1f}")}
      {kpi("Dẫn đầu", top.name, f"{top.total_score:.1f} điểm")}
    </div>
    <table>
      <thead><tr><th>Hạng</th><th>Squad</th><th>Mục tiêu</th><th>Đúng hạn</th><th>Tổng</th><th>Xếp loại</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>"""


def screen_squad_detail(squad_metrics, squad_evals) -> str:
    by_id = {e.squad_id: e for e in squad_evals}
    options = "".join(
        f'<option value="sqd-{_esc(s.squad_id)}">{_esc(s.squad_name)}</option>'
        for s in squad_metrics)
    blocks = ""
    for i, s in enumerate(squad_metrics):
        e = by_id[s.squad_id]
        m = sample.SQUAD_MASTER.get(s.squad_id, {})
        kr_rows = "".join(
            f"<tr><td>{_esc(kr.objective_name)}<div class='muted'>{_esc(kr.key_result)}</div></td>"
            f"<td>{progress(kr.actual, kr.target)}</td>"
            f"<td class='num'>{kr.weight:.0%}</td></tr>"
            for kr in s.key_results)
        hidden = "" if i == 0 else "hidden"
        blocks += f"""
        <div class="sqd-block" id="sqd-{_esc(s.squad_id)}" {hidden}>
          <div class="card">
            <div class="card-head">
              <div><h3>{_esc(s.squad_name)}</h3><div class="muted">{_esc(m.get('description',''))}</div></div>
              <div class="score-big">{e.total_score:.1f}<span>{grade_badge(e.grade)}</span></div>
            </div>
            <div class="meta"><span class="muted">Trưởng squad</span> <b>{_esc(m.get('lead',''))}</b></div>
            {links_row(m.get('links', {}))}
          </div>
          <div class="grid2">
            <div class="card">
              <h4>Key Results</h4>
              <table class="tight"><thead><tr><th>Mục tiêu</th><th>Tiến độ</th><th>Trọng số</th></tr></thead>
              <tbody>{kr_rows}</tbody></table>
              <div class="meta"><span class="muted">Điểm mục tiêu</span> <b>{e.objective_score:.1f}</b>
                &nbsp;·&nbsp;<span class="muted">Đúng hạn</span> <b>{e.on_time_score:.1f}</b></div>
            </div>
            <div class="card">
              <h4>Thành viên</h4>
              {chips(m.get('members', []))}
            </div>
          </div>
        </div>"""
    return f"""
    <h2>Squad Detail</h2>
    <div class="toolbar"><label>Chọn squad</label>
      <select onchange="showSquad(this.value)">{options}</select></div>
    {blocks}"""


def screen_agent_registry() -> str:
    rows = ""
    for aid, r in sample.AGENT_REGISTRY.items():
        rows += (
            f"<tr><td><b>{_esc(aid)}</b><div class='muted'>v{_esc(r['version'])} · {_esc(r['owner'])}</div></td>"
            f"<td>{chips(r['served_squads'])}</td>"
            f"<td>{chips(r['skills'])}</td>"
            f"<td>{chips(r['data_sources'])}</td>"
            f"<td>{badge(r['status'], _STATUS_KIND.get(r['status'],'neutral'))}</td>"
            f"<td>{_esc(r['golive_at'] or '—')}</td>"
            f"<td>{badge(r['last_test_status'], _STATUS_KIND.get(r['last_test_status'],'neutral'))}"
            f"<div class='muted'>{_esc(r['last_test_at'] or '')}</div></td></tr>")
    n_active = sum(1 for r in sample.AGENT_REGISTRY.values() if r["status"] == "active")
    n_reg = sum(1 for r in sample.AGENT_REGISTRY.values() if r["status"] == "registered")
    return f"""
    <h2>Agent Registry</h2>
    <p class="lead">Mọi agent phải <b>đăng ký đầy đủ</b> và <b>pass test</b> trước khi golive.
       Agent chưa golive ở trạng thái <code>registered</code>.</p>
    <div class="kpis">
      {kpi("Tổng agent", str(len(sample.AGENT_REGISTRY)))}
      {kpi("Đang active", str(n_active))}
      {kpi("Chờ golive", str(n_reg))}
    </div>
    <table>
      <thead><tr><th>Agent</th><th>Phục vụ squad</th><th>Skills</th><th>Nguồn dữ liệu</th>
      <th>Status</th><th>Golive</th><th>Test gần nhất</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>"""


def screen_agent_detail(agent_metrics, agent_evals) -> str:
    by_id = {e.agent_id: e for e in agent_evals}
    m_by_id = {a.agent_id: a for a in agent_metrics}
    options = "".join(
        f'<option value="agd-{_esc(a.agent_id)}">{_esc(a.agent_name)}</option>'
        for a in agent_metrics)
    blocks = ""
    for i, a in enumerate(agent_metrics):
        e = by_id[a.agent_id]
        skill_rows = "".join(
            f"<tr><td>{_esc(s.skill_name)}</td><td>{bar(s.pass_rate*100)}</td>"
            f"<td class='num'>{s.tests_passed}/{s.tests_total}</td></tr>"
            for s in a.skill_results)
        trend = sample.USAGE_TREND.get(a.agent_id, [])
        hist = sample.TEST_HISTORY.get(a.agent_id, [])
        hidden = "" if i == 0 else "hidden"
        blocks += f"""
        <div class="agd-block" id="agd-{_esc(a.agent_id)}" {hidden}>
          <div class="card">
            <div class="card-head">
              <div><h3>{_esc(a.agent_name)}</h3><div class="muted">{_esc(a.agent_id)}</div></div>
              <div>{badge(_REC_LABEL[e.status_recommendation.value], _REC_KIND[e.status_recommendation.value])}</div>
            </div>
            <div class="kpis">
              {kpi("Skill", f"{e.skill_score:.0f}")}
              {kpi("Usage", f"{e.usage_score:.0f}")}
              {kpi("Result", f"{e.result_score:.0f}")}
              {kpi("Test pass", f"{e.test_pass_rate:.0f}%")}
              {kpi("Tổng", f"{e.total_score:.0f}", e.grade)}
            </div>
            {f'<div class="note">{_esc(e.note)}</div>' if e.note else ''}
          </div>
          <div class="grid2">
            <div class="card">
              <h4>Skill breakdown</h4>
              <table class="tight"><thead><tr><th>Skill</th><th>Pass rate</th><th>Test</th></tr></thead>
              <tbody>{skill_rows}</tbody></table>
            </div>
            <div class="card">
              <h4>Xu hướng sử dụng (7 tuần)</h4>
              {sparkline(trend)}
              <div class="meta"><span class="muted">Invocations</span> <b>{a.invocations:,}</b>
                &nbsp;·&nbsp;<span class="muted">Người dùng</span> <b>{a.unique_users}</b></div>
              <div class="meta"><span class="muted">Success</span> <b>{a.success_rate:.0%}</b>
                &nbsp;·&nbsp;<span class="muted">Rating</span> <b>{a.user_rating:.1f}/5</b>
                &nbsp;·&nbsp;<span class="muted">Latency</span> <b>{a.avg_latency_ms:.0f}ms</b></div>
              <h4 style="margin-top:14px">Lịch sử test</h4>
              {test_dots(hist)}
            </div>
          </div>
        </div>"""
    return f"""
    <h2>Agent Detail</h2>
    <div class="toolbar"><label>Chọn agent</label>
      <select onchange="showAgent(this.value)">{options}</select></div>
    {blocks}"""


def screen_test_dashboard(agent_evals) -> str:
    runs = sample.RECENT_TEST_RUNS
    n_fail = sum(1 for r in runs if r["status"] == "fail")
    pass_rate = (len(runs) - n_fail) / len(runs) * 100 if runs else 0
    at_risk = [e for e in agent_evals if e.status_recommendation.value != "keep_active"]
    run_rows = "".join(
        f"<tr><td class='muted'>{_esc(r['run_at'])}</td><td><b>{_esc(r['agent'])}</b></td>"
        f"<td>{_esc(r['skill'])}</td><td>{_esc(r['test'])}</td>"
        f"<td>{badge(r['status'], _STATUS_KIND[r['status']])}</td>"
        f"<td class='num'>{r['latency_ms']}ms</td>"
        f"<td>{_esc(r['trigger'])}</td></tr>" for r in runs)
    risk_rows = "".join(
        f"<tr><td><b>{_esc(e.agent_name)}</b></td>"
        f"<td>{badge(_REC_LABEL[e.status_recommendation.value], _REC_KIND[e.status_recommendation.value])}</td>"
        f"<td class='num'>{e.test_pass_rate:.0f}%</td>"
        f"<td class='muted'>{_esc(e.note)}</td></tr>" for e in at_risk) or \
        "<tr><td colspan='4' class='muted'>Không có agent nào cần xử lý.</td></tr>"
    return f"""
    <h2>Agent Test Dashboard</h2>
    <p class="lead">Test tự động chạy định kỳ. Agent <b>fail theo chính sách</b> sẽ bị
       <b>auto-deactivate</b> (mặc định: fail 2 lần liên tiếp).</p>
    <div class="kpis">
      {kpi("Lần chạy gần đây", str(len(runs)))}
      {kpi("Tỉ lệ pass", f"{pass_rate:.0f}%")}
      {kpi("Cần xử lý", str(len(at_risk)))}
    </div>
    <div class="card">
      <h4>Agent cần xử lý (watch / deactivate)</h4>
      <table class="tight"><thead><tr><th>Agent</th><th>Khuyến nghị</th><th>Test pass</th><th>Lý do</th></tr></thead>
      <tbody>{risk_rows}</tbody></table>
    </div>
    <div class="card">
      <h4>Các lần chạy test gần đây</h4>
      <table class="tight"><thead><tr><th>Thời điểm</th><th>Agent</th><th>Skill</th><th>Bài test</th>
      <th>Kết quả</th><th>Latency</th><th>Trigger</th></tr></thead>
      <tbody>{run_rows}</tbody></table>
    </div>"""


def screen_agent_leaderboard(agent_evals) -> str:
    ranking = rank_agents(agent_evals)
    by_id = {e.agent_id: e for e in agent_evals}
    rows = ""
    for r in ranking:
        e = by_id[r.item_id]
        rec = e.status_recommendation.value
        rows += (f"<tr><td class='rank'>{r.rank}</td><td><b>{_esc(e.agent_name)}</b>"
                 f"<div class='muted'>{_esc(e.agent_id)}</div></td>"
                 f"<td>{bar(e.skill_score)}</td><td>{bar(e.usage_score)}</td>"
                 f"<td>{bar(e.result_score)}</td><td class='num'><b>{e.total_score:.0f}</b></td>"
                 f"<td>{grade_badge(e.grade)}</td>"
                 f"<td>{badge(_REC_LABEL[rec], _REC_KIND[rec])}</td></tr>")
    return f"""
    <h2>Agent Leaderboard</h2>
    <p class="lead">Xếp hạng agent theo <b>skill / usage / kết quả</b>. Cột khuyến nghị phản ánh governance gate.</p>
    <table>
      <thead><tr><th>Hạng</th><th>Agent</th><th>Skill</th><th>Usage</th><th>Result</th>
      <th>Tổng</th><th>Xếp loại</th><th>Khuyến nghị</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>"""


# ----------------------------- Lắp trang -----------------------------

_SCREENS = [
    ("scoreboard", "Squad Scoreboard", "◆"),
    ("squad-detail", "Squad Detail", "▤"),
    ("registry", "Agent Registry", "▦"),
    ("agent-detail", "Agent Detail", "◈"),
    ("test-dash", "Agent Test Dashboard", "✓"),
    ("leaderboard", "Agent Leaderboard", "★"),
]


def render_html() -> str:
    config = load_scoring_config(load_settings().scoring_config_path)
    squads = build_sample_squads()
    agents = build_sample_agents()
    squad_evals = SquadScorer(config).score_all(squads)
    agent_evals = AgentScorer(config).score_all(agents)

    contents = {
        "scoreboard": screen_squad_scoreboard(squad_evals),
        "squad-detail": screen_squad_detail(squads, squad_evals),
        "registry": screen_agent_registry(),
        "agent-detail": screen_agent_detail(agents, agent_evals),
        "test-dash": screen_test_dashboard(agent_evals),
        "leaderboard": screen_agent_leaderboard(agent_evals),
    }
    nav = "".join(
        f'<button class="nav-item{" active" if i == 0 else ""}" data-screen="{sid}" '
        f'onclick="showScreen(\'{sid}\')"><span class="nav-i">{icon}</span>'
        f'<span class="nav-label">{_esc(title)}</span></button>'
        for i, (sid, title, icon) in enumerate(_SCREENS))
    panels = "".join(
        f'<section class="screen{" active" if sid == "scoreboard" else ""}" id="screen-{sid}">{body}</section>'
        for sid, body in contents.items())

    return _TEMPLATE.replace("{{NAV}}", nav).replace("{{PANELS}}", panels)


def build(output: Path | str = "output/dashboard.html") -> Path:
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(), encoding="utf-8")
    return out


def main() -> None:  # pragma: no cover
    path = build()
    print(f"Đã sinh dashboard: {path}")


# ----------------------------- Template -----------------------------

_TEMPLATE = """<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Rating Agent — LamsonRetail</title>
<style>
:root{
  color-scheme: light;
  --surface-1:#fcfcfb; --plane:#f9f9f7;
  --text-primary:#0b0b0b; --text-secondary:#52514e; --muted:#898781;
  --grid:#e1e0d9; --baseline:#c3c2b7; --border:rgba(11,11,11,.10);
  --series-1:#2a78d6; --series-soft:#eaf2fc;
  --good:#0ca30c; --warning:#fab219; --serious:#ec835a; --critical:#d03b3b;
}
:root[data-theme="dark"]{
  color-scheme: dark;
  --surface-1:#1a1a19; --plane:#0d0d0d;
  --text-primary:#fff; --text-secondary:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --baseline:#383835; --border:rgba(255,255,255,.10);
  --series-1:#3987e5; --series-soft:#17293d;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    color-scheme: dark;
    --surface-1:#1a1a19; --plane:#0d0d0d;
    --text-primary:#fff; --text-secondary:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --baseline:#383835; --border:rgba(255,255,255,.10);
    --series-1:#3987e5; --series-soft:#17293d;
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--text-primary);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:14px;line-height:1.5}
.app{display:flex;min-height:100vh}
.sidebar{width:230px;flex:none;background:var(--surface-1);border-right:1px solid var(--border);
  padding:18px 12px;position:sticky;top:0;height:100vh;display:flex;flex-direction:column;gap:4px}
.brand{font-weight:700;font-size:15px;padding:6px 10px 16px}
.brand span{display:block;color:var(--muted);font-weight:400;font-size:12px}
.nav-item{display:flex;align-items:center;gap:10px;width:100%;text-align:left;border:0;
  background:transparent;color:var(--text-secondary);padding:9px 11px;border-radius:8px;
  cursor:pointer;font-size:13.5px;font-family:inherit}
.nav-item:hover{background:var(--series-soft)}
.nav-item.active{background:var(--series-soft);color:var(--text-primary);font-weight:600}
.nav-i{width:18px;text-align:center;color:var(--series-1)}
.theme-btn{margin-top:auto;border:1px solid var(--border);background:transparent;color:var(--text-secondary);
  padding:8px;border-radius:8px;cursor:pointer;font-family:inherit}
.main{flex:1;padding:26px 34px;max-width:1100px;overflow-x:auto}
.screen{display:none}.screen.active{display:block}
h2{margin:0 0 4px;font-size:22px}
h3{margin:0 0 2px;font-size:17px} h4{margin:0 0 10px;font-size:13.5px;color:var(--text-secondary)}
.lead{color:var(--text-secondary);margin:0 0 18px;max-width:70ch}
.muted{color:var(--muted);font-size:12px}
code{background:var(--series-soft);padding:1px 5px;border-radius:4px;font-size:12px}
.kpis{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:20px}
.kpi{background:var(--surface-1);border:1px solid var(--border);border-radius:12px;
  padding:14px 16px;min-width:120px}
.kpi-label{color:var(--muted);font-size:12px}
.kpi-val{font-size:26px;font-weight:700;margin-top:2px}
.kpi-sub{color:var(--text-secondary);font-size:12px}
table{width:100%;border-collapse:collapse;background:var(--surface-1);
  border:1px solid var(--border);border-radius:12px;overflow:hidden}
th,td{text-align:left;padding:11px 14px;border-bottom:1px solid var(--grid);vertical-align:middle}
th{font-size:11.5px;text-transform:uppercase;letter-spacing:.03em;color:var(--muted);font-weight:600}
tr:last-child td{border-bottom:0}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
td.rank{color:var(--muted);font-variant-numeric:tabular-nums;width:44px}
table.tight th,table.tight td{padding:9px 12px}
.bar{position:relative;height:22px;background:var(--grid);border-radius:6px;min-width:120px;overflow:hidden}
.bar-fill{position:absolute;left:0;top:0;bottom:0;background:var(--series-1);border-radius:6px}
.bar-fill.good{background:var(--good)}
.bar-val{position:absolute;right:7px;top:0;line-height:22px;font-size:11.5px;
  color:var(--text-primary);font-variant-numeric:tabular-nums;mix-blend-mode:normal}
.badge{display:inline-flex;align-items:center;gap:5px;padding:3px 9px;border-radius:999px;
  font-size:12px;font-weight:500;border:1px solid var(--border);white-space:nowrap}
.badge-i{display:inline-flex;width:14px;height:14px;border-radius:50%;align-items:center;
  justify-content:center;font-size:10px;color:#fff}
.badge-good{background:color-mix(in srgb,var(--good) 12%,transparent);color:var(--good)}
.badge-good .badge-i{background:var(--good)}
.badge-warning{background:color-mix(in srgb,var(--warning) 16%,transparent);color:#8a6100}
.badge-warning .badge-i{background:var(--warning);color:#3a2900}
.badge-critical{background:color-mix(in srgb,var(--critical) 12%,transparent);color:var(--critical)}
.badge-critical .badge-i{background:var(--critical)}
.badge-series{background:var(--series-soft);color:var(--series-1)}
.badge-series .badge-i{background:var(--series-1)}
.badge-neutral{background:transparent;color:var(--text-secondary)}
.badge-neutral .badge-i{background:var(--muted)}
:root[data-theme="dark"] .badge-warning{color:var(--warning)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .badge-warning{color:var(--warning)}}
.card{background:var(--surface-1);border:1px solid var(--border);border-radius:12px;padding:18px;margin-bottom:16px}
.card-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:12px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.grid2 .card{margin:0}
.score-big{font-size:30px;font-weight:700;text-align:right;line-height:1.1}
.score-big span{display:block;font-size:12px;font-weight:400;margin-top:4px}
.meta{margin-top:10px;font-size:13px}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}
.chip{background:var(--series-soft);color:var(--text-secondary);padding:3px 10px;border-radius:999px;font-size:12px}
.link-chip{background:var(--series-soft);color:var(--series-1);padding:4px 11px;border-radius:8px;
  font-size:12.5px;text-decoration:none;border:1px solid var(--border)}
.link-chip:hover{text-decoration:underline}
.toolbar{display:flex;align-items:center;gap:10px;margin:6px 0 18px}
.toolbar label{color:var(--muted);font-size:12px}
select{font-family:inherit;font-size:13.5px;padding:7px 10px;border-radius:8px;
  border:1px solid var(--border);background:var(--surface-1);color:var(--text-primary)}
.spark{display:block;width:100%;height:40px}
.dots{display:flex;gap:5px;flex-wrap:wrap}
.dot{width:22px;height:22px;border-radius:5px;display:inline-flex;align-items:center;
  justify-content:center;color:#fff;font-size:12px}
.dot-good{background:var(--good)} .dot-critical{background:var(--critical)}
.note{background:color-mix(in srgb,var(--warning) 14%,transparent);border-radius:8px;
  padding:8px 12px;font-size:13px;color:var(--text-secondary)}
@media(max-width:900px){
  .grid2{grid-template-columns:1fr}
  .sidebar{width:60px;padding:14px 8px}
  .nav-label,.brand span,.theme-btn{display:none}
  .nav-item{justify-content:center;padding:10px 0}
  .brand{padding:6px 0 14px;text-align:center;font-size:0}
  .brand::before{content:"RA";font-size:15px}
  .main{padding:20px 18px}
}
</style>
</head>
<body>
<div class="app">
  <nav class="sidebar">
    <div class="brand">Rating Agent<span>LamsonRetail · prototype</span></div>
    {{NAV}}
    <button class="theme-btn" onclick="toggleTheme()">◐ Đổi giao diện</button>
  </nav>
  <main class="main">
    {{PANELS}}
  </main>
</div>
<script>
function showScreen(id){
  document.querySelectorAll('.screen').forEach(s=>s.classList.toggle('active',s.id==='screen-'+id));
  document.querySelectorAll('.nav-item').forEach(n=>n.classList.toggle('active',n.dataset.screen===id));
}
function showSquad(id){document.querySelectorAll('.sqd-block').forEach(b=>b.hidden=(b.id!==id));}
function showAgent(id){document.querySelectorAll('.agd-block').forEach(b=>b.hidden=(b.id!==id));}
function toggleTheme(){
  const r=document.documentElement;
  const dark=r.getAttribute('data-theme')==='dark'
    || (!r.getAttribute('data-theme') && matchMedia('(prefers-color-scheme:dark)').matches);
  r.setAttribute('data-theme', dark?'light':'dark');
}
</script>
</body>
</html>"""


if __name__ == "__main__":  # pragma: no cover
    main()
