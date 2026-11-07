import { ArrowRight, CheckCircle2 } from "lucide-react";
import { useState } from "react";
import { get } from "../api";
import { useAuth } from "../auth";
import { Avatar, ErrorNote } from "../components/ui";
import type { UserBrief } from "../types";
import { useLoad } from "../useLoad";

type DevUser = UserBrief & { role: string };

/** Development sign-in. Replaced by company SSO (Google or Microsoft) before go-live. */
export default function LoginPage() {
  const { signIn } = useAuth();
  const { data: users } = useLoad(() => get<DevUser[]>("/api/auth/dev-users").catch(() => []));
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function go(address: string) {
    setBusy(true);
    setError(null);
    try {
      await signIn(address);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <section className="auth-brand">
        <div className="brand" style={{ padding: 0 }}>
          <div className="brand-mark">₹</div>
          <div>
            <div className="brand-name">Verve</div>
            <div className="brand-sub" style={{ color: "var(--brand-200)" }}>Reimbursements</div>
          </div>
        </div>
        <div>
          <h1>Expense claims, approved and paid without the spreadsheet.</h1>
          <p>Submit your monthly expenses with bills attached. Your manager and Accounts review them here, and you can see where your claim is at every step.</p>
          <ul className="auth-points">
            <li><CheckCircle2 size={18} />One claim a month, every bill attached to its expense</li>
            <li><CheckCircle2 size={18} />Manager approval, then Accounts verification</li>
            <li><CheckCircle2 size={18} />Monthly bank payout, with the reference recorded</li>
          </ul>
        </div>
        <div className="legal tiny" style={{ color: "var(--brand-200)" }}>Verve Advisory · Internal use only</div>
      </section>

      <section className="auth-form">
        <div className="auth-card">
          <h1 style={{ fontSize: 22 }}>Sign in</h1>
          <p className="muted" style={{ marginTop: 6 }}>Use your work email. Company single sign-on replaces this before launch.</p>
          <div style={{ marginTop: 20 }}>
            <ErrorNote error={error} />
          </div>
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault();
              void go(email);
            }}
          >
            <label className="field">
              <span>Work email</span>
              <input className="input" type="email" required autoComplete="email" placeholder="name@verve.example"
                value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            <button className="btn btn-primary" style={{ height: 40 }} disabled={busy}>
              Continue <ArrowRight size={16} />
            </button>
          </form>

          {users && users.length > 0 && (
            <>
              <div className="divider">Or sign in as a test user</div>
              <div className="who-grid">
                {users.map((u) => (
                  <button key={u.id} className="who-btn" disabled={busy} onClick={() => go(u.email)}>
                    <Avatar name={u.name} size="sm" />
                    <div className="grow" style={{ minWidth: 0 }}>
                      <div className="n ellipsis">{u.name}</div>
                      <div className="r">{u.role}</div>
                    </div>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </section>
    </div>
  );
}
