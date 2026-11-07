import type { ClaimStatus } from "./types";

const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });

export const money = (value: string | number | null | undefined): string =>
  value === null || value === undefined || value === "" ? "—" : inr.format(Number(value));

export const day = (iso: string | null | undefined): string =>
  iso
    ? new Date(iso.length === 10 ? `${iso}T00:00:00` : iso).toLocaleDateString("en-IN", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      })
    : "—";

export const dateTime = (iso: string | null | undefined): string =>
  iso
    ? new Date(iso).toLocaleString("en-IN", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";

export const monthLabel = (period: string): string => {
  const [y, m] = period.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString("en-IN", { month: "long", year: "numeric" });
};

export const shortMonth = (period: string): string => {
  const [y, m] = period.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString("en-IN", { month: "short", year: "numeric" });
};

export const initials = (name: string): string =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("");

export const fileSize = (bytes: number): string =>
  bytes < 1024 ? `${bytes} B` : bytes < 1024 * 1024 ? `${Math.round(bytes / 1024)} KB` : `${(bytes / 1048576).toFixed(1)} MB`;

/** "today", "yesterday", "3 days ago", then a date. */
export const ago = (iso: string | null | undefined): string => {
  if (!iso) return "—";
  const then = new Date(iso);
  const days = Math.floor((Date.now() - then.getTime()) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  return day(iso);
};

export const STATUS_TONE: Record<ClaimStatus, "" | "gray" | "warn" | "bad" | "good"> = {
  draft: "gray",
  submitted: "",
  returned: "warn",
  manager_approved: "",
  verified: "",
  in_payout_batch: "",
  paid: "good",
  rejected: "bad",
};

export const STATUS_LABEL: Record<ClaimStatus, string> = {
  draft: "Draft",
  submitted: "With manager",
  returned: "Returned",
  manager_approved: "With Accounts",
  verified: "Verified",
  in_payout_batch: "In payout",
  paid: "Paid",
  rejected: "Rejected",
};

export const ACTION_LABEL: Record<string, string> = {
  created: "Created the claim",
  submitted: "Submitted",
  withdrawn: "Withdrew the claim",
  manager_approved: "Approved",
  verified: "Verified",
  returned: "Returned for changes",
  rejected: "Rejected",
  added_to_batch: "Added to a payout batch",
  removed_from_batch: "Removed from the payout batch",
  paid: "Marked as paid",
  comment: "Commented",
};

export const today = (): string => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export const thisPeriod = (): string => today().slice(0, 7);
