import { FolderKanban, Plus, Search, ShieldCheck, Upload, Users } from "lucide-react";
import { useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { get, post, put, upload } from "../api";
import { ErrorNote, Notice, PageHead, Person, SkeletonRows } from "../components/ui";
import type { AdminUser, Category, ImportResult, Policy } from "../types";
import { useLoad } from "../useLoad";

export default function AdminPage() {
  const [tab, setTab] = useState<"users" | "categories" | "policy">("users");
  const tabs = [
    { key: "users", label: "People", icon: Users },
    { key: "categories", label: "Categories", icon: FolderKanban },
    { key: "policy", label: "Policy", icon: ShieldCheck },
  ] as const;
  return (
    <>
      <PageHead title="Admin" sub="People and reporting lines, expense categories and policy limits." />
      <div className="tabs" role="tablist">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? "on" : ""} onClick={() => setTab(key)}>
            <Icon size={15} /> {label}
          </button>
        ))}
      </div>
      {tab === "users" && <People />}
      {tab === "categories" && <Categories />}
      {tab === "policy" && <PolicyForm />}
    </>
  );
}

type UserForm = Omit<AdminUser, "id">;
const blankUser: UserForm = {
  email: "", name: "", employee_code: null, department: null, manager_id: null, is_admin: false,
  can_verify: false, can_pay: false, is_fallback_approver: false, is_active: true,
  bank_account_name: null, bank_account_number: null, bank_ifsc: null,
};

const ACCESS: [keyof UserForm, string, string][] = [
  ["can_verify", "Accounts: verify", "Checks manager-approved claims against bills"],
  ["can_pay", "Accounts: payouts", "Creates payout batches and records payments"],
  ["is_fallback_approver", "Top-level approver", "Approves claims from people with no manager"],
  ["is_admin", "Admin", "Manages people, categories and policy"],
  ["is_active", "Active", "Can sign in and submit claims"],
];

function People() {
  const { data: users, reload, error: loadError } = useLoad(() => get<AdminUser[]>("/api/admin/users"));
  const [editing, setEditing] = useState<AdminUser | "new" | null>(null);
  const [form, setForm] = useState<UserForm>(blankUser);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");

  const byId = new Map((users ?? []).map((u) => [u.id, u]));
  const q = query.trim().toLowerCase();
  const shown = (users ?? []).filter(
    (u) => !q || [u.name, u.email, u.department, u.employee_code].some((v) => v?.toLowerCase().includes(q)),
  );
  const startEdit = (u: AdminUser | "new") => {
    setEditing(u);
    setError(null);
    setForm(u === "new" ? blankUser : { ...u });
    window.scrollTo({ top: 0 });
  };
  const set = <K extends keyof UserForm>(k: K, v: UserForm[K]) => setForm((f) => ({ ...f, [k]: v }));
  const text = (k: keyof UserForm) => (e: ChangeEvent<HTMLInputElement>) => set(k, (e.target.value || null) as never);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (editing === "new") await post("/api/admin/users", form);
      else if (editing) await put(`/api/admin/users/${editing.id}`, form);
      setEditing(null);
      await reload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function importCsv(file: File) {
    setBusy(true);
    setError(null);
    try {
      setResult(await upload<ImportResult>("/api/admin/users/import", file));
      await reload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const reports = new Map<number, number>();
  for (const u of users ?? []) if (u.manager_id && u.is_active) reports.set(u.manager_id, (reports.get(u.manager_id) ?? 0) + 1);
  const tags = (u: AdminUser) =>
    [
      reports.get(u.id) && `Manages ${reports.get(u.id)}`,
      u.is_admin && "Admin",
      u.can_verify && "Verify",
      u.can_pay && "Payouts",
      u.is_fallback_approver && "Top-level approver",
    ].filter(Boolean) as string[];

  return (
    <div className="stack" style={{ gap: 20 }}>
      <ErrorNote error={error || loadError} />
      {result && (
        <Notice tone={result.errors.length ? "warn" : "success"} title={`Import finished: ${result.created} added, ${result.updated} updated`}>
          {result.errors.length > 0 && <ul>{result.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>}
        </Notice>
      )}

      {editing && (
        <form className="card" onSubmit={save}>
          <div className="card-head"><h2>{editing === "new" ? "Add a person" : `Edit ${editing.name}`}</h2></div>
          <div className="card-body stack" style={{ gap: 20 }}>
            <div className="form-grid">
              <label className="field col-6"><span>Full name</span><input className="input" required value={form.name} onChange={(e) => set("name", e.target.value)} /></label>
              <label className="field col-6"><span>Work email</span><input className="input" type="email" required value={form.email} onChange={(e) => set("email", e.target.value)} /></label>
              <label className="field col-4"><span>Employee code</span><input className="input" value={form.employee_code ?? ""} onChange={text("employee_code")} /></label>
              <label className="field col-4"><span>Department</span><input className="input" value={form.department ?? ""} onChange={text("department")} /></label>
              <label className="field col-4"><span>Reports to</span>
                <select className="input" value={form.manager_id ?? ""} onChange={(e) => set("manager_id", e.target.value ? Number(e.target.value) : null)}>
                  <option value="">No manager (top level)</option>
                  {(users ?? []).filter((u) => editing === "new" || u.id !== editing.id).map((u) => (
                    <option key={u.id} value={u.id}>{u.name}</option>
                  ))}
                </select>
              </label>
            </div>
            <div>
              <h3 style={{ marginBottom: 12 }}>Bank details for payouts</h3>
              <div className="form-grid">
                <label className="field col-4"><span>Account holder</span><input className="input" value={form.bank_account_name ?? ""} onChange={text("bank_account_name")} /></label>
                <label className="field col-4"><span>Account number</span><input className="input num" value={form.bank_account_number ?? ""} onChange={text("bank_account_number")} /></label>
                <label className="field col-4"><span>IFSC</span><input className="input num" maxLength={11} value={form.bank_ifsc ?? ""} onChange={text("bank_ifsc")} /></label>
              </div>
            </div>
            <div>
              <h3 style={{ marginBottom: 12 }}>Access</h3>
              <div className="form-grid">
                {ACCESS.map(([k, label, desc]) => (
                  <label key={k} className="check col-4">
                    <input type="checkbox" checked={Boolean(form[k])} onChange={(e) => set(k, e.target.checked as never)} />
                    <span>{label}<span className="desc">{desc}</span></span>
                  </label>
                ))}
              </div>
            </div>
          </div>
          <div className="card-foot row tight" style={{ justifyContent: "flex-end" }}>
            <button type="button" className="btn" onClick={() => setEditing(null)}>Cancel</button>
            <button className="btn btn-primary" disabled={busy}>Save</button>
          </div>
        </form>
      )}

      <section className="card">
        <div className="card-head">
          <div>
            <h2>{users ? `${users.length} people` : "People"}</h2>
            <div className="hint">Import a CSV with columns: email, name, employee_code, department, manager_email, bank details and access flags.</div>
          </div>
          <div className="row tight">
            <label className="search">
              <Search size={15} />
              <input className="input" type="search" aria-label="Search people" placeholder="Search name, email, team…" value={query}
                onChange={(e) => setQuery(e.target.value)} style={{ width: 220 }} />
            </label>
            <button className="btn btn-sm" disabled={busy} onClick={() => fileInput.current?.click()}><Upload size={14} /> Import CSV</button>
            <input ref={fileInput} type="file" accept=".csv,text/csv" hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                e.target.value = "";
                if (f) void importCsv(f);
              }} />
            <button className="btn btn-primary btn-sm" onClick={() => startEdit("new")}><Plus size={14} /> Add person</button>
          </div>
        </div>
        {!users ? (
          <SkeletonRows />
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Person</th><th>Department</th><th>Reports to</th><th>Access</th><th>Bank details</th><th /></tr></thead>
              <tbody>
                {shown.length === 0 && (
                  <tr><td colSpan={6} className="muted" style={{ textAlign: "center", padding: 28 }}>No one matches "{query}".</td></tr>
                )}
                {shown.map((u) => (
                  <tr key={u.id} className={u.is_active ? "" : "muted-row"}>
                    <td><Person name={u.name} meta={`${u.email}${u.employee_code ? ` · ${u.employee_code}` : ""}`} /></td>
                    <td className="muted">{u.department ?? "—"}</td>
                    <td className="muted">{u.manager_id ? byId.get(u.manager_id)?.name : "—"}</td>
                    <td>
                      <div className="row tight" style={{ gap: 4 }}>
                        {tags(u).length ? tags(u).map((t) => <span key={t} className="badge plain">{t}</span>) : <span className="faint small">Employee</span>}
                        {!u.is_active && <span className="badge plain gray">Inactive</span>}
                      </div>
                    </td>
                    <td>{u.bank_account_number ? <span className="badge good">On file</span> : <span className="badge warn">Missing</span>}</td>
                    <td className="right"><button className="btn btn-sm" onClick={() => startEdit(u)}>Edit</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function Categories() {
  const { data, reload, error: loadError } = useLoad(() => get<Category[]>("/api/admin/categories"));
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");

  async function save(c: Partial<Category> & { name: string }, id?: number) {
    setError(null);
    try {
      const body = {
        name: c.name, is_active: c.is_active ?? true, per_item_limit: c.per_item_limit || null,
        monthly_limit: c.monthly_limit || null, sort_order: c.sort_order ?? 0,
      };
      if (id) await put(`/api/admin/categories/${id}`, body);
      else await post("/api/admin/categories", body);
      await reload();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    }
  }

  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2>Expense categories</h2>
          <div className="hint">Limits only warn in v1: claims above them can still be approved. Leave blank for no limit. Changes save when you leave a field.</div>
        </div>
      </div>
      <div className="card-body" style={{ paddingTop: 0, paddingBottom: 0 }}><ErrorNote error={error || loadError} /></div>
      {!data ? <SkeletonRows /> : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Category</th><th>Limit per item</th><th>Limit per month</th><th>Active</th></tr></thead>
            <tbody>
              {data.map((c) => <CategoryRow key={c.id} cat={c} onSave={(patch) => save({ ...c, ...patch }, c.id)} />)}
            </tbody>
          </table>
        </div>
      )}
      <form className="card-foot row tight"
        onSubmit={async (e) => {
          e.preventDefault();
          if (await save({ name, sort_order: (data?.length ?? 0) + 1 })) setName("");
        }}>
        <input className="input" placeholder="New category, e.g. Internet & phone" required value={name} onChange={(e) => setName(e.target.value)} style={{ maxWidth: 300 }} />
        <button className="btn"><Plus size={15} /> Add category</button>
      </form>
    </section>
  );
}

function CategoryRow({ cat, onSave }: { cat: Category; onSave: (patch: Partial<Category>) => void }) {
  const [item, setItem] = useState(cat.per_item_limit ?? "");
  const [month, setMonth] = useState(cat.monthly_limit ?? "");
  const blur = () => {
    if ((item || null) !== cat.per_item_limit || (month || null) !== cat.monthly_limit)
      onSave({ per_item_limit: item || null, monthly_limit: month || null });
  };
  return (
    <tr className={cat.is_active ? "" : "muted-row"}>
      <td className="strong">{cat.name}</td>
      <td>
        <div className="affix" style={{ maxWidth: 150 }}><span className="pre" aria-hidden="true">₹</span>
          <input className="input" style={{ height: 34 }} type="number" min="0" step="0.01" placeholder="No limit" aria-label={`${cat.name} per item limit`}
            value={item} onChange={(e) => setItem(e.target.value)} onBlur={blur} />
        </div>
      </td>
      <td>
        <div className="affix" style={{ maxWidth: 150 }}><span className="pre" aria-hidden="true">₹</span>
          <input className="input" style={{ height: 34 }} type="number" min="0" step="0.01" placeholder="No limit" aria-label={`${cat.name} monthly limit`}
            value={month} onChange={(e) => setMonth(e.target.value)} onBlur={blur} />
        </div>
      </td>
      <td>
        <label className="check"><input type="checkbox" aria-label={`${cat.name} active`} checked={cat.is_active} onChange={(e) => onSave({ is_active: e.target.checked })} /></label>
      </td>
    </tr>
  );
}

function PolicyForm() {
  const { data, setData, error: loadError } = useLoad(() => get<Policy>("/api/admin/policy"));
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  if (!data) return loadError ? <ErrorNote error={loadError} /> : <div className="card"><SkeletonRows rows={3} /></div>;
  const set = <K extends keyof Policy>(k: K, v: Policy[K]) => {
    setSaved(false);
    setData({ ...data, [k]: v });
  };

  return (
    <form className="card"
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        try {
          setData(await put<Policy>("/api/admin/policy", data));
          setSaved(true);
        } catch (err) {
          setError((err as Error).message);
        }
      }}>
      <div className="card-head">
        <div>
          <h2>Reimbursement policy</h2>
          <div className="hint">Applies to every claim. All limits produce warnings, not blocks, in v1.</div>
        </div>
      </div>
      <div className="card-body stack" style={{ gap: 20 }}>
        <ErrorNote error={error} />
        {saved && <Notice tone="success">Policy saved.</Notice>}
        <div>
          <h3 style={{ marginBottom: 12 }}>Deadlines</h3>
          <div className="form-grid">
            <label className="field col-6"><span>Claims due by (day of next month)</span>
              <input className="input" type="number" min={1} max={28} value={data.submission_due_day} onChange={(e) => set("submission_due_day", Number(e.target.value))} />
              <span className="help">A claim for October is due by this day in November.</span>
            </label>
            <label className="field col-6"><span>Oldest expense without Finance approval (days)</span>
              <input className="input" type="number" min={1} max={365} value={data.max_age_days} onChange={(e) => set("max_age_days", Number(e.target.value))} />
            </label>
          </div>
        </div>
        <div>
          <h3 style={{ marginBottom: 12 }}>Cash expenses without a bill</h3>
          <div className="form-grid">
            <label className="field col-6"><span>Limit per expense</span>
              <div className="affix"><span className="pre" aria-hidden="true">₹</span>
                <input className="input" type="number" min="0" step="0.01" placeholder="Not set" value={data.cash_no_bill_item_limit ?? ""} onChange={(e) => set("cash_no_bill_item_limit", e.target.value || null)} />
              </div>
            </label>
            <label className="field col-6"><span>Limit per month</span>
              <div className="affix"><span className="pre" aria-hidden="true">₹</span>
                <input className="input" type="number" min="0" step="0.01" placeholder="Not set" value={data.cash_no_bill_month_limit ?? ""} onChange={(e) => set("cash_no_bill_month_limit", e.target.value || null)} />
              </div>
              <span className="help">Values to be confirmed by Accounts.</span>
            </label>
          </div>
        </div>
      </div>
      <div className="card-foot" style={{ display: "flex", justifyContent: "flex-end" }}>
        <button className="btn btn-primary">Save policy</button>
      </div>
    </form>
  );
}
