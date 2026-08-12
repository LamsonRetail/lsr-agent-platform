import { pendingActions, martKpi } from "@/lib/platform";
import ApprovalsConsole from "@/components/ApprovalsConsole";

export const dynamic = "force-dynamic";

export default async function ApprovalsPage() {
  const [actions, kpi] = await Promise.all([pendingActions("?limit=100"), martKpi(7)]);
  return (
    <>
      <h1>Duyệt việc &amp; KPI</h1>
      <p className="lead">
        Platform agent (AG-OPS, AG-EVAL) quan sát và <b>đề xuất</b>; người vận hành <b>duyệt</b>.
        Việc rủi ro thấp tự chạy nhưng vẫn ghi log. Không ai được tự duyệt đề xuất của chính mình.
      </p>
      <ApprovalsConsole actions={actions} kpi={kpi} />
    </>
  );
}
