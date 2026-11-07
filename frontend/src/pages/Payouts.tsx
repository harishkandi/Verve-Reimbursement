import { CheckCircle2, Landmark, Wallet } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { get, post } from "../api";
import { ClaimTable, Empty, ErrorNote, PageHead, SkeletonRows, Stat } from "../components/ui";
import { day, money, today } from "../format";
import type { BatchDetail, BatchSummary, ClaimSummary } from "../types";
import { useLoad } from "../useLoad";

export default function PayoutsPage() {
  const navigate = useNavigate();
  const ready = useLoad(() => get<ClaimSummary[]>("/api/payouts/ready"));
  const batches = useLoad(() => get<BatchSummary[]>("/api/payouts"));
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [payoutDate, setPayoutDate] = useState(today());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const readyList = ready.data ?? [];
  const toggle = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const toggleAll = () => setSelected((prev) => (prev.size === readyList.length ? new Set() : new Set(readyList.map((c) => c.id))));
  const selectedTotal = readyList.filter((c) => selected.has(c.id)).reduce((s, c) => s + Number(c.total_approved), 0);
  const readyTotal = readyList.reduce((s, c) => s + Number(c.total_approved), 0);
  const open = (batches.data ?? []).filter((b) => b.status === "open");
  const lastPaid = (batches.data ?? [])
    .filter((b) => b.status === "paid")
    .sort((a, b) => (b.paid_on ?? "").localeCompare(a.paid_on ?? ""))[0];

  async function createBatch() {
    setBusy(true);
    setError(null);
    try {
      const batch = await post<BatchDetail>("/api/payouts", { payout_date: payoutDate, claim_ids: [...selected] });
      navigate(`/payouts/${batch.id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHead title="Payouts" sub="Group verified claims into a batch, export it for the bank, then record the payment." />
      <ErrorNote error={error || ready.error || batches.error} />

      <div className="stats">
        <Stat icon={Wallet} label="Ready to pay" value={money(readyTotal)} foot={`${readyList.length} verified ${readyList.length === 1 ? "claim" : "claims"}`} />
        <Stat icon={Landmark} label="Open batches" value={open.length} foot={open.length ? `${money(open.reduce((s, b) => s + Number(b.total), 0))} awaiting transfer` : "None"} />
        <Stat icon={CheckCircle2} label="Last payout" value={lastPaid ? money(lastPaid.total) : "—"}
          foot={lastPaid ? `${day(lastPaid.paid_on)} · ${lastPaid.claim_count} ${lastPaid.claim_count === 1 ? "claim" : "claims"}` : "No payouts yet"} />
      </div>

      <section className="card" style={{ marginBottom: 20 }}>
        <div className="card-head">
          <div>
            <h2>Ready to pay</h2>
            <div className="hint">Verified by Accounts and not yet in a batch.</div>
          </div>
        </div>
        {selected.size > 0 && (
          <div className="selbar">
            <span className="strong">{selected.size} selected</span>
            <span className="num muted">{money(selectedTotal)}</span>
            <span className="grow" />
            <label className="row tight small muted">
              Payout date
              <input className="input" type="date" value={payoutDate} onChange={(e) => setPayoutDate(e.target.value)} style={{ width: 160, height: 34 }} />
            </label>
            <button className="btn btn-primary btn-sm" style={{ height: 34 }} disabled={busy} onClick={createBatch}>Create payout batch</button>
          </div>
        )}
        {ready.data ? (
          <ClaimTable claims={readyList} cols={["employee", "month", "items", "updated", "approved"]} select={{ ids: selected, toggle, toggleAll }}
            empty={<Empty icon={Wallet} title="Nothing to pay right now">Claims appear here once Accounts has verified them.</Empty>} />
        ) : (
          <SkeletonRows />
        )}
      </section>

      <section className="card">
        <div className="card-head"><h2>Batches</h2></div>
        {batches.data && batches.data.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Batch</th><th>Payout date</th><th>Status</th><th>Reference</th><th className="money">Claims</th><th className="money">Total</th></tr>
              </thead>
              <tbody>
                {batches.data.map((b) => (
                  <tr key={b.id} className="clickable" onClick={() => navigate(`/payouts/${b.id}`)}>
                    <td className="strong">#{b.id}</td>
                    <td className="nowrap">{day(b.payout_date)}</td>
                    <td><span className={`badge ${b.status === "paid" ? "good" : ""}`}>{b.status === "paid" ? `Paid ${day(b.paid_on).slice(0, 6)}` : "Awaiting transfer"}</span></td>
                    <td className="muted num">{b.reference ?? "—"}</td>
                    <td className="money">{b.claim_count}</td>
                    <td className="money strong">{money(b.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : batches.data ? (
          <Empty icon={Landmark} title="No batches yet">Select verified claims above to create the first payout batch.</Empty>
        ) : (
          <SkeletonRows rows={2} />
        )}
      </section>
    </>
  );
}
