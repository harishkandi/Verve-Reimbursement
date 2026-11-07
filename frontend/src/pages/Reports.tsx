import { Clock3, Download, FileSearch, Hourglass, ListChecks } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { get, openFile } from "../api";
import { ClaimTable, Empty, ErrorNote, PageHead, Person, SkeletonRows, StatusBadge } from "../components/ui";
import { STATUS_LABEL, money, monthLabel, thisPeriod } from "../format";
import type { ClaimStatus, ClaimSummary, PendingRow } from "../types";
import { useLoad } from "../useLoad";

export default function ReportsPage() {
  const [tab, setTab] = useState<"pending" | "register">("pending");
  return (
    <>
      <PageHead title="Reports" sub="Where claims are waiting, and every claim by month for Accounts." />
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === "pending"} className={tab === "pending" ? "on" : ""} onClick={() => setTab("pending")}>
          <Hourglass size={15} /> Waiting claims
        </button>
        <button role="tab" aria-selected={tab === "register"} className={tab === "register" ? "on" : ""} onClick={() => setTab("register")}>
          <ListChecks size={15} /> Claims register
        </button>
      </div>
      {tab === "pending" ? <Pending /> : <Register />}
    </>
  );
}

function Pending() {
  const navigate = useNavigate();
  const { data, error } = useLoad(() => get<PendingRow[]>("/api/reports/pending"));
  if (error) return <ErrorNote error={error} />;
  const slow = (data ?? []).filter((r) => r.days_waiting > 5).length;
  return (
    <section className="card">
      {data && data.length > 0 && (
        <div className="card-head">
          <div>
            <h2>{data.length} claims in progress</h2>
            <div className="hint">{slow ? `${slow} waiting more than 5 days` : "Nothing waiting more than 5 days"} · longest wait first</div>
          </div>
        </div>
      )}
      {!data ? (
        <SkeletonRows />
      ) : data.length === 0 ? (
        <Empty icon={Clock3} title="Nothing is waiting">Every submitted claim has been paid or closed.</Empty>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Employee</th><th>Month</th><th>Stage</th><th>Waiting with</th><th className="money">Days</th><th className="money">Amount</th></tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.claim.id} className="clickable" onClick={() => navigate(`/claims/${r.claim.id}`)}>
                  <td><Person name={r.claim.employee.name} meta={r.claim.employee_department} /></td>
                  <td className="nowrap">{monthLabel(r.claim.period)}</td>
                  <td><StatusBadge status={r.stage} /></td>
                  <td className="muted">{r.waiting_with}</td>
                  <td className="money">
                    <span className={`badge plain ${r.days_waiting > 5 ? "bad" : "gray"}`}>{r.days_waiting}d</span>
                  </td>
                  <td className="money strong">{money(r.stage === "submitted" ? r.claim.total_claimed : r.claim.total_approved)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function Register() {
  const [month, setMonth] = useState(thisPeriod());
  const [status, setStatus] = useState<ClaimStatus | "">("");
  const [department, setDepartment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const query = new URLSearchParams();
  if (month) query.set("month", month);
  if (status) query.set("status", status);
  if (department.trim()) query.set("department", department.trim());
  const qs = query.toString();
  const { data, error: loadError } = useLoad(() => get<ClaimSummary[]>(`/api/reports/register?${qs}`), [qs]);
  const claimed = (data ?? []).reduce((s, c) => s + Number(c.total_claimed), 0);
  const approved = (data ?? []).reduce((s, c) => s + Number(c.total_approved), 0);

  return (
    <>
      <ErrorNote error={error || loadError} />
      <section className="card">
        <div className="card-head" style={{ alignItems: "flex-end" }}>
          <div className="row" style={{ alignItems: "flex-end" }}>
            <label className="field"><span>Month</span>
              <input className="input" type="month" value={month} onChange={(e) => setMonth(e.target.value)} style={{ width: 168 }} />
            </label>
            <label className="field"><span>Status</span>
              <select className="input" value={status} onChange={(e) => setStatus(e.target.value as ClaimStatus | "")} style={{ width: 180 }}>
                <option value="">All except drafts</option>
                {(Object.keys(STATUS_LABEL) as ClaimStatus[]).filter((s) => s !== "draft").map((s) => (
                  <option key={s} value={s}>{STATUS_LABEL[s]}</option>
                ))}
              </select>
            </label>
            <label className="field"><span>Department</span>
              <input className="input" placeholder="Any" value={department} onChange={(e) => setDepartment(e.target.value)} style={{ width: 160 }} />
            </label>
          </div>
          <button className="btn" onClick={() => openFile(`/api/reports/register/export?${qs}`, true).catch((e) => setError(e.message))}>
            <Download size={15} /> Export line items (CSV)
          </button>
        </div>
        {data && data.length > 0 && (
          <div className="selbar" style={{ background: "var(--surface-alt)", borderColor: "var(--line)" }}>
            <span className="strong">{data.length} claims</span>
            <span className="muted num">Claimed {money(claimed)}</span>
            <span className="muted num">Approved {money(approved)}</span>
          </div>
        )}
        {data ? (
          <ClaimTable claims={data} cols={["employee", "month", "status", "updated", "claimed", "approved"]}
            empty={<Empty icon={FileSearch} title="No claims match">Try another month or clear the filters.</Empty>} />
        ) : (
          <SkeletonRows />
        )}
      </section>
    </>
  );
}
