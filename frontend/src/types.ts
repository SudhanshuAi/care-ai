export type AppointmentSummary = {
  appointment_id: string;
  status: string;
  patient_id: string;
  patient_name: string;
  patient_phone: string;
  practitioner_id: string;
  practitioner_name: string;
  branch_id: string;
  branch_name: string;
  appointment_type_id: string;
  appointment_type_name: string;
  start_time: string;
  end_time: string;
  pms_sync_status: string;
  pms_sync_operation: string | null;
  pms_sync_attempts: number;
  pms_last_attempt_at: string | null;
  pms_synced_at: string | null;
  pms_last_error: string | null;
  receipt_count: number;
  created_at: string;
};

export type PmsReceipt = {
  id: string;
  appointment_id: string;
  operation: string;
  idempotency_key: string;
  payload: Record<string, unknown>;
  received_at: string;
};

export type AppointmentDetail = AppointmentSummary & {
  notes: string | null;
  receipts: PmsReceipt[];
};

export type AppointmentListResponse = {
  total: number;
  items: AppointmentSummary[];
};

export type ReceiptListResponse = {
  total: number;
  items: PmsReceipt[];
};

export type RetryResponse = {
  appointment_id: string;
  operation: string;
  status: string;
  attempted: boolean;
  detail: string | null;
};
