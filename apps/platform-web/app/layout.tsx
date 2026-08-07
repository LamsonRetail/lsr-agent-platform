import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "LSR Agent Platform",
  description: "Nền tảng agent nội bộ LamsonRetail",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body>
        <div className="topbar">
          <div className="brand">LSR Agent Platform <span>· web</span></div>
          <nav className="nav">
            <Link href="/">Platform</Link>
            <Link href="/cost">Chi phí</Link>
            <Link href="/health">Sức khoẻ</Link>
            <Link href="/test-learn">Test &amp; Learn</Link>
            <Link href="/golden">Golden</Link>
            <Link href="/review">Duyệt tri thức</Link>
            <Link href="/audit">Audit</Link>
          </nav>
          <div className="spacer" />
          <span className="muted">dữ liệu live</span>
        </div>
        <main className="wrap">{children}</main>
      </body>
    </html>
  );
}
