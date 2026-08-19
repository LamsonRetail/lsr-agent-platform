import "./globals.css";
import Link from "next/link";
export const metadata = { title: "Agent Backend · AG-LEGAL" };
export default function L({ children }){ return (<html lang="vi"><body><div className="wrap">
  <nav className="row" style={{ marginBottom: 14, gap: 14 }}>
    <Link href="/">Dashboard</Link><Link href="/traces">Chi tiết</Link><Link href="/brain">Brain</Link><Link href="/config">Config</Link>
  </nav>
  {children}
</div></body></html>); }
