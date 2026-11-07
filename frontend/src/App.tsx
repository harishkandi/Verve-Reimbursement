import {
  BarChart3,
  BookOpen,
  ClipboardCheck,
  Inbox,
  LogOut,
  Menu,
  Receipt,
  Settings,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { get } from "./api";
import { useAuth } from "./auth";
import { DialogProvider } from "./components/Dialog";
import { Avatar } from "./components/ui";
import AdminPage from "./pages/Admin";
import BatchPage from "./pages/Batch";
import ClaimPage from "./pages/Claim";
import InboxPage from "./pages/Inbox";
import LoginPage from "./pages/Login";
import MyClaimsPage from "./pages/MyClaims";
import PayoutsPage from "./pages/Payouts";
import PolicyPage from "./pages/Policy";
import { ToastProvider } from "./components/Toast";
import ReportsPage from "./pages/Reports";
import type { ClaimSummary, Me } from "./types";

export function roleLabel(me: Pick<Me, "is_admin" | "can_verify" | "can_pay" | "is_approver">): string {
  if (me.is_admin) return "Admin";
  if (me.can_verify || me.can_pay) return "Accounts";
  if (me.is_approver) return "Manager";
  return "Employee";
}

interface Counts {
  approvals?: number;
  verification?: number;
  payouts?: number;
}

/** Badge counts for the sidebar; refreshed on every navigation so they follow the user's actions. */
function useCounts(me: Me): Counts {
  const { pathname } = useLocation();
  const [counts, setCounts] = useState<Counts>({});
  useEffect(() => {
    const n = (url: string) => get<ClaimSummary[]>(url).then((r) => r.length).catch(() => undefined);
    void Promise.all([
      me.is_approver ? n("/api/inbox/approvals") : undefined,
      me.can_verify ? n("/api/inbox/verification") : undefined,
      me.can_pay ? n("/api/payouts/ready") : undefined,
    ]).then(([approvals, verification, payouts]) => setCounts({ approvals, verification, payouts }));
  }, [me, pathname]);
  return counts;
}

function NavItem({ to, icon: Icon, label, count, end }: { to: string; icon: LucideIcon; label: string; count?: number; end?: boolean }) {
  return (
    <NavLink to={to} end={end} className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
      <Icon size={18} />
      {label}
      {count ? <span className="count">{count}</span> : null}
    </NavLink>
  );
}

function Brand() {
  return (
    <div className="brand">
      <div className="brand-mark">₹</div>
      <div>
        <div className="brand-name">Verve</div>
        <div className="brand-sub">Reimbursements</div>
      </div>
    </div>
  );
}

function Sidebar({ me, open, onSignOut }: { me: Me; open: boolean; onSignOut: () => void }) {
  const counts = useCounts(me);
  const finance = me.is_admin || me.can_verify || me.can_pay;
  return (
    <aside className={`sidebar ${open ? "open" : ""}`} aria-label="Main navigation">
      <Brand />
      <nav className="stack" style={{ gap: 2 }}>
        <NavItem to="/" end icon={Receipt} label="My claims" />
        {(me.is_approver || me.can_verify) && <div className="nav-label">Review</div>}
        {me.is_approver && <NavItem to="/approvals" icon={Inbox} label="Approvals" count={counts.approvals} />}
        {me.can_verify && <NavItem to="/verification" icon={ClipboardCheck} label="Verification" count={counts.verification} />}
        {finance && <div className="nav-label">Finance</div>}
        {me.can_pay && <NavItem to="/payouts" icon={Wallet} label="Payouts" count={counts.payouts} />}
        {finance && <NavItem to="/reports" icon={BarChart3} label="Reports" />}
        {me.is_admin && <NavItem to="/admin" icon={Settings} label="Admin" />}
        <div className="nav-label">Help</div>
        <NavItem to="/policy" icon={BookOpen} label="Policy & limits" />
      </nav>
      <div className="sidebar-foot">
        <Avatar name={me.name} />
        <div className="who">
          <div className="name ellipsis">{me.name}</div>
          <div className="role">{roleLabel(me)}</div>
        </div>
        <button className="btn btn-ghost btn-icon" onClick={onSignOut} aria-label="Sign out">
          <LogOut size={17} />
        </button>
      </div>
    </aside>
  );
}

export default function App() {
  const { me, loading, signOut } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const { pathname } = useLocation();

  useEffect(() => {
    setMenuOpen(false);
    window.scrollTo(0, 0);
  }, [pathname]);

  if (loading) return null;
  if (!me) {
    return (
      <Routes>
        <Route path="*" element={<LoginPage />} />
      </Routes>
    );
  }

  const finance = me.is_admin || me.can_verify || me.can_pay;
  return (
    <ToastProvider>
      <DialogProvider>
        <div className="app">
          <Sidebar me={me} open={menuOpen} onSignOut={signOut} />
          {menuOpen && <div className="scrim" onClick={() => setMenuOpen(false)} />}
          <div>
            <header className="topbar">
              <button className="btn btn-ghost btn-icon" aria-label="Open menu" onClick={() => setMenuOpen(true)}>
                <Menu size={20} />
              </button>
              <Brand />
            </header>
            <main className="content">
              <Routes>
                <Route path="/" element={<MyClaimsPage />} />
                <Route path="/claims/:id" element={<ClaimPage />} />
                <Route path="/policy" element={<PolicyPage />} />
                {me.is_approver && <Route path="/approvals" element={<InboxPage kind="approvals" />} />}
                {me.can_verify && <Route path="/verification" element={<InboxPage kind="verification" />} />}
                {me.can_pay && <Route path="/payouts" element={<PayoutsPage />} />}
                {me.can_pay && <Route path="/payouts/:id" element={<BatchPage />} />}
                {finance && <Route path="/reports" element={<ReportsPage />} />}
                {me.is_admin && <Route path="/admin" element={<AdminPage />} />}
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </main>
          </div>
        </div>
      </DialogProvider>
    </ToastProvider>
  );
}
