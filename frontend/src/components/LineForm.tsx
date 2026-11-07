import { Banknote, CreditCard, Paperclip, Upload, X } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { fileSize, money, today } from "../format";
import type { Category, Line, LineInput, PaymentMode } from "../types";
import { Notice } from "./ui";

function limitText(c: Category | undefined): string {
  if (!c) return "";
  const parts = [
    c.per_item_limit && `${money(c.per_item_limit).replace(".00", "")} per expense`,
    c.monthly_limit && `${money(c.monthly_limit).replace(".00", "")} per month`,
  ].filter(Boolean);
  return parts.length ? `Limit: ${parts.join(" · ")}` : "No limit for this category";
}

export function LineForm({
  categories,
  initial,
  busy,
  onSave,
  onCancel,
}: {
  categories: Category[];
  initial?: Line;
  busy: boolean;
  /** `file` is only offered for new expenses; existing ones attach bills from the row. */
  onSave: (input: LineInput, file: File | null) => void;
  onCancel: () => void;
}) {
  const [date, setDate] = useState(initial?.expense_date ?? today());
  const [categoryId, setCategoryId] = useState<number>(initial?.category_id ?? categories[0]?.id ?? 0);
  const [description, setDescription] = useState(initial?.description ?? "");
  const [mode, setMode] = useState<PaymentMode>(initial?.payment_mode ?? "online");
  const [amount, setAmount] = useState(initial?.amount ?? "");
  const [noBill, setNoBill] = useState(initial?.no_bill_declaration ?? false);
  const [showGst, setShowGst] = useState(Boolean(initial?.gstin || initial?.tax_amount));
  const [gstin, setGstin] = useState(initial?.gstin ?? "");
  const [tax, setTax] = useState(initial?.tax_amount ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [over, setOver] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const category = categories.find((c) => c.id === categoryId);
  const overLimit = Boolean(category?.per_item_limit && amount && Number(amount) > Number(category.per_item_limit));

  function submit(e: FormEvent) {
    e.preventDefault();
    onSave(
      {
        expense_date: date,
        category_id: categoryId,
        description: description.trim(),
        payment_mode: mode,
        amount: Number(amount).toFixed(2),
        no_bill_declaration: mode === "cash" && noBill && !file,
        gstin: showGst && gstin.trim() ? gstin.trim().toUpperCase() : null,
        tax_amount: showGst && tax ? Number(tax).toFixed(2) : null,
      },
      file,
    );
  }

  return (
    <form onSubmit={submit} className="stack" style={{ gap: 18 }}>
      <div className="form-grid">
        <label className="field col-3">
          <span>Date</span>
          <input className="input" type="date" required max={today()} value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label className="field col-6">
          <span>Category</span>
          <select className="input" required aria-label="Category" aria-describedby="category-limit" value={categoryId}
            onChange={(e) => setCategoryId(Number(e.target.value))}>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <span className="help" id="category-limit">{limitText(category)}</span>
        </label>
        <label className="field col-3">
          <span>Amount</span>
          <div className="affix">
            <span className="pre" aria-hidden="true">₹</span>
            <input className="input" type="number" required min="0.01" step="0.01" inputMode="decimal" placeholder="0.00"
              value={amount} onChange={(e) => setAmount(e.target.value)} />
          </div>
        </label>
        <label className="field col-8">
          <span>Description</span>
          <input className="input" required maxLength={500} placeholder="What was it for? e.g. Cab to client office, BKC"
            value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
        <div className="field col-4">
          <span>Paid by</span>
          <div className="seg" role="radiogroup" aria-label="Paid by">
            <button type="button" role="radio" aria-checked={mode === "online"} className={mode === "online" ? "on" : ""} onClick={() => setMode("online")}>
              <CreditCard size={15} /> Online
            </button>
            <button type="button" role="radio" aria-checked={mode === "cash"} className={mode === "cash" ? "on" : ""} onClick={() => setMode("cash")}>
              <Banknote size={15} /> Cash
            </button>
          </div>
        </div>
      </div>

      {overLimit && (
        <Notice tone="warn">
          This is above the {category?.name} limit of {money(category?.per_item_limit)}. You can still submit it; your manager will see a warning.
        </Notice>
      )}

      {!initial && (
        <div className="field">
          <span>Bill</span>
          {file ? (
            <div className="file" style={{ maxWidth: 380, height: 36 }}>
              <Paperclip size={14} />
              <span className="ellipsis fname">{file.name}</span>
              <span className="fsize">{fileSize(file.size)}</span>
              <button type="button" className="x" aria-label="Remove file" onClick={() => setFile(null)}><X size={14} /></button>
            </div>
          ) : (
            <div
              className={`dropzone ${over ? "over" : ""}`}
              role="button"
              tabIndex={0}
              onClick={() => fileInput.current?.click()}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && fileInput.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setOver(true);
              }}
              onDragLeave={() => setOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setOver(false);
                const f = e.dataTransfer.files?.[0];
                if (f) setFile(f);
              }}
            >
              <span className="icon"><Upload size={16} /></span>
              <span><b>Choose a file</b> or drag the bill here<br /><span className="tiny faint">PDF, JPG or PNG up to 10 MB. A phone photo is fine.</span></span>
            </div>
          )}
          <input ref={fileInput} type="file" hidden accept="application/pdf,image/jpeg,image/png"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              e.target.value = "";
            }} />
        </div>
      )}

      <div className="stack" style={{ gap: 10 }}>
        {mode === "cash" && !file && (
          <label className="check">
            <input type="checkbox" checked={noBill} onChange={(e) => setNoBill(e.target.checked)} />
            <span>
              I don't have a bill for this cash expense
              <span className="desc">You declare the expense is genuine. Allowed for small cash amounts only.</span>
            </span>
          </label>
        )}
        <label className="check">
          <input type="checkbox" checked={showGst} onChange={(e) => setShowGst(e.target.checked)} />
          <span>The bill shows GST details</span>
        </label>
      </div>

      {showGst && (
        <div className="form-grid">
          <label className="field col-4">
            <span>Vendor GSTIN</span>
            <input className="input" maxLength={15} placeholder="27ABCDE1234F1Z5" value={gstin} onChange={(e) => setGstin(e.target.value)} />
          </label>
          <label className="field col-3">
            <span>GST amount</span>
            <div className="affix">
              <span className="pre" aria-hidden="true">₹</span>
              <input className="input" type="number" min="0" step="0.01" value={tax} onChange={(e) => setTax(e.target.value)} />
            </div>
          </label>
        </div>
      )}

      <div className="row tight" style={{ justifyContent: "flex-end" }}>
        <button type="button" className="btn" onClick={onCancel}>Cancel</button>
        <button className="btn btn-primary" type="submit" disabled={busy || !categories.length}>
          {initial ? "Save changes" : "Add expense"}
        </button>
      </div>
    </form>
  );
}
