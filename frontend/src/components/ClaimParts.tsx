import {
  Check,
  CornerUpLeft,
  FilePlus2,
  Landmark,
  MessageSquare,
  Send,
  ShieldCheck,
  Undo2,
  Wallet,
  X,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import { ACTION_LABEL, dateTime, day, money, monthLabel } from "../format";
import type { ClaimDetail, ClaimEvent, Line } from "../types";
import { Avatar, StatusBadge } from "./ui";

const STEPS = [
  { name: "Submitted", event: "submitted" },
  { name: "Manager", event: "manager_approved" },
  { name: "Accounts", event: "verified" },
  { name: "Payout", event: "added_to_batch" },
  { name: "Paid", event: "paid" },
] as const;

const WAITING: Record<string, string> = {
  submitted: "Awaiting approval",
  manager_approved: "Being verified",
  verified: "Next payout run",
  in_payout_batch: "Transfer scheduled",
};

const lastEvent = (events: ClaimEvent[], action: string) => [...events].reverse().find((e) => e.action === action);

/** Title, status, headline amount and progress in one header. */
export function ClaimHero({
  claim,
  owner,
  approverName,
  actions,
}: {
  claim: ClaimDetail;
  owner: boolean;
  approverName: string | null;
  actions?: ReactNode;
}) {
  const reviewed = !["draft", "submitted", "returned"].includes(claim.status);
  const amountLabel = claim.status === "paid" ? "Paid" : claim.status === "rejected" ? "Claimed" : reviewed ? "Approved" : "Total claimed";
  const amount = reviewed && claim.status !== "rejected" ? claim.total_approved : claim.total_claimed;
  return (
    <section className="card hero">
      <div className="hero-top">
        <div className="who">
          {!owner && <Avatar name={claim.employee.name} size="lg" />}
          <div style={{ minWidth: 0 }}>
            <div className="row tight">
              <h1 style={{ fontSize: 24 }}>{owner ? `${monthLabel(claim.period)} claim` : claim.employee.name}</h1>
              <StatusBadge status={claim.status} />
            </div>
            <div className="meta">
              {!owner && <span>{monthLabel(claim.period)}{claim.employee_department ? ` · ${claim.employee_department}` : ""}</span>}
              <span>Claim #{claim.id}</span>
              <span>{claim.lines.length} {claim.lines.length === 1 ? "expense" : "expenses"}</span>
              {approverName && <span>Approver: {approverName}</span>}
            </div>
            {actions && <div className="row tight" style={{ marginTop: 12 }}>{actions}</div>}
          </div>
        </div>
        <div className="hero-amount">
          <div className="label">{amountLabel}</div>
          <div className="value">{money(amount)}</div>
          {reviewed && Number(claim.total_claimed) !== Number(claim.total_approved) && claim.status !== "rejected" && (
            <div className="sub">of {money(claim.total_claimed)} claimed</div>
          )}
          {claim.payment_reference && <div className="sub num">Ref. {claim.payment_reference}</div>}
        </div>
      </div>
      {claim.status !== "draft" && <Stepper claim={claim} />}
    </section>
  );
}

function Stepper({ claim }: { claim: ClaimDetail }) {
  const stopEvent = lastEvent(claim.events, claim.status === "rejected" ? "rejected" : "returned");
  // The step the claim is waiting on, or stopped at.
  const position: Record<string, number> = {
    draft: 0, submitted: 1, manager_approved: 2, verified: 3, in_payout_batch: 3, paid: 5,
    returned: stopEvent?.from_status === "manager_approved" ? 2 : 1,
    rejected: stopEvent?.from_status === "manager_approved" ? 2 : 1,
  };
  const at = position[claim.status];
  const halted = claim.status === "returned" || claim.status === "rejected";

  return (
    <ol className="stepper" aria-label="Claim progress" style={{ listStyle: "none", margin: 0 }}>
      {STEPS.map((s, i) => {
        const done = i < at;
        const current = i === at;
        const state = done ? "done" : current ? (halted ? (claim.status === "rejected" ? "stop" : "halt") : "current") : "upcoming";
        const ev = done ? lastEvent(claim.events, s.event) : undefined;
        return (
          <li key={s.name} className={`step ${state}`} aria-current={current ? "step" : undefined}>
            <span className="dot">
              {state === "done" ? <Check size={15} strokeWidth={3} /> : state === "stop" ? <X size={15} strokeWidth={3} /> : i + 1}
            </span>
            <span className="name">{s.name}</span>
            <span className="when" style={state === "halt" ? { color: "var(--warning)" } : state === "stop" ? { color: "var(--danger)" } : undefined}>
              {state === "halt" ? "Returned" : state === "stop" ? "Rejected" : ev ? day(ev.created_at) : current ? WAITING[claim.status] ?? "" : ""}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

const MARK: Record<string, [LucideIcon, string]> = {
  created: [FilePlus2, "gray"],
  submitted: [Send, ""],
  withdrawn: [Undo2, "gray"],
  manager_approved: [Check, "good"],
  verified: [ShieldCheck, "good"],
  returned: [CornerUpLeft, "warn"],
  rejected: [X, "bad"],
  added_to_batch: [Wallet, ""],
  removed_from_batch: [Undo2, "gray"],
  paid: [Landmark, "good"],
  comment: [MessageSquare, "gray"],
};

interface Change {
  line_id: number;
  claimed: string;
  after: { status: string; approved_amount: string | null };
  reason: string | null;
}

export function Timeline({ claim }: { claim: ClaimDetail }) {
  const lineName = (id: number) => {
    const l: Line | undefined = claim.lines.find((x) => x.id === id);
    return l ? `${day(l.expense_date).slice(0, 6)} · ${l.category_name}` : "Expense";
  };
  return (
    <ol className="timeline">
      {[...claim.events].reverse().map((e) => {
        const changes = (Array.isArray(e.details?.changes) ? e.details!.changes : []) as Change[];
        const [Icon, tone] = MARK[e.action] ?? [MessageSquare, "gray"];
        return (
          <li key={e.id}>
            <span className="tl-mark">
              <Avatar name={e.actor.name} size="sm" />
              <span className={`ico ${tone}`}><Icon size={8} strokeWidth={3.5} /></span>
            </span>
            <div style={{ minWidth: 0 }}>
              <div className="what">
                <b>{e.actor.name}</b> <span className="muted">{(ACTION_LABEL[e.action] ?? e.action).toLowerCase()}</span>
                {e.action === "paid" && e.details?.reference ? <span className="muted"> · ref {String(e.details.reference)}</span> : null}
              </div>
              <div className="when">{dateTime(e.created_at)}</div>
              {e.comment && <div className="bubble">{e.comment}</div>}
              {changes.length > 0 && (
                <div className="changes">
                  {changes.map((c) => (
                    <div key={c.line_id}>
                      {lineName(c.line_id)}:{" "}
                      {c.after.status === "rejected" ? "rejected" : <span className="num">{money(c.claimed)} → {money(c.after.approved_amount)}</span>}
                      {c.reason && <span className="faint"> — {c.reason}</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
