import {
  AlertTriangle,
  Check,
  CornerUpLeft,
  FileImage,
  FileText,
  Paperclip,
  Pencil,
  Plus,
  Receipt,
  Send,
  ShieldCheck,
  Trash2,
  Undo2,
  X,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { useParams } from "react-router-dom";
import { del, get, post, put, upload } from "../api";
import { useMe } from "../auth";
import { BillViewer, type BillRef } from "../components/BillViewer";
import { ClaimHero, Timeline } from "../components/ClaimParts";
import { useDialog } from "../components/Dialog";
import { LineForm } from "../components/LineForm";
import { useToast } from "../components/Toast";
import { Empty, ErrorNote, Notice, PageHead, SkeletonRows } from "../components/ui";
import { dateTime, fileSize, money, monthLabel } from "../format";
import type { Category, ClaimDetail, Line, LineDecision, LineInput } from "../types";
import { useLoad } from "../useLoad";

interface Review {
  decision: "approve" | "reject";
  amount: string;
  reason: string;
}

export default function ClaimPage() {
  const { id } = useParams();
  const me = useMe();
  const ask = useDialog();
  const toast = useToast();
  const claimId = Number(id);
  const { data: claim, setData: setClaim, error: loadError } = useLoad(() => get<ClaimDetail>(`/api/claims/${claimId}`), [claimId]);
  const { data: categories } = useLoad(() => get<Category[]>("/api/categories"));
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [review, setReview] = useState<Record<number, Review>>({});
  const [reviewComment, setReviewComment] = useState("");
  const [comment, setComment] = useState("");
  const [viewing, setViewing] = useState<number | null>(null);

  const can = (a: string) => claim?.allowed_actions.includes(a as never) ?? false;
  const editable = can("edit");
  const reviewMode = can("approve") ? "approve" : can("verify") ? "verify" : null;

  // Each review starts from the claim's current numbers.
  useEffect(() => {
    if (!claim || !reviewMode) return;
    const init: Record<number, Review> = {};
    for (const l of claim.lines) {
      init[l.id] = {
        decision: reviewMode === "verify" && l.status === "rejected" ? "reject" : "approve",
        amount: reviewMode === "approve" ? l.amount : (l.approved_amount ?? l.amount),
        reason: l.adjust_reason ?? "",
      };
    }
    setReview(init);
  }, [claim, reviewMode]);

  /** Runs an action; the result replaces the claim and the outcome is reported as a toast. */
  async function run(fn: () => Promise<ClaimDetail | void>, done?: string): Promise<boolean> {
    setBusy(true);
    try {
      const updated = await fn();
      if (updated) setClaim(updated);
      if (done) toast.success(done);
      return true;
    } catch (e) {
      toast.error((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  const refresh = () => get<ClaimDetail>(`/api/claims/${claimId}`);

  async function attach(lineId: number, file: File) {
    const res = await upload<{ duplicate_of_claim_ids: number[] }>(`/api/claims/${claimId}/lines/${lineId}/attachments`, file);
    if (res.duplicate_of_claim_ids.length) {
      toast.info(`"${file.name}" was already uploaded on claim ${res.duplicate_of_claim_ids.map((c) => `#${c}`).join(", ")}. Remove it if it's the same bill.`);
    }
  }

  const saveLine = (input: LineInput, file: File | null) =>
    run(async () => {
      if (editing === "new") {
        const before = new Set(claim?.lines.map((l) => l.id));
        const res = await post<ClaimDetail>(`/api/claims/${claimId}/lines`, input);
        const added = res.lines.find((l) => !before.has(l.id));
        setEditing(null);
        if (file && added) {
          await attach(added.id, file);
          return refresh();
        }
        return res;
      }
      const res = await put<ClaimDetail>(`/api/claims/${claimId}/lines/${editing}`, input);
      setEditing(null);
      return res;
    }, editing === "new" ? "Expense added." : "Expense updated.");

  const decisions = useMemo((): LineDecision[] => {
    if (!claim || !reviewMode) return [];
    const out: LineDecision[] = [];
    for (const l of claim.lines) {
      const r = review[l.id];
      if (!r) continue;
      if (r.decision === "reject") {
        if (l.status !== "rejected") out.push({ line_id: l.id, decision: "reject", reason: r.reason || null });
        continue;
      }
      const current = reviewMode === "approve" ? l.amount : (l.approved_amount ?? l.amount);
      if (Number(r.amount) !== Number(current)) {
        out.push({ line_id: l.id, decision: "approve", approved_amount: Number(r.amount).toFixed(2), reason: r.reason || null });
      }
    }
    return out;
  }, [claim, review, reviewMode]);

  const reviewTotal = useMemo(
    () => (claim?.lines ?? []).reduce((s, l) => (review[l.id]?.decision === "approve" ? s + Number(review[l.id].amount || 0) : s), 0),
    [claim, review],
  );

  // Every bill on the claim, in display order, for the viewer's next/previous.
  const bills = useMemo<BillRef[]>(
    () => (claim?.lines ?? []).flatMap((line) => line.attachments.map((attachment) => ({ attachment, line }))),
    [claim],
  );

  if (loadError) return <ErrorNote error={loadError} />;
  if (!claim || !categories) return <div className="card"><SkeletonRows rows={5} /></div>;

  const owner = claim.employee.id === me.id;
  const stop = [...claim.events].reverse().find((e) => e.action === "returned" || e.action === "rejected");
  const reviewed = !["draft", "submitted", "returned"].includes(claim.status);
  const adjustments = Number(claim.total_claimed) - Number(claim.total_approved);
  const approverName = claim.approver?.name ?? (owner ? me.manager?.name ?? null : null);
  const missingBills = claim.lines.filter((l) => l.attachments.length === 0 && !l.no_bill_declaration);
  const crumbs = owner
    ? [{ label: "My claims", to: "/" }]
    : reviewMode === "verify" || (me.can_verify && !me.is_approver)
      ? [{ label: "Verification", to: "/verification" }]
      : me.is_approver
        ? [{ label: "Approvals", to: "/approvals" }]
        : [{ label: "Claims" }];
  const openBill = (attachmentId: number) => setViewing(bills.findIndex((b) => b.attachment.id === attachmentId));

  async function returnOrReject(kind: "return" | "reject") {
    const res = await ask({
      title: kind === "return" ? "Return for changes?" : "Reject this claim?",
      text: kind === "return"
        ? `${claim!.employee.name} can fix the claim and resubmit it.`
        : "This is final. The employee would need a new claim for any of these expenses.",
      confirm: kind === "return" ? "Return claim" : "Reject claim",
      danger: kind === "reject",
      input: { label: "Reason (the employee will see this)", required: true },
    });
    if (res.ok) {
      await run(() => post<ClaimDetail>(`/api/claims/${claimId}/${kind}`, { comment: res.value }),
        kind === "return" ? `Returned to ${claim!.employee.name}.` : "Claim rejected.");
    }
  }

  async function submitClaim() {
    if (missingBills.length) {
      toast.error(`${missingBills.length} ${missingBills.length === 1 ? "expense needs" : "expenses need"} a bill, or a no-bill declaration for cash.`);
      return;
    }
    await run(() => post<ClaimDetail>(`/api/claims/${claimId}/submit`), `Submitted to ${approverName ?? "your approver"}.`);
  }

  return (
    <>
      <PageHead crumbsOnly crumbs={[...crumbs, { label: monthLabel(claim.period) }]}
        title={owner ? `${monthLabel(claim.period)} claim` : `${claim.employee.name}, ${monthLabel(claim.period)}`} />

      <ClaimHero
        claim={claim}
        owner={owner}
        approverName={approverName}
        actions={can("withdraw") ? (
          <button className="btn btn-sm" disabled={busy}
            onClick={async () => {
              const res = await ask({ title: "Withdraw this claim?", text: "It goes back to draft so you can make changes, then submit again.", confirm: "Withdraw" });
              if (res.ok) void run(() => post<ClaimDetail>(`/api/claims/${claimId}/withdraw`), "Withdrawn. You can edit and resubmit.");
            }}>
            <Undo2 size={14} /> Withdraw to edit
          </button>
        ) : undefined}
      />

      {stop && (claim.status === "returned" || claim.status === "rejected") && (
        <Notice tone={claim.status === "rejected" ? "error" : "warn"} title={`${claim.status === "rejected" ? "Rejected" : "Returned"} by ${stop.actor.name}`}>
          {stop.comment}
          {claim.status === "returned" && owner && <div className="small" style={{ marginTop: 4 }}>Make the changes below, then resubmit.</div>}
        </Notice>
      )}
      {claim.warnings.length > 0 && (
        <Notice tone="warn" title={`${claim.warnings.length} policy ${claim.warnings.length === 1 ? "warning" : "warnings"}`}>
          <ul>{claim.warnings.map((w, i) => <li key={i}>{w.message}</li>)}</ul>
          <div className="small" style={{ marginTop: 6, opacity: 0.85 }}>Warnings don't block the claim; reviewers decide.</div>
        </Notice>
      )}

      <div className="split">
        <div className="stack" style={{ gap: 20, minWidth: 0 }}>
          <section className="card">
            <div className="card-head">
              <div>
                <h2>Expenses</h2>
                <div className="hint">
                  {reviewMode ? "Open a bill to check it against the amount. Adjust or reject items as needed."
                    : editable ? "Drag a bill onto an expense to attach it." : `${claim.lines.length} items · ${money(claim.total_claimed)}`}
                </div>
              </div>
              {editable && editing === null && (
                <button className="btn btn-primary btn-sm" onClick={() => setEditing("new")}><Plus size={15} /> Add expense</button>
              )}
            </div>
            {editing === "new" && (
              <div className="card-body" style={{ borderBottom: "1px solid var(--line)", background: "var(--surface-alt)" }}>
                <LineForm categories={categories} busy={busy} onSave={saveLine} onCancel={() => setEditing(null)} />
              </div>
            )}
            {claim.lines.length === 0 && editing !== "new" ? (
              <Empty icon={Receipt} title="No expenses yet"
                action={editable && <button className="btn btn-primary" onClick={() => setEditing("new")}><Plus size={15} /> Add your first expense</button>}>
                Add each bill as its own expense: date, category, amount and the bill itself.
              </Empty>
            ) : (
              claim.lines.map((l) =>
                editing === l.id ? (
                  <div key={l.id} className="card-body" style={{ borderBottom: "1px solid var(--line)", background: "var(--surface-alt)" }}>
                    <LineForm categories={categories} initial={l} busy={busy} onSave={saveLine} onCancel={() => setEditing(null)} />
                  </div>
                ) : (
                  <ExpenseRow key={l.id} line={l} editable={editable && editing === null} reviewMode={reviewMode}
                    showApproved={reviewed} review={review[l.id]} busy={busy}
                    onReview={(patch) => setReview((p) => ({ ...p, [l.id]: { ...p[l.id], ...patch } }))}
                    onEdit={() => setEditing(l.id)}
                    onDelete={async () => {
                      const res = await ask({ title: "Delete this expense?", text: "Its bills are deleted too.", confirm: "Delete", danger: true });
                      if (res.ok) void run(() => del<ClaimDetail>(`/api/claims/${claimId}/lines/${l.id}`), "Expense deleted.");
                    }}
                    onAttach={(file) => run(async () => { await attach(l.id, file); return refresh(); }, `Attached ${file.name}.`)}
                    onRemoveFile={(attId) => run(() => del<ClaimDetail>(`/api/claims/${claimId}/attachments/${attId}`), "Bill removed.")}
                    onOpenFile={openBill}
                  />
                ),
              )
            )}
          </section>

          {reviewMode && (
            <section className="card">
              <div className="card-head">
                <div>
                  <h2>{reviewMode === "approve" ? "Your decision" : "Accounts verification"}</h2>
                  <div className="hint">
                    {reviewMode === "approve"
                      ? "Confirm these are genuine business expenses. Accounts checks the bills in detail next."
                      : "Check each amount against its bill. Any change needs a reason, which the employee sees."}
                  </div>
                </div>
              </div>
              <div className="card-body">
                <label className="field">
                  <span>Note for {claim.employee.name.split(" ")[0]} (optional)</span>
                  <textarea className="input" style={{ minHeight: 64 }} placeholder="Shown with your decision" value={reviewComment} onChange={(e) => setReviewComment(e.target.value)} />
                </label>
              </div>
            </section>
          )}
        </div>

        <aside className="stack" style={{ gap: 20, minWidth: 0 }}>
          <section className="card">
            <div className="card-head"><h2>Summary</h2></div>
            <div className="card-body" style={{ paddingTop: 10, paddingBottom: 10 }}>
              <div className="total-line"><span className="muted">Expenses</span><span className="v">{claim.lines.length}</span></div>
              <div className="total-line"><span className="muted">Claimed</span><span className="v">{money(claim.total_claimed)}</span></div>
              {reviewed && adjustments > 0 && (
                <div className="total-line"><span className="muted">Adjusted or rejected</span><span className="v" style={{ color: "var(--warning)" }}>− {money(adjustments)}</span></div>
              )}
              {reviewed && claim.status !== "rejected" && (
                <div className="total-line" style={{ borderTop: "1px solid var(--line)", marginTop: 6, paddingTop: 10 }}>
                  <span className="strong">{claim.status === "paid" ? "Paid" : "Approved"}</span>
                  <span className="v strong">{money(claim.total_approved)}</span>
                </div>
              )}
            </div>
            <div className="card-foot">
              <dl className="dl">
                <dt>Approver</dt><dd>{approverName ?? "—"}</dd>
                <dt>Submitted</dt><dd>{claim.submitted_at ? dateTime(claim.submitted_at) : "Not yet"}</dd>
                <dt>Bills</dt><dd>{bills.length} attached{missingBills.length ? <span style={{ color: "var(--warning)" }}> · {missingBills.length} missing</span> : ""}</dd>
                {claim.payout_batch_id && <><dt>Payout batch</dt><dd>#{claim.payout_batch_id}</dd></>}
              </dl>
            </div>
          </section>

          <section className="card">
            <div className="card-head"><h2>Activity</h2><span className="faint small">{claim.events.length} {claim.events.length === 1 ? "event" : "events"}</span></div>
            <div className="card-body" style={{ paddingBottom: 4 }}>
              <Timeline claim={claim} />
            </div>
            {can("comment") && (
              <form className="card-foot"
                onSubmit={(e) => {
                  e.preventDefault();
                  void run(() => post<ClaimDetail>(`/api/claims/${claimId}/comments`, { comment }), "Comment posted.").then((ok) => ok && setComment(""));
                }}>
                <div className="row tight" style={{ flexWrap: "nowrap" }}>
                  <input className="input" aria-label="Add a comment" placeholder="Ask or answer a question…" value={comment} onChange={(e) => setComment(e.target.value)} />
                  <button className="btn" disabled={busy || !comment.trim()}>Post</button>
                </div>
              </form>
            )}
          </section>
        </aside>
      </div>

      {can("submit") && claim.lines.length > 0 && editing === null && (
        <div className="dock" role="region" aria-label="Submit claim">
          <div className="info">
            <span className="amt">{money(claim.total_claimed)}</span> · {claim.lines.length} {claim.lines.length === 1 ? "expense" : "expenses"}
            <div>
              {missingBills.length
                ? <span style={{ color: "var(--warning)" }}>{missingBills.length} {missingBills.length === 1 ? "expense is" : "expenses are"} missing a bill</span>
                : <>Goes to <b>{approverName ?? "your approver"}</b> for approval</>}
            </div>
          </div>
          <div className="row tight actions">
            <button className="btn btn-primary" disabled={busy} onClick={submitClaim}>
              <Send size={15} /> {claim.status === "returned" ? "Resubmit claim" : "Submit claim"}
            </button>
          </div>
        </div>
      )}

      {reviewMode && (
        <div className="dock" role="region" aria-label="Review actions">
          <div className="info">
            <span className="amt">{money(reviewTotal)}</span> of {money(claim.total_claimed)}
            <div>{decisions.length ? `${decisions.length} ${decisions.length === 1 ? "change" : "changes"} to items` : "All items as claimed"}</div>
          </div>
          <div className="row tight actions">
            <button className="btn btn-danger" disabled={busy} onClick={() => returnOrReject("reject")}><XCircle size={15} /> Reject</button>
            <button className="btn" disabled={busy} onClick={() => returnOrReject("return")}><CornerUpLeft size={15} /> Return</button>
            <button className="btn btn-primary" disabled={busy}
              onClick={() =>
                run(() => post<ClaimDetail>(`/api/claims/${claimId}/${reviewMode}`, { lines: decisions, comment: reviewComment || null }),
                  reviewMode === "approve" ? "Approved and sent to Accounts." : "Verified. Ready for the next payout.",
                ).then((ok) => ok && setReviewComment(""))
              }>
              {reviewMode === "approve" ? <Check size={15} /> : <ShieldCheck size={15} />}
              {reviewMode === "approve" ? "Approve" : "Verify"} {money(reviewTotal)}
            </button>
          </div>
        </div>
      )}

      {viewing !== null && viewing >= 0 && bills[viewing] && (
        <BillViewer claimId={claimId} bills={bills} index={viewing} onIndex={setViewing} onClose={() => setViewing(null)} />
      )}
    </>
  );
}

function ExpenseRow({
  line: l,
  editable,
  reviewMode,
  showApproved,
  review,
  busy,
  onReview,
  onEdit,
  onDelete,
  onAttach,
  onRemoveFile,
  onOpenFile,
}: {
  line: Line;
  editable: boolean;
  reviewMode: "approve" | "verify" | null;
  showApproved: boolean;
  review: Review | undefined;
  busy: boolean;
  onReview: (patch: Partial<Review>) => void;
  onEdit: () => void;
  onDelete: () => void;
  onAttach: (file: File) => void;
  onRemoveFile: (attachmentId: number) => void;
  onOpenFile: (attachmentId: number) => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const d = new Date(`${l.expense_date}T00:00:00`);
  const lockedByManager = reviewMode === "verify" && l.status === "rejected";
  const changed = review && (review.decision === "reject" || Number(review.amount) !== Number(l.amount));
  const drop = editable
    ? {
        onDragOver: (e: DragEvent) => { e.preventDefault(); setOver(true); },
        onDragLeave: () => setOver(false),
        onDrop: (e: DragEvent) => {
          e.preventDefault();
          setOver(false);
          const f = e.dataTransfer.files?.[0];
          if (f) onAttach(f);
        },
      }
    : {};

  return (
    <div className={`expense droppable ${over ? "over" : ""} ${l.status === "rejected" && !reviewMode ? "rejected" : ""} ${reviewMode && review?.decision === "reject" ? "declined" : ""}`} {...drop}>
      <div className="datetile" aria-label={d.toDateString()}>
        <div className="m">{d.toLocaleDateString("en-IN", { month: "short" })}</div>
        <div className="d">{d.getDate()}</div>
      </div>

      <div style={{ minWidth: 0 }}>
        <div className="cat">
          {l.category_name}
          <span className="faint">·</span>
          {l.payment_mode === "cash" ? "Cash" : "Online"}
          {l.gstin && <span className="badge gray plain" style={{ height: 20, fontSize: 11 }}>GST {money(l.tax_amount)}</span>}
        </div>
        <div className="desc">{l.description}</div>
        {l.adjust_reason && !reviewMode && (
          <div className="reason"><AlertTriangle size={13} style={{ marginTop: 2 }} />{l.status === "rejected" ? "Rejected" : "Adjusted"}: {l.adjust_reason}</div>
        )}
        <div className="files">
          {l.attachments.map((a) => (
            <span key={a.id} className="file">
              <button className="open" onClick={() => onOpenFile(a.id)} aria-label={`View ${a.original_name}`}>
                {a.content_type === "application/pdf" ? <FileText size={14} color="var(--danger)" /> : <FileImage size={14} color="var(--brand-500)" />}
                <span className="ellipsis fname">{a.original_name}</span>
                <span className="fsize">{fileSize(a.size_bytes)}</span>
              </button>
              {editable ? (
                <button className="x" aria-label={`Remove ${a.original_name}`} onClick={() => onRemoveFile(a.id)}><X size={13} /></button>
              ) : <span style={{ width: 4 }} />}
            </span>
          ))}
          {l.attachments.length === 0 && (
            <span className="file none" style={!l.no_bill_declaration && editable ? { color: "var(--warning)", borderColor: "#f4dcae" } : undefined}>
              {l.no_bill_declaration ? "No bill · self-declared" : "Bill needed"}
            </span>
          )}
          {editable && (
            <>
              <button className="btn btn-ghost btn-sm" style={{ height: 28 }} disabled={busy} onClick={() => fileInput.current?.click()}>
                <Paperclip size={13} /> Attach
              </button>
              <input ref={fileInput} type="file" hidden accept="application/pdf,image/jpeg,image/png"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  e.target.value = "";
                  if (f) onAttach(f);
                }} />
            </>
          )}
        </div>
      </div>

      <div className="amounts">
        <div className="claimed">{money(l.amount)}</div>
        {showApproved && !reviewMode && (
          <div className="approved">
            {l.status === "rejected" ? (
              <span style={{ color: "var(--danger)" }}>Rejected</span>
            ) : Number(l.approved_amount) === Number(l.amount) ? (
              <span className="row tight" style={{ gap: 4, justifyContent: "flex-end", color: "var(--success)" }}><Check size={13} strokeWidth={2.5} /> Approved</span>
            ) : (
              <span style={{ color: "var(--warning)" }}>Approved {money(l.approved_amount)}</span>
            )}
          </div>
        )}
        {editable && (
          <div className="tools">
            <button className="btn btn-ghost btn-icon btn-sm" aria-label="Edit expense" onClick={onEdit}><Pencil size={15} /></button>
            <button className="btn btn-ghost btn-icon btn-sm" aria-label="Delete expense" onClick={onDelete}><Trash2 size={15} /></button>
          </div>
        )}
      </div>

      {reviewMode && review && (
        <div className="review">
          {lockedByManager ? (
            <span className="badge bad">Rejected by manager{l.adjust_reason ? `: ${l.adjust_reason}` : ""}</span>
          ) : (
            <>
              <div className="seg" role="radiogroup" aria-label="Decision">
                <button type="button" role="radio" aria-checked={review.decision === "approve"} className={review.decision === "approve" ? "on" : ""} onClick={() => onReview({ decision: "approve" })}>
                  <Check size={14} /> Approve
                </button>
                <button type="button" role="radio" aria-checked={review.decision === "reject"} className={review.decision === "reject" ? "on" : ""} onClick={() => onReview({ decision: "reject" })}>
                  <X size={14} /> Reject
                </button>
              </div>
              {review.decision === "approve" && (
                <div className="affix" style={{ width: 140 }}>
                  <span className="pre" aria-hidden="true">₹</span>
                  <input className="input" aria-label="Approved amount" type="number" min="0" step="0.01" max={l.amount}
                    style={{ height: 34 }} value={review.amount} onChange={(e) => onReview({ amount: e.target.value })} />
                </div>
              )}
              {changed && (
                <input className="input grow" style={{ height: 34, minWidth: 180 }} aria-label="Reason"
                  placeholder={review.decision === "reject" ? "Why is it rejected? (required)" : "Why the change? (required)"}
                  value={review.reason} onChange={(e) => onReview({ reason: e.target.value })} />
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
