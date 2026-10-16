export type Role = 'OPERATOR' | 'ADMIN';
export type User = { id: string; email: string; full_name: string; role: Role; is_active: boolean; is_primary: boolean; created_at: string };
export type Room = {
  id: string; number: string; floor: number; capacity: number; price: number | null; notes: string;
  is_active: boolean; resident_count: number; available_beds: number;
};
export type Resident = {
  id: string; first_name: string; last_name: string; phone: string | null; telegram_username: string | null;
  room_id: string | null; room_number: string | null; check_in_date: string | null;
  payment_period_days: number | null; agreed_price: number | null; notes: string; is_archived: boolean;
  created_at: string; updated_at: string; billing_start: string | null; billing_end: string | null;
  billing_period_id: string | null; billing_status: string; paid_amount: number; balance: number; overdue_days: number;
};
export type BillingPeriod = {
  id: string; start_date: string; end_date: string; period_days: number;
  charge_amount: number; paid_amount: number; balance: number; status: string;
};
export type BillingChange = {
  id: string; billing_period_id: string; old_start_date: string; old_end_date: string;
  new_start_date: string; new_end_date: string; change_type: string; reason: string; created_at: string;
};
export type ResidentDetail = Resident & { billing_history: BillingPeriod[]; changes: BillingChange[] };
export type Payment = {
  id: string; resident_id: string; resident_name: string; billing_period_id: string | null;
  amount: number; net_amount: number; payment_date: string; method: string;
  covered_start: string | null; covered_end: string | null; notes: string;
  recorded_by: string; recorded_by_name: string; created_at: string;
};
export type Notification = { id: string; title: string; message: string; kind: string; entity_id: string | null; read_at: string | null; created_at: string };
export type Page<T> = { items: T[]; total: number; skip: number; limit: number };
export type Dashboard = {
  residents: number; rooms: number; occupancy_rate: number; available_beds: number;
  due_today: number; due_soon: number; overdue: number; actual_revenue: number;
  expected_payments: number; outstanding_debt: number;
  revenue_trend: { month: string; amount: number }[];
  occupancy_by_room: { room: string; occupied: number; available: number }[];
  recent_payments: Payment[]; recent_residents: Resident[];
};
export type SystemSettings = { dorm_name: string; default_period_days: number; currency: 'UZS'; updated_at: string | null; billing_change_allowed: boolean };
export type AuditEvent = { id: string; actor_id: string | null; actor_name: string; action: string; entity_type: string; entity_id: string | null; details: Record<string, unknown>; created_at: string };
export type PaymentAdjustment = { id: string; payment_id: string; amount_delta: number; reason: string; adjusted_by: string; created_at: string };
