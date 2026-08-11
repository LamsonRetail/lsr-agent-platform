import { routingList, jobsList, listAgents } from "@/lib/platform";
import JobsConsole from "@/components/JobsConsole";

export const dynamic = "force-dynamic";

export default async function JobsPage({ searchParams }: { searchParams: { status?: string } }) {
  const status = searchParams?.status || "";
  const qs = status ? `?status=${encodeURIComponent(status)}&limit=100` : "?limit=100";
  const [routes, jobs, agents] = await Promise.all([
    routingList(), jobsList(qs), listAgents(),
  ]);
  return (
    <>
      <h1>Ingress · Routing &amp; Jobs</h1>
      <p className="lead">
        Cổng sự kiện hợp nhất: mọi kênh (Lark, web chat, cron, webhook, A2A) vào một hàng đợi.
        Thêm agent = thêm 1 binding. Job lỗi tự retry → DLQ; replay lại từ đây.
      </p>
      <JobsConsole routes={routes} jobs={jobs} agents={agents} status={status} />
    </>
  );
}
