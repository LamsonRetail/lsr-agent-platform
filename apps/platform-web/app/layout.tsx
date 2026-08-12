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
  return (
    <html lang="vi">
      <body>
        <div className="topbar">
          <div className="brand">LSR Agent Platform <span>· web</span></div>
          <nav className="nav">
            <Link href="/">Platform</Link>
            {u?.platform_role === "admin" && <Link href="/approvals">Duyệt việc</Link>}
            {(u?.can_create_agent) && <Link href="/builder">Builder</Link>}
            {(u?.can_create_agent) && <Link href="/jobs">Ingress</Link>}
            {u?.platform_role === "admin" && <Link href="/connectors">Connectors</Link>}
            {u?.platform_role === "admin" && <Link href="/model-auth">Model Auth</Link>}
            {u?.can_manage_accounts && <Link href="/accounts">Tài khoản</Link>}
            <Link href="/cost">Chi phí</Link>
            <Link href="/health">Sức khoẻ</Link>
            <Link href="/test-learn">Test &amp; Learn</Link>
            <Link href="/golden">Golden</Link>
            <Link href="/brain">Brain Console</Link>
            <Link href="/review">Duyệt tri thức</Link>
            <Link href="/brain-3d">Brain 3D</Link>
            <Link href="/audit">Audit</Link>
          </nav>
          <div className="spacer" />
          {u ? <UserBadge name={u.name} email={u.email} role={u.platform_role} />
             : <span className="muted">chưa đăng nhập</span>}
        </div>
        <main className="wrap">{children}</main>
      </body>
    </html>
  );
}
