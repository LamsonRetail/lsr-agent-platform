import LoginForm from "@/components/LoginForm";
export const dynamic = "force-dynamic";

export default function LoginPage({ searchParams }: { searchParams: { next?: string } }) {
  return (
    <div style={{ maxWidth: 380, margin: "8vh auto" }}>
      <h1 style={{ marginBottom: 4 }}>LSR Agent Platform</h1>
      <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
        Đăng nhập bằng tài khoản công ty. Chưa có tài khoản? Liên hệ quản trị platform.
      </p>
      <LoginForm next={searchParams?.next || "/"} />
    </div>
  );
}
