import { ClipboardCheck, Inbox, Users } from "lucide-react";
import { useState } from "react";
import { get } from "../api";
import { ClaimTable, Empty, ErrorNote, PageHead, SkeletonRows } from "../components/ui";
import { money } from "../format";
import type { ClaimSummary } from "../types";
import { useLoad } from "../useLoad";

export default function InboxPage({ kind }: { kind: "approvals" | "verification" }) {
  const [tab, setTab] = useState<"waiting" | "history">("waiting");
  const showHistory = kind === "approvals" && tab === "history";
  const url = kind === "verification" ? "/api/inbox/verification" : showHistory ? "/api/inbox/team" : "/api/inbox/approvals";
  const { data, error } = useLoad(() => get<ClaimSummary[]>(url), [url]);
  const total = (data ?? []).reduce((s, c) => s + Number(kind === "verification" ? c.total_approved : c.total_claimed), 0);

  return (
    <>
      <PageHead
        title={kind === "approvals" ? "Approvals" : "Verification"}
        sub={kind === "approvals" ? "Claims from your team that need your decision." : "Manager-approved claims to check against their bills before payout."}
      />
      {kind === "approvals" && (
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === "waiting"} className={tab === "waiting" ? "on" : ""} onClick={() => setTab("waiting")}>
            <Inbox size={15} /> Waiting for you
          </button>
          <button role="tab" aria-selected={tab === "history"} className={tab === "history" ? "on" : ""} onClick={() => setTab("history")}>
            <Users size={15} /> Team history
          </button>
        </div>
      )}
      <ErrorNote error={error} />
      <section className="card">
        {data && data.length > 0 && !showHistory && (
          <div className="card-head">
            <div>
              <h2>{data.length} {data.length === 1 ? "claim" : "claims"} waiting</h2>
              <div className="hint">{money(total)} in total · oldest first</div>
            </div>
          </div>
        )}
        {data ? (
          <ClaimTable
            claims={data}
            cols={showHistory ? ["employee", "month", "status", "updated", "claimed", "approved"]
              : kind === "verification" ? ["employee", "month", "items", "warnings", "updated", "approved"]
              : ["employee", "month", "items", "warnings", "updated", "claimed"]}
            empty={
              <Empty icon={kind === "verification" ? ClipboardCheck : Inbox} title={showHistory ? "No team claims yet" : "You're all caught up"}>
                {showHistory ? "Claims your team submits will appear here." : "New claims will appear here as soon as they're submitted."}
              </Empty>
            }
          />
        ) : (
          <SkeletonRows />
        )}
      </section>
    </>
  );
}
