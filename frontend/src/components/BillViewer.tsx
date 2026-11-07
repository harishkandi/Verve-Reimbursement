import { ChevronLeft, ChevronRight, Download, X } from "lucide-react";
import { useEffect, useState } from "react";
import { fetchBlob } from "../api";
import { day, fileSize, money } from "../format";
import type { Attachment, Line } from "../types";

export interface BillRef {
  attachment: Attachment;
  line: Line;
}

/** Side panel showing a bill next to its expense, with ←/→ to step through every bill on the claim. */
export function BillViewer({
  claimId,
  bills,
  index,
  onIndex,
  onClose,
}: {
  claimId: number;
  bills: BillRef[];
  index: number;
  onIndex: (i: number) => void;
  onClose: () => void;
}) {
  const bill = bills[index];
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let revoke: string | null = null;
    setUrl(null);
    setError(null);
    fetchBlob(`/api/claims/${claimId}/attachments/${bill.attachment.id}`)
      .then((blob) => {
        revoke = URL.createObjectURL(blob);
        setUrl(revoke);
      })
      .catch((e) => setError((e as Error).message));
    return () => {
      // Released a moment later: the frame may still be reading it while the next bill loads.
      const old = revoke;
      if (old) setTimeout(() => URL.revokeObjectURL(old), 2000);
    };
  }, [claimId, bill.attachment.id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight" && index < bills.length - 1) onIndex(index + 1);
      if (e.key === "ArrowLeft" && index > 0) onIndex(index - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, bills.length, onIndex, onClose]);

  const { attachment: a, line: l } = bill;
  const isPdf = a.content_type === "application/pdf";

  return (
    <>
      <div className="viewer-scrim" onClick={onClose} />
      <aside className="viewer" role="dialog" aria-modal="true" aria-label={`Bill: ${a.original_name}`}>
        <div className="viewer-head">
          <div className="title">
            <div className="n ellipsis">{a.original_name}</div>
            <div className="tiny faint">{fileSize(a.size_bytes)} · bill {index + 1} of {bills.length}</div>
          </div>
          <button className="btn btn-ghost btn-icon" aria-label="Previous bill" disabled={index === 0} onClick={() => onIndex(index - 1)}><ChevronLeft size={18} /></button>
          <button className="btn btn-ghost btn-icon" aria-label="Next bill" disabled={index === bills.length - 1} onClick={() => onIndex(index + 1)}><ChevronRight size={18} /></button>
          {url && (
            <a className="btn btn-ghost btn-icon" aria-label="Download" href={url} download={a.original_name}><Download size={17} /></a>
          )}
          <button className="btn btn-ghost btn-icon" aria-label="Close" onClick={onClose}><X size={18} /></button>
        </div>
        <div className="viewer-body">
          {error ? (
            <div className="notice error" style={{ margin: 20 }}>{error}</div>
          ) : !url ? (
            <div className="skeleton" style={{ width: "70%", height: "80%", borderRadius: 8 }} />
          ) : isPdf ? (
            // Hide the browser PDF chrome (toolbar, thumbnails) and fit the page to the panel width.
            <iframe src={`${url}#toolbar=0&navpanes=0&view=FitH`} title={a.original_name} />
          ) : (
            <img src={url} alt={`Bill for ${l.description}`} />
          )}
        </div>
        <div className="viewer-foot">
          <div style={{ minWidth: 0 }}>
            <div className="small muted">{day(l.expense_date)} · {l.category_name} · {l.payment_mode === "cash" ? "Cash" : "Online"}</div>
            <div className="strong ellipsis">{l.description}</div>
          </div>
          <div className="right">
            <div className="tiny faint">Claimed</div>
            <div className="amt">{money(l.amount)}</div>
          </div>
        </div>
        <div className="tiny faint" style={{ padding: "0 20px 12px" }}>
          <span className="kbd">←</span> <span className="kbd">→</span> previous / next bill · <span className="kbd">Esc</span> close
        </div>
      </aside>
    </>
  );
}
