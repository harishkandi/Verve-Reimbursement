import { CheckCircle2, Download, FileSpreadsheet, Trash2 } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { get, openFile, post } from "../api";
import { useDialog } from "../components/Dialog";
import { useToast } from "../components/Toast";
import { ErrorNote, Notice, PageHead, Person, SkeletonRows } from "../components/ui";
import { day, money, monthLabel, today } from "../format";
import type { BatchDetail } from "../types";
import { useLoad } from "../useLoad";

export default function BatchPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const ask = useDialog();
  const toast = useToast();
  const batchId = Number(id);
  const { data: batch, setData, error: loadError } = useLoad(() => get<BatchDetail>(`/api/payouts/${batchId}`), [batchId]);
  const [paidOn, setPaidOn] = useState(today());
  const [reference, setReference] = useState("");
  const [refs, setRefs] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function act(fn: () => Promise<BatchDetail>, done: string) {
    setBusy(true);
    try {
      setData(await fn());
      toast.success(done);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (loadError) return <ErrorNote error={loadError} />;
  if (!batch) return <div className="card"><SkeletonRows /></div>;
  const open = batch.status === "open";
  const download = (format: "xlsx" | "csv") =>
    openFile(`/api/payouts/${batchId}/export?format=${format}`, true).catch((e) => setError(e.message));

  return (
    <>
      <PageHead
        crumbs={[{ label: "Payouts", to: "/payouts" }, { label: `Batch #${batch.id}` }]}
        title={`Payout batch #${batch.id}`}
        badge={<span className={`badge ${open ? "" : "good"}`}>{open ? "Awaiting transfer" : "Paid"}</span>}
        sub={`Payout date ${day(batch.payout_date)} · created by ${batch.created_by.name}`}
      >
        <button className="btn" onClick={() => download("csv")}><Download size={15} /> CSV</button>
        <button className="btn" onClick={() => download("xlsx")}><FileSpreadsheet size={15} /> Excel</button>
      </PageHead>
      <ErrorNote error={error} />
      {!open && (
        <Notice tone="success" title={`Paid on ${day(batch.paid_on)}`}>Reference {batch.reference}. Each employee was notified by email.</Notice>
      )}

      <div className="split">
        <section className="card">
          <div className="card-head">
            <div>
              <h2>{batch.claim_count} {batch.claim_count === 1 ? "claim" : "claims"}</h2>
              <div className="hint">{open ? "Download the file for the bank, make the transfers, then record the payment." : "Paid claims are locked."}</div>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Employee</th><th>Month</th>
                  <th>{open ? "Own UTR (optional)" : "Reference"}</th>
                  <th className="money">Amount</th>
                  {open && <th />}
                </tr>
              </thead>
              <tbody>
                {batch.claims.map((c) => (
                  <tr key={c.id} className="clickable" onClick={() => navigate(`/claims/${c.id}`)}>
                    <td><Person name={c.employee.name} meta={c.employee_department} /></td>
                    <td className="nowrap">{monthLabel(c.period)}</td>
                    <td onClick={(e) => open && e.stopPropagation()}>
                      {open ? (
                        <input className="input" style={{ height: 32, maxWidth: 200 }} aria-label={`UTR for ${c.employee.name}`}
                          placeholder="Uses batch reference" value={refs[c.id] ?? ""} onChange={(e) => setRefs({ ...refs, [c.id]: e.target.value })} />
                      ) : (
                        <span className="num muted">{c.payment_reference}</span>
                      )}
                    </td>
                    <td className="money strong">{money(c.total_approved)}</td>
                    {open && (
                      <td onClick={(e) => e.stopPropagation()}>
                        <button className="btn btn-ghost btn-icon btn-sm" aria-label={`Remove ${c.employee.name} from batch`} disabled={busy}
                          onClick={async () => {
                            const res = await ask({ title: "Remove from this batch?", text: "The claim goes back to Ready to pay.", confirm: "Remove" });
                            if (res.ok) void act(() => post<BatchDetail>(`/api/payouts/${batchId}/remove/${c.id}`), `${c.employee.name} removed from the batch.`);
                          }}>
                          <Trash2 size={15} />
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <aside className="stack" style={{ gap: 20 }}>
          <section className="card">
            <div className="card-body">
              <div className="total-line"><span className="muted">Claims</span><span className="v">{batch.claim_count}</span></div>
              <div className="total-line"><span className="muted">Payout date</span><span className="v">{day(batch.payout_date)}</span></div>
              <div className="total-line big"><span className="strong">Total</span><span className="v">{money(batch.total)}</span></div>
            </div>
          </section>

          {open && batch.claims.length > 0 && (
            <form className="card"
              onSubmit={async (e) => {
                e.preventDefault();
                const res = await ask({
                  title: `Mark ${batch.claim_count} ${batch.claim_count === 1 ? "claim" : "claims"} as paid?`,
                  text: `${money(batch.total)} with reference ${reference}. Employees are emailed and the claims are locked.`,
                  confirm: "Mark as paid",
                });
                if (!res.ok) return;
                const claim_references = Object.fromEntries(Object.entries(refs).filter(([, v]) => v.trim()));
                void act(() => post<BatchDetail>(`/api/payouts/${batchId}/mark-paid`, { paid_on: paidOn, reference, claim_references }),
                  "Batch marked as paid. Employees have been notified.");
              }}>
              <div className="card-head">
                <div>
                  <h2>Record payment</h2>
                  <div className="hint">After the bank transfers have gone through.</div>
                </div>
              </div>
              <div className="card-body stack">
                <label className="field"><span>Paid on</span>
                  <input className="input" type="date" value={paidOn} max={today()} onChange={(e) => setPaidOn(e.target.value)} />
                </label>
                <label className="field"><span>Bank reference</span>
                  <input className="input" required placeholder="UTR or bulk-transfer reference" value={reference} onChange={(e) => setReference(e.target.value)} />
                </label>
              </div>
              <div className="card-foot" style={{ display: "flex", justifyContent: "flex-end" }}>
                <button className="btn btn-primary" disabled={busy || !reference.trim()}><CheckCircle2 size={15} /> Mark as paid</button>
              </div>
            </form>
          )}
        </aside>
      </div>
    </>
  );
}
