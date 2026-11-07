// Mirrors backend/app/schemas.py. Money comes back as decimal strings to keep paise exact.

export type ClaimStatus =
  | "draft"
  | "submitted"
  | "returned"
  | "manager_approved"
  | "verified"
  | "in_payout_batch"
  | "paid"
  | "rejected";
export type LineStatus = "pending" | "approved" | "rejected";
export type PaymentMode = "cash" | "online";
export type Action = "edit" | "submit" | "withdraw" | "approve" | "verify" | "return" | "reject" | "comment";

export interface UserBrief {
  id: number;
  name: string;
  email: string;
}

export interface User extends UserBrief {
  employee_code: string | null;
  department: string | null;
  manager_id: number | null;
  is_admin: boolean;
  can_verify: boolean;
  can_pay: boolean;
  is_fallback_approver: boolean;
  is_active: boolean;
}

export interface Me extends User {
  is_approver: boolean;
  manager: UserBrief | null;
}

export interface AdminUser extends User {
  bank_account_name: string | null;
  bank_account_number: string | null;
  bank_ifsc: string | null;
}

export interface Category {
  id: number;
  name: string;
  is_active: boolean;
  per_item_limit: string | null;
  monthly_limit: string | null;
  sort_order: number;
}

export interface Policy {
  submission_due_day: number;
  max_age_days: number;
  cash_no_bill_item_limit: string | null;
  cash_no_bill_month_limit: string | null;
}

export interface Attachment {
  id: number;
  original_name: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
}

export interface Line {
  id: number;
  expense_date: string;
  category_id: number;
  category_name: string;
  description: string;
  payment_mode: PaymentMode;
  amount: string;
  approved_amount: string | null;
  status: LineStatus;
  adjust_reason: string | null;
  no_bill_declaration: boolean;
  gstin: string | null;
  tax_amount: string | null;
  attachments: Attachment[];
}

export interface LineInput {
  expense_date: string;
  category_id: number;
  description: string;
  payment_mode: PaymentMode;
  amount: string;
  no_bill_declaration: boolean;
  gstin: string | null;
  tax_amount: string | null;
}

export interface PolicyWarning {
  code: string;
  message: string;
  line_id: number | null;
}

export interface ClaimEvent {
  id: number;
  action: string;
  from_status: string | null;
  to_status: string | null;
  comment: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
  actor: UserBrief;
}

export interface ClaimSummary {
  id: number;
  period: string;
  status: ClaimStatus;
  employee: UserBrief;
  employee_department: string | null;
  approver: UserBrief | null;
  total_claimed: string;
  total_approved: string;
  line_count: number;
  submitted_at: string | null;
  status_changed_at: string;
  payout_batch_id: number | null;
  payment_reference: string | null;
  paid_at: string | null;
  warning_count: number | null;
}

export interface ClaimDetail extends ClaimSummary {
  lines: Line[];
  events: ClaimEvent[];
  warnings: PolicyWarning[];
  allowed_actions: Action[];
}

export interface LineDecision {
  line_id: number;
  decision: "approve" | "reject";
  approved_amount?: string | null;
  reason?: string | null;
}

export interface BatchSummary {
  id: number;
  payout_date: string;
  status: "open" | "paid";
  created_by: UserBrief;
  created_at: string;
  paid_on: string | null;
  reference: string | null;
  claim_count: number;
  total: string;
}

export interface BatchDetail extends BatchSummary {
  claims: ClaimSummary[];
}

export interface PendingRow {
  claim: ClaimSummary;
  stage: ClaimStatus;
  waiting_with: string;
  days_waiting: number;
}

export interface ImportResult {
  created: number;
  updated: number;
  errors: string[];
}
