import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";
import { me } from "@/lib/session";
import UserBadge from "@/components/UserBadge";

export const metadata: Metadata = {
  title: "LSR Agent Platform",
  description: "Nền tảng agent nội bộ LamsonRetail",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const u = await me();
  const isAdmin = u?.platform_role === "admin";
  const canBuild = !!u?.can_create_agent;

  // Menu DỌC bên trái, gom theo nhóm công việc — không phình khi thêm trang.
  const groups: { title: string; items: [string, string, boolean][] }[] = [
    {
      title: "Tổng quan",
      items: [
        ["/", "📊 Platform", true],
        ["/cost", "💰 Chi phí", true],
        ["/health", "🩺 Sức khoẻ", true],
      ],
    },
    {
      title: "Agent",
      items: [
        ["/agents/new", "➕ Tạo agent", canBuild],
        ["/builder", "🛠 Builder", canBuild],
        ["/jobs", "🔀 Ingress", canBuild],
      ],
    },
    {
      title: "Tri thức",
      items: [
        ["/brain", "🧠 Brain Console", true],
        ["/review", "✅ Duyệt tri thức", true],
        ["/brain-3d", "🌐 Brain 3D", true],
      ],
    },
    {
      title: "Chất lượng",
      items: [
        ["/golden", "🎯 Golden", true],
        ["/test-learn", "🧪 Test & Learn", true],
      ],
    },
    {
      title: "Quản trị",
      items: [
        ["/approvals", "📋 Duyệt việc", isAdmin],
        ["/connectors", "🔌 Connectors", isAdmin],
        ["/model-auth", "🔑 Model Auth", isAdmin],
        ["/accounts", "👥 Tài khoản", !!u?.can_manage_accounts],
        ["/audit", "📜 Audit", true],
      ],
    },
  ];

  return (
    <html lang="vi">
      <body>
        <div className="shell">
          <aside className="side">
            <div className="brand">LSR Agent Platform</div>
            {groups.map((g) => {
              const items = g.items.filter(([, , show]) => show);
              if (!items.length) return null;
              return (
                <div className="grp" key={g.title}>
                  <div className="grp-t">{g.title}</div>
                  {items.map(([href, label]) => (
                    <Link href={href} key={href}>{label}</Link>
                  ))}
                </div>
              );
            })}
            <div className="foot">
              {u ? <UserBadge name={u.name} email={u.email} role={u.platform_role} />
                : <span className="muted" style={{ fontSize: 12 }}>chưa đăng nhập</span>}
            </div>
          </aside>
          <div className="content">
            <main className="wrap">{children}</main>
          </div>
        </div>
      </body>
    </html>
  );
}
