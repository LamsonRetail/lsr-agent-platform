import LoginForm from "@/components/LoginForm";
export const dynamic = "force-dynamic";

export default function LoginPage({ searchParams }: { searchParams: { next?: string; err?: string } }) {
  return (
    <div style={{ maxWidth: 380, margin: "8vh auto" }}>
      <h1 style={{ marginBottom: 4 }}>LSR Agent Platform</h1>
      <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
        Đăng nhập bằng tài khoản công ty hoặc bằng Lark — tài khoản Lark thuộc org
        sẽ được tự mở với quyền user.
      </p>
      {searchParams?.err && <p className="err" style={{ fontSize: 13 }}>{searchParams.err}</p>}
      <LoginForm next={searchParams?.next || "/"} />
    </div>
  );
}
