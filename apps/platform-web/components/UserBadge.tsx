"use client";
import { useRouter } from "next/navigation";

export default function UserBadge({ name, email, role }:
  { name: string; email: string; role: string | null }) {
  const router = useRouter();
  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login"); router.refresh();
  }
  const color: Record<string, string> = { admin: "#d1495b", moderator: "#c98a00", user: "#4a7edb" };
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 12 }}>
      <span title={email}>{name}</span>
      <span style={{ color: color[role || "user"], fontWeight: 600 }}>{role || "—"}</span>
      <button className="btn" style={{ fontSize: 11, padding: "1px 7px" }} onClick={logout}>Đăng xuất</button>
    </span>
  );
}
