"use client";
import { useRef, useState, useCallback } from "react";
import dynamic from "next/dynamic";

// three.js/WebGL chỉ chạy client → import động, tắt SSR.
const ForceGraph3D = dynamic(() => import("react-force-graph-3d"), { ssr: false });

const COLOR: Record<string, string> = {
  domain: "#c98a00",     // chuyên môn
  belief: "#7a5cff",     // niềm tin chung (admin)
  knowledge: "#2e9e5b",  // tri thức đã duyệt
  team: "#4a7edb",       // team nguồn
};
const KIND: Record<string, string> = {
  domain: "Chuyên môn", belief: "Shared belief", knowledge: "Tri thức", team: "Team nguồn",
  skill: "Kỹ năng", policy: "Chính sách",
};
// Màu cạnh theo LOẠI quan hệ (typed edges); cạnh cấu trúc mờ.
const REL_COLOR: Record<string, string> = {
  relates_to: "#8892a6", depends_on: "#3b7bc4", derived_from: "#5b5bd6", supersedes: "#b7791f",
  contradicts: "#d1495b", refines: "#1f9d57", uses_skill: "#12a4a4", governed_by: "#a4128f",
  in_domain: "#ffffff22", from_team: "#ffffff22",
};

export default function Brain3D({ data }: { data: { nodes: any[]; links: any[]; counts: any } }) {
  const fgRef = useRef<any>(null);
  const [sel, setSel] = useState<any>(null);

  const onNodeClick = useCallback((node: any) => {
    setSel(node);
    // bay camera tới node cho trực quan
    const fg = fgRef.current;
    if (fg && node) {
      const d = 90;
      const r = 1 + d / Math.hypot(node.x || 1, node.y || 1, node.z || 1);
      fg.cameraPosition({ x: (node.x || 0) * r, y: (node.y || 0) * r, z: (node.z || 0) * r },
                        node, 800);
    }
  }, []);

  return (
    <div style={{ position: "relative" }}>
      <div style={{ height: "72vh", borderRadius: 12, overflow: "hidden", border: "1px solid #0002" }}>
        <ForceGraph3D
          ref={fgRef}
          graphData={data}
          backgroundColor="#0b0b12"
          nodeLabel={(n: any) => `${KIND[n.type] || n.type}: ${n.label}`}
          nodeColor={(n: any) => COLOR[n.type] || "#999"}
          nodeVal={(n: any) => (n.type === "domain" ? 6 : n.type === "team" ? 5 : 2)}
          nodeOpacity={0.9}
          linkColor={(l: any) => REL_COLOR[l.rel] || "#ffffff33"}
          linkWidth={(l: any) => (l.rel && !["in_domain", "from_team"].includes(l.rel) ? 1.5 : 0.5)}
          linkDirectionalParticles={(l: any) => (l.rel && !["in_domain", "from_team"].includes(l.rel) ? 2 : 0)}
          linkDirectionalParticleWidth={1.6}
          onNodeClick={onNodeClick}
        />
      </div>

      {/* Chú thích */}
      <div style={{ position: "absolute", top: 10, left: 12, display: "flex", gap: 12, flexWrap: "wrap",
                    background: "#0009", padding: "6px 10px", borderRadius: 8, fontSize: 12, color: "#fff" }}>
        {Object.entries(KIND).map(([k, v]) => (
          <span key={k}><span style={{ color: COLOR[k] }}>●</span> {v}
            {" "}({data.counts?.[k] ?? 0})</span>
        ))}
      </div>

      {/* Panel chi tiết khi click node */}
      {sel && (
        <div style={{ position: "absolute", top: 10, right: 12, width: 320, maxHeight: "66vh",
                      overflow: "auto", background: "var(--card,#fff)", color: "inherit",
                      border: "1px solid #0002", borderRadius: 12, padding: 14, boxShadow: "0 6px 24px #0003" }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <span className="b b-neutral">{KIND[sel.type] || sel.type}</span>
            <button className="btn" onClick={() => setSel(null)}>×</button>
          </div>
          <h3 style={{ margin: "8px 0 4px" }}>{sel.label}</h3>
          {sel.domain && <div className="muted" style={{ fontSize: 12 }}>Chuyên môn: {sel.domain}</div>}
          {sel.source_team && <div className="muted" style={{ fontSize: 12 }}>Team: {sel.source_team}</div>}
          {sel.detail && <p style={{ fontSize: 13, whiteSpace: "pre-wrap" }}>{sel.detail}</p>}
          {sel.source_url ? (
            <a href={sel.source_url} target="_blank" rel="noreferrer" className="btn btn-p"
               style={{ display: "inline-block", marginTop: 6 }}>Mở nguồn Lark ↗</a>
          ) : (
            (sel.type === "knowledge" || sel.type === "belief") &&
            <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>⚠ Thiếu link nguồn (source_url)</div>
          )}
          <div style={{ marginTop: 8 }}>
            <a href="/review" className="muted" style={{ fontSize: 12 }}>→ xem/duyệt trong Review</a>
          </div>
        </div>
      )}
    </div>
  );
}
