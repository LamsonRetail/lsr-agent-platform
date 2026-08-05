"""Prototype LSR Agent Platform: dashboard platform + backend riêng từng agent.

Sinh 1 trang HTML self-contained mô phỏng kiến trúc chung:
  - Dashboard PLATFORM: tổng hợp mọi agent + squad; active/deactivate/rating;
    mở được backend từng agent.
  - BACKEND từng agent (mô phỏng app Vercel, chỉ owner sửa): Config (skills,
    system prompt, model), Dashboard (log, usage, kết quả squad), Schedule.

Chạy:  python -m rating_agent.reporting.platform_proto  ->  output/platform.html
Điểm rating lấy từ AgentScorer thật; phần config/log/schedule từ platform_sample.
"""

from __future__ import annotations

from pathlib import Path

from ..config import load_scoring_config, load_settings
from ..evaluation import AgentScorer, SquadScorer
from ..pipeline import build_sample_agents, build_sample_squads
from . import sample
from .dashboard import _esc, badge, bar, chips, grade_badge, kpi, sparkline
from .platform_sample import AGENT_BACKEND
from ..testlearn import (
    Answer,
    Question,
    TakerType,
    Test,
    TestStatus,
    TrainingMaterial,
    grade,
    recommend_training,
)

_STATUS_KIND = {"active": "good", "registered": "neutral", "deactivated": "critical"}
_LOG_KIND = {"ok": "good", "warn": "warning", "fail": "critical"}
_REC_KIND = {"keep_active": "good", "watch": "warning", "deactivate": "critical"}
_REC_LABEL = {"keep_active": "Giữ active", "watch": "Cảnh báo", "deactivate": "Đề nghị tắt"}


def _stars(agent_id: str, score: float) -> str:
    filled = round(score / 20)  # 0..100 -> 0..5
    spans = "".join(
        f'<span class="star{" on" if i < filled else ""}" '
        f'onclick="rate(\'{agent_id}\',{i + 1})">★</span>'
        for i in range(5)
    )
    return f'<span class="stars" id="stars-{agent_id}">{spans}</span>'


# --------------------------- PLATFORM ---------------------------

def render_platform(agents: list[dict], squads: list[dict]) -> str:
    n_active = sum(1 for a in agents if a["status"] == "active")
    n_off = sum(1 for a in agents if a["status"] == "deactivated")
    total_inv = sum(a["invocations"] for a in agents)

    a_rows = ""
    for a in agents:
        aid = a["agent_id"]
        toggle_label = "Deactivate" if a["status"] == "active" else "Activate"
        a_rows += (
            f'<tr id="prow-{aid}"><td><b>{_esc(a["name"])}</b>'
            f'<div class="muted">{_esc(aid)}</div></td>'
            f'<td>{_esc(a["squad"])}</td>'
            f'<td>{_esc(a["owner"])}</td>'
            f'<td id="pstatus-{aid}">{badge(a["status"], _STATUS_KIND.get(a["status"],"neutral"))}</td>'
            f'<td>{_stars(aid, a["rating"])}<div class="muted">{a["rating"]:.0f} · {_esc(a["grade"])}</div></td>'
            f'<td class="num">{a["invocations"]:,}</td>'
            f'<td class="actions">'
            f'<button class="btn btn-sm" onclick="toggleStatus(\'{aid}\')" id="ptoggle-{aid}">{toggle_label}</button>'
            f'<button class="btn btn-sm btn-primary" onclick="openAgent(\'{aid}\')">Mở backend →</button>'
            f'</td></tr>'
        )

    s_rows = "".join(
        f'<tr><td><b>{_esc(s["name"])}</b><div class="muted">{_esc(s["squad_id"])}</div></td>'
        f'<td>{_esc(s["primary_agent"])}</td>'
        f'<td>{bar(s["objective_score"])}</td>'
        f'<td>{grade_badge(s["grade"])}</td></tr>'
        for s in squads
    )

    return f"""
    <section id="view-platform" class="view active">
      <h1>Platform Dashboard</h1>
      <p class="lead">Tổng hợp mọi agent & squad. Active/Deactivate, rating, và mở
         backend riêng của từng agent.</p>
      <div class="kpis">
        {kpi("Tổng agent", str(len(agents)))}
        {kpi("Đang active", str(n_active))}
        {kpi("Đã tắt", str(n_off))}
        {kpi("Squad", str(len(squads)))}
        {kpi("Lượt dùng (kỳ)", f"{total_inv:,}")}
      </div>

      <h3>Agents</h3>
      <table>
        <thead><tr><th>Agent</th><th>Squad</th><th>Owner</th><th>Status</th>
        <th>Rating</th><th>Lượt dùng</th><th>Hành động</th></tr></thead>
        <tbody>{a_rows}</tbody>
      </table>

      <h3 style="margin-top:26px">Squads</h3>
      <table>
        <thead><tr><th>Squad</th><th>Agent phụ trách</th><th>Hiệu quả mục tiêu</th><th>Xếp loại</th></tr></thead>
        <tbody>{s_rows}</tbody>
      </table>
    </section>"""


# --------------------------- AGENT BACKEND ---------------------------

def render_agent_backend(a: dict, squad_krs: list[dict]) -> str:
    aid = a["agent_id"]
    be = a["backend"]
    skills_chips = "".join(
        f'<span class="chip skill">{_esc(s)}'
        f'<button class="chip-x" onclick="rmSkill(this)" disabled>×</button></span>'
        for s in be["skills"]
    )
    kr_rows = "".join(
        f'<tr><td>{_esc(k["name"])}<div class="muted">{_esc(k["kr"])}</div></td>'
        f'<td>{bar(k["progress"])}</td></tr>'
        for k in squad_krs
    )
    log_rows = "".join(
        f'<tr><td class="muted">{_esc(l["time"])}</td><td>{_esc(l["user"])}</td>'
        f'<td>{_esc(l["action"])}</td><td class="num">{l["tokens"]:,}</td>'
        f'<td>{badge(l["status"], _LOG_KIND.get(l["status"],"neutral"))}</td></tr>'
        for l in be["logs"]
    )
    sched_rows = "".join(
        f'<tr><td>{_esc(j["name"])}</td><td><code>{_esc(j["cron"])}</code></td>'
        f'<td class="muted">{_esc(j["next"])}</td>'
        f'<td>{badge("bật" if j["enabled"] else "tắt", "good" if j["enabled"] else "neutral")}</td></tr>'
        for j in be["schedule"]
    ) or '<tr><td colspan="4" class="muted">Chưa có lịch nào.</td></tr>'

    total_inv = a["invocations"]
    return f"""
    <section id="view-agent-{aid}" class="view">
      <div class="subbar">
        <button class="btn btn-sm" onclick="backToPlatform()">← Platform</button>
        <div class="subbar-title">Backend: <b>{_esc(a["name"])}</b>
          <span class="tag">Vercel</span></div>
        <div class="subbar-right">
          <span class="muted">Owner</span> <b>{_esc(a["owner"])}</b>
          {badge(a["status"], _STATUS_KIND.get(a["status"],"neutral"))}
        </div>
      </div>
      <div class="owner-note">
        <label class="switch"><input type="checkbox" onchange="toggleOwner('{aid}',this.checked)"><span></span></label>
        Chế độ owner (bật để chỉnh sửa) — chỉ <b>{_esc(a["owner"])}</b> mới sửa được config.
      </div>

      <div class="tabs">
        <button class="tab active" onclick="showTab('{aid}','config',this)">Config</button>
        <button class="tab" onclick="showTab('{aid}','dash',this)">Dashboard</button>
        <button class="tab" onclick="showTab('{aid}','sched',this)">Schedule</button>
      </div>

      <div class="tabpane active" id="{aid}-config">
        <div class="grid2">
          <div class="card">
            <h4>System prompt</h4>
            <textarea class="ta" data-agent="{aid}" disabled rows="8">{_esc(be["system_prompt"])}</textarea>
          </div>
          <div class="card">
            <h4>Model</h4>
            <select class="cfg" data-agent="{aid}" disabled>
              <option>{_esc(be["model"])}</option>
            </select>
            <h4 style="margin-top:16px">Skills (MCP)</h4>
            <div class="chips" id="skills-{aid}">{skills_chips}</div>
            <div class="addskill">
              <input class="cfg" data-agent="{aid}" placeholder="thêm MCP skill..." disabled>
              <button class="btn btn-sm" onclick="addSkill('{aid}')" disabled>+ Thêm</button>
            </div>
            <div style="margin-top:14px">
              <button class="btn btn-primary cfg" data-agent="{aid}" disabled onclick="saveCfg('{aid}')">Lưu thay đổi</button>
            </div>
          </div>
        </div>
      </div>

      <div class="tabpane" id="{aid}-dash">
        <div class="kpis">
          {kpi("Lượt dùng", f"{total_inv:,}")}
          {kpi("Success", f"{a['success_rate']:.0%}")}
          {kpi("Rating", f"{a['rating']:.0f}", a["grade"])}
          {kpi("Khuyến nghị", _REC_LABEL[a["recommendation"]])}
        </div>
        <div class="grid2">
          <div class="card">
            <h4>Xu hướng sử dụng</h4>
            {sparkline(a["trend"])}
          </div>
          <div class="card">
            <h4>Kết quả squad phụ trách — {_esc(a["squad"])}</h4>
            <table class="tight"><thead><tr><th>Mục tiêu</th><th>Tiến độ</th></tr></thead>
            <tbody>{kr_rows}</tbody></table>
          </div>
        </div>
        <div class="card">
          <h4>Log gần đây</h4>
          <table class="tight"><thead><tr><th>Thời gian</th><th>Người dùng</th><th>Hành động</th>
          <th>Token</th><th>Kết quả</th></tr></thead><tbody>{log_rows}</tbody></table>
        </div>
      </div>

      <div class="tabpane" id="{aid}-sched">
        <div class="card">
          <div class="card-head"><h4>Lịch chạy (schedule)</h4>
            <button class="btn btn-sm cfg" data-agent="{aid}" disabled>+ Thêm lịch</button></div>
          <table class="tight"><thead><tr><th>Tên</th><th>Cron</th><th>Lần kế</th><th>Trạng thái</th></tr></thead>
          <tbody>{sched_rows}</tbody></table>
        </div>
      </div>
    </section>"""


# --------------------------- TEST & LEARN ---------------------------

_TEST_STATUS_KIND = {"draft": "neutral", "in_review": "warning", "active": "good", "archived": "neutral"}
_SOURCE_KIND = {"auto": "series", "manual": "neutral"}


def _testlearn_sample():
    order_q = [
        Question(question_id="q1", prompt="Trạng thái đơn đã giao?", expected="delivered",
                 assertion_type="contains", skill_id="order", tags=["order"]),
        Question(question_id="q2", prompt="Mã đơn hợp lệ có tiền tố?", expected="A-",
                 assertion_type="contains", skill_id="order", tags=["order"]),
    ]
    t_active = Test(test_id="TL-1", title="KT đơn hàng", status=TestStatus.ACTIVE,
                    reviewed_by="hr.lan", source="manual", questions=order_q, pass_threshold=0.8)
    t_review = Test(test_id="TL-2", title="KT vận hành kho", status=TestStatus.IN_REVIEW,
                    source="auto", pass_threshold=0.7,
                    questions=[Question(question_id="q1", prompt="Nguyên tắc xuất kho?",
                                        expected="fifo", skill_id="ops", tags=["ops"])])
    t_draft = Test(test_id="TL-3", title="An toàn dữ liệu KH", status=TestStatus.DRAFT,
                   source="manual", pass_threshold=0.8,
                   questions=[Question(question_id="q1", prompt="PII là gì?",
                                       expected="pii", skill_id="security", tags=["security"])])
    tests = [t_active, t_review, t_draft]
    mats = [
        TrainingMaterial(material_id="M-order", title="Quy trình đơn hàng", md_content="# Đơn hàng...",
                         tags=["order"], provided_by="HR", source_file="quy_trinh_don_hang.md"),
        TrainingMaterial(material_id="M-ops", title="Vận hành kho (FIFO)", md_content="# Kho...",
                         tags=["ops"], provided_by="HR", source_file="kho_fifo.docx"),
        TrainingMaterial(material_id="M-sec", title="Bảo mật dữ liệu KH", md_content="# Bảo mật...",
                         tags=["security"], provided_by="HR", source_file="bao_mat.pdf"),
    ]

    def _attempt(taker_type, taker_id, ans):
        score, passed, _ = grade(t_active, ans)
        rec = [] if passed else recommend_training(t_active, mats)
        return {"taker_id": taker_id, "taker_type": taker_type.value, "test": t_active.title,
                "score": round(score * 100), "passed": passed, "training": [m.title for m in rec]}

    attempts = [
        _attempt(TakerType.AGENT, "Order Lookup Bot",
                 [Answer(question_id="q1", response="order is delivered"),
                  Answer(question_id="q2", response="mã A-1023")]),
        _attempt(TakerType.AGENT, "Chat Helper Bot",
                 [Answer(question_id="q1", response="không rõ"),
                  Answer(question_id="q2", response="123")]),
        _attempt(TakerType.HUMAN, "nv.binh",
                 [Answer(question_id="q1", response="delivered"),
                  Answer(question_id="q2", response="mã A-9")]),
    ]
    return tests, attempts, mats


def render_testlearn() -> str:
    tests, attempts, mats = _testlearn_sample()
    n_active = sum(1 for t in tests if t.status == TestStatus.ACTIVE)
    n_review = sum(1 for t in tests if t.status in (TestStatus.DRAFT, TestStatus.IN_REVIEW))

    test_rows = ""
    for t in tests:
        st = t.status.value
        actions = (
            f'<button class="btn btn-sm btn-primary" onclick="assignTest(\'{t.test_id}\')">Giao bài</button>'
            if st == "active" else
            f'<button class="btn btn-sm" id="tlreview-{t.test_id}" onclick="reviewTest(\'{t.test_id}\')">Duyệt →</button>'
        )
        test_rows += (
            f'<tr><td><b>{_esc(t.title)}</b><div class="muted">{_esc(t.test_id)}</div></td>'
            f'<td>{badge(t.source, _SOURCE_KIND.get(t.source,"neutral"))}</td>'
            f'<td id="tlstatus-{t.test_id}">{badge(st, _TEST_STATUS_KIND.get(st,"neutral"))}</td>'
            f'<td class="num">{len(t.questions)}</td>'
            f'<td class="num">{t.pass_threshold:.0%}</td>'
            f'<td>{_esc(t.reviewed_by or "—")}</td>'
            f'<td class="actions">{actions}</td></tr>'
        )

    att_rows = ""
    for a in attempts:
        tkind = "series" if a["taker_type"] == "agent" else "neutral"
        training = chips(a["training"]) if a["training"] else '<span class="muted">—</span>'
        att_rows += (
            f'<tr><td><b>{_esc(a["taker_id"])}</b></td>'
            f'<td>{badge(a["taker_type"], tkind)}</td><td>{_esc(a["test"])}</td>'
            f'<td>{bar(a["score"])}</td>'
            f'<td>{badge("pass" if a["passed"] else "fail", "good" if a["passed"] else "critical")}</td>'
            f'<td>{training}</td></tr>'
        )

    mat_rows = "".join(
        f'<tr><td><b>{_esc(m.title)}</b></td><td>{chips(m.tags)}</td>'
        f'<td>{_esc(m.provided_by)}</td><td class="muted">{_esc(m.source_file)}</td></tr>'
        for m in mats
    )

    return f"""
    <section id="view-testlearn" class="view">
      <h1>Test &amp; Learn</h1>
      <p class="lead">Tạo bài test (nhiều case) → <b>người review mới active</b> → giao
         cho agent/nhân sự làm → trượt thì <b>training lại</b> (tài liệu do HR cung cấp).</p>
      <div class="tabs">
        <button class="tab active" onclick="showTL('tests',this)">Bài test</button>
        <button class="tab" onclick="showTL('results',this)">Kết quả</button>
        <button class="tab" onclick="showTL('training',this)">Training (HR)</button>
      </div>

      <div class="tabpane active" id="tl-tests">
        <div class="kpis">
          {kpi("Tổng bài test", str(len(tests)))}
          {kpi("Đang active", str(n_active))}
          {kpi("Chờ review", str(n_review))}
        </div>
        <table>
          <thead><tr><th>Bài test</th><th>Nguồn</th><th>Trạng thái</th><th>Số câu</th>
          <th>Ngưỡng</th><th>Người duyệt</th><th>Hành động</th></tr></thead>
          <tbody>{test_rows}</tbody>
        </table>
        <p class="muted" style="margin-top:8px">Bài <code>auto</code> do hệ sinh tự động
           vẫn phải <b>Duyệt</b> mới dùng được.</p>
      </div>

      <div class="tabpane" id="tl-results">
        <table>
          <thead><tr><th>Người làm</th><th>Loại</th><th>Bài test</th><th>Điểm</th>
          <th>Kết quả</th><th>Training gợi ý (nếu trượt)</th></tr></thead>
          <tbody>{att_rows}</tbody>
        </table>
      </div>

      <div class="tabpane" id="tl-training">
        <div class="card-head" style="margin-bottom:12px">
          <h3 style="margin:0">Tài liệu training (HR cung cấp)</h3>
          <button class="btn btn-sm btn-primary" onclick="importTraining()">+ Import file → markdown</button>
        </div>
        <table>
          <thead><tr><th>Tài liệu</th><th>Tags</th><th>Nguồn</th><th>File gốc</th></tr></thead>
          <tbody>{mat_rows}</tbody>
        </table>
      </div>
    </section>"""


# --------------------------- Lắp trang ---------------------------

def _assemble():
    config = load_scoring_config(load_settings().scoring_config_path)
    agent_metrics = build_sample_agents()
    squads = build_sample_squads()
    agent_evals = {e.agent_id: e for e in AgentScorer(config).score_all(agent_metrics)}
    squad_evals = {e.squad_id: e for e in SquadScorer(config).score_all(squads)}
    m_by_id = {m.agent_id: m for m in agent_metrics}
    sq_by_id = {s.squad_id: s for s in squads}

    agents: list[dict] = []
    for aid, reg in sample.AGENT_REGISTRY.items():
        if aid not in AGENT_BACKEND:
            continue
        be = AGENT_BACKEND[aid]
        ev = agent_evals[aid]
        m = m_by_id[aid]
        sq = sq_by_id[be["primary_squad"]]
        agents.append({
            "agent_id": aid,
            "name": reg_name(aid, m),
            "owner": reg["owner"],
            "squad": sq.squad_name,
            "status": reg["status"],
            "rating": ev.total_score,
            "grade": ev.grade,
            "recommendation": ev.status_recommendation.value,
            "invocations": m.invocations,
            "success_rate": m.success_rate,
            "trend": sample.USAGE_TREND.get(aid, []),
            "backend": be,
        })

    squad_rows = []
    # agent phụ trách mỗi squad = agent có primary_squad = squad
    primary_of = {be["primary_squad"]: aid for aid, be in AGENT_BACKEND.items()}
    for sid, s in sq_by_id.items():
        se = squad_evals[sid]
        squad_rows.append({
            "squad_id": sid,
            "name": s.squad_name,
            "primary_agent": next((a["name"] for a in agents if a["agent_id"] == primary_of.get(sid)), "—"),
            "objective_score": se.objective_score,
            "grade": se.grade,
        })
    return agents, squad_rows, sq_by_id


def reg_name(aid: str, metrics) -> str:
    return metrics.agent_name or aid


def render_html() -> str:
    agents, squad_rows, sq_by_id = _assemble()
    backends = ""
    for a in agents:
        sq = sq_by_id[a["backend"]["primary_squad"]]
        krs = [{"name": kr.objective_name, "kr": kr.key_result, "progress": kr.progress()}
               for kr in sq.key_results]
        backends += render_agent_backend(a, krs)
    body = render_platform(agents, squad_rows) + backends + render_testlearn()
    return _TEMPLATE.replace("{{BODY}}", body)


def build(output: Path | str = "output/platform.html") -> Path:
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(), encoding="utf-8")
    return out


def main() -> None:  # pragma: no cover
    print(f"Đã sinh prototype platform: {build()}")


_TEMPLATE = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>LSR Agent Platform — prototype</title>
<style>
:root{color-scheme:light;
  --surface-1:#fcfcfb;--plane:#f9f9f7;--text-primary:#0b0b0b;--text-secondary:#52514e;--muted:#898781;
  --grid:#e1e0d9;--border:rgba(11,11,11,.10);--series-1:#2a78d6;--series-soft:#eaf2fc;
  --good:#0ca30c;--warning:#fab219;--critical:#d03b3b;--star:#eda100;}
:root[data-theme="dark"]{color-scheme:dark;
  --surface-1:#1a1a19;--plane:#0d0d0d;--text-primary:#fff;--text-secondary:#c3c2b7;--muted:#898781;
  --grid:#2c2c2a;--border:rgba(255,255,255,.10);--series-1:#3987e5;--series-soft:#17293d;--star:#eda100;}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;
  --surface-1:#1a1a19;--plane:#0d0d0d;--text-primary:#fff;--text-secondary:#c3c2b7;--muted:#898781;
  --grid:#2c2c2a;--border:rgba(255,255,255,.10);--series-1:#3987e5;--series-soft:#17293d;}}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--text-primary);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:14px;line-height:1.5}
.topbar{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:14px;
  background:var(--surface-1);border-bottom:1px solid var(--border);padding:12px 22px}
.topbar .brand{font-weight:700}
.topbar .brand span{color:var(--muted);font-weight:400;font-size:12px}
.spacer{flex:1}
.theme-btn{border:1px solid var(--border);background:transparent;color:var(--text-secondary);
  padding:6px 10px;border-radius:8px;cursor:pointer;font-family:inherit}
.navlink{border:0;background:transparent;color:var(--text-secondary);padding:6px 12px;
  border-radius:8px;cursor:pointer;font-family:inherit;font-size:14px}
.navlink:hover{background:var(--series-soft)}
.navlink.active{background:var(--series-soft);color:var(--text-primary);font-weight:600}
.wrap{max-width:1080px;margin:0 auto;padding:24px 22px}
.view{display:none}.view.active{display:block}
h1{font-size:24px;margin:0 0 4px}h3{font-size:16px;margin:22px 0 10px}
h4{font-size:13px;margin:0 0 10px;color:var(--text-secondary)}
.lead{color:var(--text-secondary);margin:0 0 18px;max-width:72ch}
.muted{color:var(--muted);font-size:12px}
code{background:var(--series-soft);padding:1px 6px;border-radius:4px;font-size:12px}
.kpis{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:18px}
.kpi{background:var(--surface-1);border:1px solid var(--border);border-radius:12px;padding:13px 15px;min-width:110px}
.kpi-label{color:var(--muted);font-size:12px}.kpi-val{font-size:24px;font-weight:700;margin-top:2px}
.kpi-sub{color:var(--text-secondary);font-size:12px}
table{width:100%;border-collapse:collapse;background:var(--surface-1);border:1px solid var(--border);border-radius:12px;overflow:hidden}
th,td{text-align:left;padding:11px 14px;border-bottom:1px solid var(--grid);vertical-align:middle}
th{font-size:11px;text-transform:uppercase;letter-spacing:.03em;color:var(--muted);font-weight:600}
tr:last-child td{border-bottom:0}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
table.tight th,table.tight td{padding:9px 12px}
td.actions{white-space:nowrap;display:flex;gap:6px}
.bar{position:relative;height:22px;background:var(--grid);border-radius:6px;min-width:120px;overflow:hidden}
.bar-fill{position:absolute;left:0;top:0;bottom:0;background:var(--series-1);border-radius:6px}
.bar-fill.good{background:var(--good)}
.bar-val{position:absolute;right:7px;top:0;line-height:22px;font-size:11.5px;font-variant-numeric:tabular-nums}
.badge{display:inline-flex;align-items:center;gap:5px;padding:3px 9px;border-radius:999px;font-size:12px;font-weight:500;border:1px solid var(--border);white-space:nowrap}
.badge-i{display:inline-flex;width:14px;height:14px;border-radius:50%;align-items:center;justify-content:center;font-size:10px;color:#fff}
.badge-good{background:color-mix(in srgb,var(--good) 12%,transparent);color:var(--good)}.badge-good .badge-i{background:var(--good)}
.badge-warning{background:color-mix(in srgb,var(--warning) 16%,transparent);color:#8a6100}.badge-warning .badge-i{background:var(--warning);color:#3a2900}
.badge-critical{background:color-mix(in srgb,var(--critical) 12%,transparent);color:var(--critical)}.badge-critical .badge-i{background:var(--critical)}
.badge-neutral{background:transparent;color:var(--text-secondary)}.badge-neutral .badge-i{background:var(--muted)}
:root[data-theme="dark"] .badge-warning{color:var(--warning)}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]) .badge-warning{color:var(--warning)}}
.btn{border:1px solid var(--border);background:var(--surface-1);color:var(--text-primary);
  padding:7px 12px;border-radius:8px;cursor:pointer;font-family:inherit;font-size:13px}
.btn:hover{background:var(--series-soft)}
.btn-sm{padding:5px 10px;font-size:12.5px}
.btn-primary{background:var(--series-1);color:#fff;border-color:transparent}
.btn-primary:hover{filter:brightness(1.05);background:var(--series-1)}
.btn:disabled{opacity:.5;cursor:not-allowed}
.stars{white-space:nowrap;cursor:pointer}
.star{color:var(--grid);font-size:15px}.star.on{color:var(--star)}
.subbar{display:flex;align-items:center;gap:14px;background:var(--surface-1);border:1px solid var(--border);
  border-radius:12px;padding:12px 16px;margin-bottom:12px}
.subbar-title{font-size:15px}.subbar-right{margin-left:auto;display:flex;align-items:center;gap:10px}
.tag{background:var(--series-soft);color:var(--series-1);padding:2px 8px;border-radius:6px;font-size:11px;margin-left:6px}
.owner-note{display:flex;align-items:center;gap:10px;background:color-mix(in srgb,var(--warning) 12%,transparent);
  border-radius:10px;padding:10px 14px;font-size:13px;color:var(--text-secondary);margin-bottom:16px}
.switch{position:relative;display:inline-block;width:38px;height:22px;flex:none}
.switch input{opacity:0;width:0;height:0}
.switch span{position:absolute;inset:0;background:var(--grid);border-radius:999px;transition:.2s}
.switch span:before{content:"";position:absolute;width:16px;height:16px;left:3px;top:3px;background:#fff;border-radius:50%;transition:.2s}
.switch input:checked+span{background:var(--series-1)}
.switch input:checked+span:before{transform:translateX(16px)}
.tabs{display:flex;gap:6px;border-bottom:1px solid var(--border);margin-bottom:16px}
.tab{border:0;background:transparent;color:var(--text-secondary);padding:9px 14px;cursor:pointer;
  font-family:inherit;font-size:13.5px;border-bottom:2px solid transparent;margin-bottom:-1px}
.tab.active{color:var(--text-primary);font-weight:600;border-bottom-color:var(--series-1)}
.tabpane{display:none}.tabpane.active{display:block}
.card{background:var(--surface-1);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:16px}
.card-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:10px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}.grid2 .card{margin:0}
.ta{width:100%;font-family:ui-monospace,monospace;font-size:12.5px;padding:10px;border-radius:8px;
  border:1px solid var(--border);background:var(--plane);color:var(--text-primary);resize:vertical}
.cfg,select.cfg{font-family:inherit}
input.cfg,select.cfg,select{font-size:13px;padding:7px 10px;border-radius:8px;border:1px solid var(--border);
  background:var(--surface-1);color:var(--text-primary)}
.ta:disabled,input:disabled,select:disabled{opacity:.7}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip{background:var(--series-soft);color:var(--text-secondary);padding:3px 8px;border-radius:999px;font-size:12px;display:inline-flex;align-items:center;gap:4px}
.chip-x{border:0;background:transparent;color:var(--muted);cursor:pointer;font-size:14px;line-height:1;padding:0}
.chip-x:disabled{opacity:.4;cursor:not-allowed}
.addskill{display:flex;gap:8px;margin-top:8px}
.spark{display:block;width:100%;height:40px}
@media(max-width:820px){.grid2{grid-template-columns:1fr}td.actions{flex-wrap:wrap}}
</style></head>
<body>
<div class="topbar">
  <div class="brand">LSR Agent Platform <span>· prototype</span></div>
  <button class="navlink active" id="nav-platform" onclick="goView('platform')">Platform</button>
  <button class="navlink" id="nav-testlearn" onclick="goView('testlearn')">Test &amp; Learn</button>
  <div class="spacer"></div>
  <span class="muted" id="crumb"></span>
  <button class="theme-btn" onclick="toggleTheme()">◐</button>
</div>
<div class="wrap">{{BODY}}</div>
<script>
function show(id){document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id===id));
  window.scrollTo(0,0);}
function goView(name){show('view-'+name);
  document.querySelectorAll('.navlink').forEach(n=>n.classList.toggle('active',n.id==='nav-'+name));
  document.getElementById('crumb').textContent='';}
function openAgent(id){show('view-agent-'+id);document.getElementById('crumb').textContent='Backend: '+id;}
function backToPlatform(){show('view-platform');document.getElementById('crumb').textContent='';
  document.querySelectorAll('.navlink').forEach(n=>n.classList.toggle('active',n.id==='nav-platform'));}
function showTL(tab,btn){document.querySelectorAll('#view-testlearn .tabpane').forEach(p=>p.classList.toggle('active',p.id==='tl-'+tab));
  btn.parentNode.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));btn.classList.add('active');}
function reviewTest(id){var c=document.getElementById('tlstatus-'+id);
  c.innerHTML='<span class="badge badge-good"><span class="badge-i">✓</span>active</span>';
  var b=document.getElementById('tlreview-'+id);if(b)b.remove();
  alert('(prototype) Đã duyệt '+id+' → active. Giờ mới giao bài được.');}
function assignTest(id){alert('(prototype) Chọn agent đã đăng ký để giao bài '+id);}
function importTraining(){alert('(prototype) Import file training của công ty → chuyển sang markdown → lưu lại.');}
function showTab(aid,tab,btn){
  document.querySelectorAll('#view-agent-'+aid+' .tabpane').forEach(p=>p.classList.toggle('active',p.id===aid+'-'+tab));
  btn.parentNode.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));btn.classList.add('active');
}
function toggleOwner(aid,on){
  document.querySelectorAll('#view-agent-'+aid+' .ta, #view-agent-'+aid+' .cfg, #view-agent-'+aid+' .chip-x')
    .forEach(el=>el.disabled=!on);
}
function toggleStatus(id){
  const cell=document.getElementById('pstatus-'+id), btn=document.getElementById('ptoggle-'+id);
  const active=cell.textContent.trim().startsWith('active');
  cell.innerHTML='<span class="badge badge-'+(active?'critical':'good')+'"><span class="badge-i">'
    +(active?'✕':'✓')+'</span>'+(active?'deactivated':'active')+'</span>';
  btn.textContent=active?'Activate':'Deactivate';
}
function rate(aid,n){const s=document.getElementById('stars-'+aid);
  [...s.children].forEach((el,i)=>el.classList.toggle('on',i<n));}
function addSkill(aid){const box=document.getElementById('skills-'+aid);
  const inp=document.querySelector('#view-agent-'+aid+' .addskill input');if(!inp.value)return;
  const c=document.createElement('span');c.className='chip skill';
  c.innerHTML=inp.value+'<button class="chip-x" onclick="rmSkill(this)">×</button>';box.appendChild(c);inp.value='';}
function rmSkill(b){b.parentNode.remove();}
function saveCfg(aid){alert('(prototype) Đã lưu config cho '+aid);}
function toggleTheme(){const r=document.documentElement;
  const dark=r.getAttribute('data-theme')==='dark'||(!r.getAttribute('data-theme')&&matchMedia('(prefers-color-scheme:dark)').matches);
  r.setAttribute('data-theme',dark?'light':'dark');}
</script>
</body></html>"""


if __name__ == "__main__":  # pragma: no cover
    main()
