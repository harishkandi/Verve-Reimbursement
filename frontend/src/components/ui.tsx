import { AlertCircle, AlertTriangle, CheckCircle2, ChevronRight, Info, type LucideIcon } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { STATUS_LABEL, STATUS_TONE, ago, initials, money, monthLabel } from "../format";
import type { ClaimStatus, ClaimSummary } from "../types";

export function StatusBadge({ status }: { status: ClaimStatus }) {
  return <span className={`badge ${STATUS_TONE[status]}`}>{STATUS_LABEL[status]}</span>;
}

export function Avatar({ name, size }: { name: string; size?: "sm" | "lg" }) {
  return (
    <span className={`avatar ${size ?? ""}`} aria-hidden="true">
      {initials(name)}
    </span>
  );
}

export function Person({ name, meta, size }: { name: string; meta?: ReactNode; size?: "sm" | "lg" }) {
  return (
    <div className="cell-person">
      <Avatar name={name} size={size} />
      <div className="grow">
        <div className="name ellipsis">{name}</div>
        {meta && <div className="meta ellipsis">{meta}</div>}
      </div>
    </div>
  );
}

export function PageHead({
  title,
  sub,
  crumbs,
  badge,
  children,
  crumbsOnly,
}: {
  title: string;
  sub?: ReactNode;
  crumbs?: { label: string; to?: string }[];
  badge?: ReactNode;
  children?: ReactNode;
  /** For pages that render their own header card: keeps the breadcrumb and tab title only. */
  crumbsOnly?: boolean;
}) {
  useEffect(() => {
    document.title = `${title} · Verve Reimbursements`;
  }, [title]);
  return (
    <>
      {crumbs && (
        <nav className="crumbs" aria-label="Breadcrumb" style={crumbsOnly ? { marginBottom: 14 } : undefined}>
          {crumbs.map((c, i) => (
            <span key={i} className="row tight" style={{ gap: 6 }}>
              {i > 0 && <ChevronRight size={13} />}
              {c.to ? <Link to={c.to}>{c.label}</Link> : <span>{c.label}</span>}
            </span>
          ))}
        </nav>
      )}
      {!crumbsOnly && <div className="page-head">
        <div>
          <div className="title-row">
            <h1>{title}</h1>
            {badge}
          </div>
          {sub && <div className="sub">{sub}</div>}
        </div>
        {children && <div className="row tight">{children}</div>}
      </div>}
    </>
  );
}

const NOTICE_ICON: Record<string, LucideIcon> = {
  info: Info,
  success: CheckCircle2,
  warn: AlertTriangle,
  error: AlertCircle,
};

export function Notice({
  tone,
  title,
  children,
}: {
  tone: "info" | "success" | "warn" | "error";
  title?: ReactNode;
  children?: ReactNode;
}) {
  const Icon = NOTICE_ICON[tone];
  return (
    <div className={`notice ${tone}`} role={tone === "error" ? "alert" : "status"}>
      <Icon size={17} />
      <div className="grow">
        {title && <div className="title">{title}</div>}
        {children}
      </div>
    </div>
  );
}

export function ErrorNote({ error }: { error: string | null | undefined }) {
  return error ? <Notice tone="error">{error}</Notice> : null;
}

export function Empty({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon: LucideIcon;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="icon"><Icon size={22} /></div>
      <div className="title">{title}</div>
      {children && <div className="text">{children}</div>}
      {action}
    </div>
  );
}

export function SkeletonRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="skeleton-rows" aria-label="Loading" role="status">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="row" style={{ gap: 14 }}>
          <div className="skeleton" style={{ width: 32, height: 32, borderRadius: "50%" }} />
          <div className="grow stack" style={{ gap: 8 }}>
            <div className="skeleton" style={{ width: `${45 + ((i * 17) % 30)}%` }} />
            <div className="skeleton" style={{ width: "22%", height: 10 }} />
          </div>
          <div className="skeleton" style={{ width: 72 }} />
        </div>
      ))}
    </div>
  );
}

export function Stat({
  icon: Icon,
  label,
  value,
  foot,
}: {
  icon: LucideIcon;
  label: string;
  value: ReactNode;
  foot?: ReactNode;
}) {
  return (
    <div className="card stat">
      <div className="label">
        <span className="icon"><Icon size={15} /></span>
        {label}
      </div>
      <div className="value">{value}</div>
      {foot && <div className="foot">{foot}</div>}
    </div>
  );
}

type Col = "employee" | "month" | "status" | "claimed" | "approved" | "approver" | "updated" | "items" | "warnings";

/** The standard claims table used by inboxes, reports and payouts. */
export function ClaimTable({
  claims,
  cols,
  empty,
  select,
}: {
  claims: ClaimSummary[];
  cols: Col[];
  empty: ReactNode;
  select?: { ids: Set<number>; toggle: (id: number) => void; toggleAll: () => void };
}) {
  const navigate = useNavigate();
  if (!claims.length) return <>{empty}</>;
  const has = (c: Col) => cols.includes(c);
  const allOn = select ? claims.every((c) => select.ids.has(c.id)) : false;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {select && (
              <th style={{ width: 44 }}>
                <input type="checkbox" aria-label="Select all" checked={allOn} onChange={select.toggleAll}
                  style={{ accentColor: "var(--brand-600)" }} />
              </th>
            )}
            {has("employee") && <th>Employee</th>}
            {has("month") && <th>Month</th>}
            {has("items") && <th>Items</th>}
            {has("status") && <th>Status</th>}
            {has("approver") && <th>Approver</th>}
            {has("warnings") && <th>Checks</th>}
            {has("updated") && <th>Last update</th>}
            {has("claimed") && <th className="money">Claimed</th>}
            {has("approved") && <th className="money">Approved</th>}
            <th className="chev" aria-hidden="true" />
          </tr>
        </thead>
        <tbody>
          {claims.map((c) => (
            <tr key={c.id} className="clickable" onClick={() => navigate(`/claims/${c.id}`)}>
              {select && (
                <td onClick={(e) => e.stopPropagation()}>
                  <input type="checkbox" aria-label={`Select claim ${c.id}`} checked={select.ids.has(c.id)}
                    onChange={() => select.toggle(c.id)} style={{ accentColor: "var(--brand-600)" }} />
                </td>
              )}
              {has("employee") && (
                <td><Person name={c.employee.name} meta={c.employee_department ?? c.employee.email} /></td>
              )}
              {has("month") && <td className="nowrap strong">{monthLabel(c.period)}</td>}
              {has("items") && <td className="muted">{c.line_count} {c.line_count === 1 ? "expense" : "expenses"}</td>}
              {has("status") && <td><StatusBadge status={c.status} /></td>}
              {has("approver") && <td className="muted">{c.approver?.name ?? "—"}</td>}
              {has("warnings") && (
                <td>
                  {c.warning_count ? (
                    <span className="badge warn"><AlertTriangle size={12} style={{ marginLeft: -2 }} />{c.warning_count} {c.warning_count === 1 ? "warning" : "warnings"}</span>
                  ) : (
                    <span className="badge good plain"><CheckCircle2 size={12} style={{ marginLeft: -2 }} />Within policy</span>
                  )}
                </td>
              )}
              {has("updated") && <td className="muted nowrap">{ago(c.status_changed_at)}</td>}
              {has("claimed") && <td className="money">{money(c.total_claimed)}</td>}
              {has("approved") && (
                <td className="money strong">
                  {["draft", "submitted", "returned", "rejected"].includes(c.status) ? <span className="faint">—</span> : money(c.total_approved)}
                </td>
              )}
              <td className="chev"><ChevronRight size={16} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
