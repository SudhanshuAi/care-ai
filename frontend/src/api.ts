import type {
  AppointmentDetail,
  AppointmentListResponse,
  ReceiptListResponse,
  RetryResponse,
} from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

export function getApiBase(): string {
  return API_BASE;
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  if (!API_BASE) {
    throw new Error("VITE_API_BASE_URL is not configured.");
  }

  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) {
        detail = body.detail;
      }
    } catch {
      // keep status fallback
    }
    throw new Error(detail);
  }

  return (await response.json()) as T;
}

export function listAppointments(params: {
  status?: string;
  pms_sync_status?: string;
  limit?: number;
  offset?: number;
}): Promise<AppointmentListResponse> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.pms_sync_status) query.set("pms_sync_status", params.pms_sync_status);
  query.set("limit", String(params.limit ?? 50));
  query.set("offset", String(params.offset ?? 0));
  return request(`/admin/pms/appointments?${query}`);
}

export function getAppointment(id: string): Promise<AppointmentDetail> {
  return request(`/admin/pms/appointments/${id}`);
}

export function listReceipts(params: {
  operation?: string;
  limit?: number;
}): Promise<ReceiptListResponse> {
  const query = new URLSearchParams();
  if (params.operation) query.set("operation", params.operation);
  query.set("limit", String(params.limit ?? 50));
  return request(`/admin/pms/receipts?${query}`);
}

export function retryAppointment(id: string): Promise<RetryResponse> {
  return request(`/admin/pms/appointments/${id}/retry`, { method: "POST" });
}
