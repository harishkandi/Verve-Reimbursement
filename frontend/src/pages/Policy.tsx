import { ArrowRight, Banknote, CalendarClock, FileCheck2, History, Landmark, ShieldCheck, UserCheck } from "lucide-react";
import { get } from "../api";
import { useMe } from "../auth";
import { ErrorNote, PageHead, SkeletonRows } from "../components/ui";
import { money } from "../format";
import type { Category, Policy } from "../types";
import { useLoad } from "../useLoad";

const limit = (v: string | null) => (v ? money(v).replace(".00", "") : <span className="faint">No limit</span>);

/** Read-only rules for everyone, so employees know limits before they claim. */
export default function PolicyPage() {
  const me = useMe();
  const { data: policy, error } = useLoad(() => get<Policy>("/api/policy"));
  const { data: categories } = useLoad(() => get<Category[]>("/api/categories"));
  const due = policy?.submission_due_day ?? 5;

  return (
    <>
      <PageHead title="Reimbursement policy" sub="What you can claim, the limits, and how a claim gets paid." />
      <ErrorNote error={error} />

      <section className="card" style={{ marginBottom: 20 }}>
        <div className="card-head"><h2>How a claim moves</h2></div>
        <div className="flow">
          <span className="node"><FileCheck2 size={15} /> You submit</span><ArrowRight size={16} className="arrow" />
          <span className="node"><UserCheck size={15} /> {me.manager?.name ?? "Your manager"} approves</span><ArrowRight size={16} className="arrow" />
          <span className="node"><ShieldCheck size={15} /> Accounts verifies bills</span><ArrowRight size={16} className="arrow" />
          <span className="node"><Landmark size={15} /> Monthly bank transfer</span>
        </div>
      </section>

      <div className="rules" style={{ marginBottom: 20 }}>
        <div className="card rule">
          <div className="ic"><CalendarClock size={17} /></div>
          <h3>One claim per month, due by the {due}th</h3>
          <p>Add expenses as they happen and submit by the {due}th of the next month. Late claims are flagged to your manager.</p>
        </div>
        <div className="card rule">
          <div className="ic"><FileCheck2 size={17} /></div>
          <h3>A bill for every expense</h3>
          <p>Online payments always need a bill (PDF or a clear photo). Each bill can only be claimed once.</p>
        </div>
        <div className="card rule">
          <div className="ic"><Banknote size={17} /></div>
          <h3>Cash without a bill</h3>
          <p>
            Allowed with a self-declaration
            {policy?.cash_no_bill_item_limit ? <> up to <b>{money(policy.cash_no_bill_item_limit).replace(".00", "")}</b> per expense</> : ""}
            {policy?.cash_no_bill_month_limit ? <> and <b>{money(policy.cash_no_bill_month_limit).replace(".00", "")}</b> per month</> : ""}.
          </p>
        </div>
        <div className="card rule">
          <div className="ic"><History size={17} /></div>
          <h3>Older than {policy?.max_age_days ?? 60} days</h3>
          <p>Expenses older than this need Finance approval. Claim them as soon as you can.</p>
        </div>
      </div>

      <section className="card">
        <div className="card-head">
          <div>
            <h2>Categories and limits</h2>
            <div className="hint">Going over a limit shows a warning to your reviewers; it doesn't block the claim.</div>
          </div>
        </div>
        {!categories ? <SkeletonRows rows={4} /> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Category</th><th className="money">Per expense</th><th className="money">Per month</th></tr></thead>
              <tbody>
                {categories.map((c) => (
                  <tr key={c.id}>
                    <td className="strong">{c.name}</td>
                    <td className="money">{limit(c.per_item_limit)}</td>
                    <td className="money">{limit(c.monthly_limit)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
