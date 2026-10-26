export type Role = 'OPERATOR' | 'ADMIN';
export type User = { id: string; email: string; full_name: string; role: Role; is_active: boolean; is_primary: boolean; created_at: string };
export type Room = {
  id: string; dormitory_id: string; number: string; floor: number; capacity: number; price: number | null; notes: string;
  is_active: boolean; resident_count: number; available_beds: number;
};
export type Resident = {
  id: string; first_name: string; last_name: string; phone: string | null; telegram_username: string | null;
  room_id: string | null; room_number: string | null; check_in_date: string | null; departed_on: string | null;
  payment_period_days: number | null; agreed_price: number | null; notes: string; is_archived: boolean;
  created_at: string; updated_at: string; billing_start: string | null; billing_end: string | null;
  billing_period_id: string | null; billing_status: string; paid_amount: number; balance: number; overdue_days: number;
};
export type BillingPeriod = {
  id: string; start_date: string; end_date: string; period_days: number;
  charge_amount: number; paid_amount: number; balance: number; status: string;
};
export type BillingChange = {
  id: string; billing_period_id: string; old_start_date: string; old_end_date: string; old_charge_amount: number | string | null;
  new_start_date: string; new_end_date: string; new_charge_amount: number | string | null; change_type: string; reason: string; created_at: string;
};
export type ResidentDetail = Resident & { billing_history: BillingPeriod[]; changes: BillingChange[] };
export type Payment = {
  id: string; resident_id: string; resident_name: string; billing_period_id: string | null;
  amount: number; net_amount: number; payment_date: string; method: string;
  covered_start: string | null; covered_end: string | null; notes: string;
  recorded_by: string; recorded_by_name: string; created_at: string;
};
export type Notification = { id: string; title: string; message: string; kind: string; entity_id: string | null; read_at: string | null; created_at: string };

export type ExpenseCategory = 'UTILITIES' | 'REPAIR' | 'SUPPLIES' | 'FOOD' | 'SALARY' | 'OTHER';
export type Expense = {
  id: string; expense_date: string; category: ExpenseCategory; description: string;
  amount: number; method: string; reference: string; recorded_by: string;
  recorded_by_name: string; voided_at: string | null; voided_by: string | null;
  void_reason: string; created_at: string;
};

export type Page<T> = { items: T[]; total: number; skip: number; limit: number };
export type Dashboard = {
  residents: number; rooms: number; occupancy_rate: number; available_beds: number;
  due_today: number; due_soon: number; overdue: number; actual_revenue: number; actual_expenses: number; net_cash_flow: number;
  expected_payments: number; outstanding_debt: number;
  revenue_trend: { month: string; amount: number }[];
  occupancy_by_room: { room: string; occupied: number; available: number }[];
  recent_payments: Payment[]; recent_residents: Resident[];
};
export type SystemSettings = { dorm_name: string; default_period_days: number; currency: 'UZS'; updated_at: string | null; billing_change_allowed: boolean };
export type AuditEvent = { id: string; actor_id: string | null; actor_name: string; action: string; entity_type: string; entity_id: string | null; details: Record<string, unknown>; created_at: string };
export type PaymentAdjustment = { id: string; payment_id: string; amount_delta: number; reason: string; adjusted_by: string; created_at: string };
export type Dormitory = { id: string; name: string; address: string; is_default: boolean; is_active: boolean };
export type Campaign = {
  id: string; name: string; dormitory_id: string; status: string; custom_fields: CustomField[];
  document_types: string[]; consent_version: string; consent_text: string; created_at: string;
};
export type CustomField = { key: string; label: string; kind: 'text' | 'date' | 'select' | 'checkbox'; required: boolean; options: string[] };
export type Invitation = {
  id: string; campaign_id: string; dormitory_id: string; expires_at: string; max_submissions: number;
  submission_count: number; paused_at: string | null; revoked_at: string | null; created_at: string;
  status: 'ACTIVE' | 'PAUSED' | 'REVOKED' | 'EXPIRED' | 'EXHAUSTED'; link?: string | null;
};
export type ApplicationData = {
  first_name_latin: string; last_name_latin: string; middle_name_latin: string;
  first_name_cyrillic: string; last_name_cyrillic: string; middle_name_cyrillic: string;
  birth_date: string | null; nationality: string; gender: 'FEMALE' | 'MALE' | null;
  phone: string; email: string; address: string; emergency_name: string; emergency_phone: string;
  institution: string; faculty: string; course: string; study_group: string;
  study_start: string | null; study_end: string | null; requested_move_in: string | null; requested_move_out: string | null;
  preferences: string; additional_data: Record<string, string | boolean | null>;
};
type ApplicationFileBase = {
  id: string; kind: 'PHOTO' | 'DOCUMENT'; document_type: string; original_name: string;
  content_type: string; size_bytes: number; scan_status: string; ocr_status: string; uploaded_at: string;
};
export type ApplicationFile = ApplicationFileBase & { ocr_text: string | null; ocr_truncated: boolean };
export type PublicApplicationFile = ApplicationFileBase;
export type ApplicationEvent = { from_status: string; to_status: string; reason: string; created_at: string };
export type Application = ApplicationData & {
  id: string; reference: string; status: string; requested_fields: string[]; review_reason: string;
  consent_version: string; invitation_id: string; campaign_id: string; dormitory_id: string;
  resident_id: string | null; assigned_to: string | null; internal_notes: string;
  files: ApplicationFile[]; events: ApplicationEvent[]; created_at: string; updated_at: string;
};
export type ApplicationQueueItem = {
  id: string; reference: string; status: string; first_name_latin: string; last_name_latin: string;
  phone: string; campaign_id: string; dormitory_id: string; assigned_to: string | null; created_at: string;
};
export type PublicCampaign = { name: string; custom_fields: CustomField[]; document_types: string[]; consent_version: string; consent_text: string };
export type PublicApplication = ApplicationData & { reference: string; status: string; requested_fields: string[]; review_reason: string; consent_version: string };
export type AdmissionSettings = { storage_backend: string; storage_configured: boolean; retention_days: number | null; default_period_days: number; billing_change_allowed: boolean; uploads_enabled: boolean; ocr_configured: boolean; antivirus_configured: boolean };
export type AdmissionSummary = {
  total_applications: number; applications_this_month: number; pending_applications: number;
  approved_applications: number; approved_this_month: number; rejected_applications: number; linked_residents: number;
  expected_payments: number; outstanding_debt: number; actual_revenue_this_month: number;
  by_status: Record<string, number>;
};
