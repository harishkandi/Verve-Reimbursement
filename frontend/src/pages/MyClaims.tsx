import { CalendarClock, CheckCircle2, Clock3, PenLine, Plus, Receipt } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { get, post } from "../api";
import { useMe } from "../auth";
import { ClaimTable, Empty, ErrorNote, PageHead, SkeletonRows, Stat } from "../components/ui";
import { day, money, monthLabel, thisPeriod } from "../format";
import type { ClaimDetail, ClaimSummary, Policy } from "../types";
import { useLoad } from "../useLoad";

const IN_REVIEW = ["submitted", "manager_approved", "verified", "in_payout_batch"];

function actionFoot(claims: ClaimSummary[]): string {
  const returned = claims.filter((c) => c.status === "returned").length;
  const drafts = claims.filter((c) => c.status === "draft").length;
  const parts = [
    returned && `${returned} returned for changes`,
    drafts && `${drafts} ${drafts === 1 ? "draft" : "drafts"} to submit`,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "Nothing pending";
}

export default function MyClaimsPage() {
  const me = useMe();
  const navigate = useNavigate();
  const { data: claims, error } = useLoad(() => get<ClaimSummary[]>("/api/claims"));
  const { data: policy } = useLoad(() => get<Policy>("/api/policy"));
  const [period, setPeriod] = useState(thisPeriod());
  const [busy, setBusy] = useState(false);
  const [openError, setOpenError] = useState<string | null>(null);

  async function open(p = period) {
    setBusy(true);
    setOpenError(null);
    try {
      // Returns the existing claim if this month already has one.
      const claim = await post<ClaimDetail>("/api/claims", { period: p });
      navigate(`/claims/${claim.id}`);
    } catch (e) {
      setOpenError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const [y, m] = thisPeriod().split("-").map(Number);
  const prevPeriod = m === 1 ? `${y - 1}-12` : `${y}-${String(m - 1).padStart(2, "0")}`;
  const due = `${y}-${String(m).padStart(2, "0")}-${String(policy?.submission_due_day ?? 5).padStart(2, "0")}`;
  const list = claims ?? [];
  const inReview = list.filter((c) => IN_REVIEW.includes(c.status));
  const paidThisYear = list.filter((c) => c.status === "paid" && c.paid_at?.startsWith(String(y)));
  const yours = list.filter((c) => c.status === "draft" || c.status === "returned");
  const sum = (cs: ClaimSummary[], key: "total_claimed" | "total_approved") => cs.reduce((s, c) => s + Number(c[key]), 0);
  const prevDone = list.some((c) => c.period === prevPeriod && !["draft", "returned"].includes(c.status));

  return (
    <>
      <PageHead title={`Hello, ${me.name.split(" ")[0]}`} sub="Your reimbursement claims, one per month.">
        <input className="input" type="month" aria-label="Claim month" value={period} max={thisPeriod()} style={{ width: 168 }}
          onChange={(e) => setPeriod(e.target.value)} />
        <button className="btn btn-primary" onClick={() => open()} disabled={busy || !period}>
          <Plus size={16} /> Open claim
        </button>
      </PageHead>
      <ErrorNote error={error || openError} />

      <div className="stats">
        <Stat icon={PenLine} label="Needs your action" value={yours.length} foot={actionFoot(yours)} />
        <Stat icon={Clock3} label="On its way" value={money(sum(inReview, "total_claimed"))}
          foot={inReview.length ? `${inReview.length} ${inReview.length === 1 ? "claim" : "claims"} in review or awaiting payout` : "Nothing in review"} />
        <Stat icon={CheckCircle2} label={`Paid in ${y}`} value={money(sum(paidThisYear, "total_approved"))}
          foot={`${paidThisYear.length} ${paidThisYear.length === 1 ? "claim" : "claims"}`} />
        <Stat icon={CalendarClock} label="Next deadline" value={day(due).slice(0, 6)}
          foot={prevDone ? `${monthLabel(prevPeriod)} already submitted` : `For ${monthLabel(prevPeriod)} expenses`} />
      </div>

      <section className="card">
        <div className="card-head">
          <div>
            <h2>All claims</h2>
            <div className="hint">Open a claim to add expenses, attach bills or follow its progress.</div>
          </div>
        </div>
        {claims ? (
          <ClaimTable claims={list} cols={["month", "items", "status", "updated", "claimed", "approved"]}
            empty={
              <Empty icon={Receipt} title="No claims yet"
                action={<button className="btn btn-primary" onClick={() => open(thisPeriod())}><Plus size={15} /> Start {monthLabel(thisPeriod())}</button>}>
                Each month gets one claim. Add your expenses with bills as they happen, then submit by the {policy?.submission_due_day ?? 5}th of the next month.
              </Empty>
            } />
        ) : (
          <SkeletonRows />
        )}
      </section>
    </>
  );
}
