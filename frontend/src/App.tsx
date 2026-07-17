import { useCallback, useEffect, useState } from "react";
import {
  getApiBase,
  getAppointment,
  listAppointments,
  listReceipts,
  retryAppointment,
} from "./api";
import type {
  AppointmentDetail,
  AppointmentSummary,
  PmsReceipt,
} from "./types";

function formatWhen(value: string | null | undefined): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kolkata",
  }).format(new Date(value));
}

function StatusBadge({ value }: { value: string }) {
  const cls = `badge badge-${value.replace(/\s+/g, "_")}`;
  return <span className={cls}>{value}</span>;
}

export default function App() {
  const [status, setStatus] = useState("");
  const [pmsStatus, setPmsStatus] = useState("");
  const [items, setItems] = useState<AppointmentSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AppointmentDetail | null>(null);
  const [recentReceipts, setRecentReceipts] = useState<PmsReceipt[]>([]);
  const [loading, setLoading] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (!getApiBase()) {
        throw new Error("Build is missing VITE_API_BASE_URL.");
      }
      const [appointments, receipts] = await Promise.all([
        listAppointments({
          status: status || undefined,
          pms_sync_status: pmsStatus || undefined,
          limit: 50,
        }),
        listReceipts({ limit: 20 }),
      ]);
      setItems(appointments.items);
      setTotal(appointments.total);
      setRecentReceipts(receipts.items);
      if (selectedId) {
        const next = await getAppointment(selectedId);
        setDetail(next);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [status, pmsStatus, selectedId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function openDetail(id: string) {
    setSelectedId(id);
    setError(null);
    try {
      setDetail(await getAppointment(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load detail");
    }
  }

  async function onRetry() {
    if (!selectedId) return;
    setRetrying(true);
    setError(null);
    try {
      await retryAppointment(selectedId);
      await refresh();
      setDetail(await getAppointment(selectedId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Retry failed");
    } finally {
      setRetrying(false);
    }
  }

  const canRetry =
    detail &&
    (detail.pms_sync_status === "pending" ||
      detail.pms_sync_status === "pending_retry" ||
      detail.pms_sync_status === "failed");

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <h1>Mock PMS Console</h1>
          <p>
            Demo write-backs for create, reschedule, and cancel — {total}{" "}
            appointments
          </p>
          <p className="muted" style={{ marginTop: 6, fontSize: "0.85rem" }}>
            API: {getApiBase() || "(not configured)"}
          </p>
        </div>
        <div className="actions">
          <button className="btn" type="button" onClick={() => void refresh()}>
            Refresh
          </button>
        </div>
      </header>

      <section className="panel panel-pad" style={{ marginBottom: 16 }}>
        <div className="filters">
          <div className="field">
            <label htmlFor="status">Appointment status</label>
            <select
              id="status"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="">All</option>
              <option value="booked">booked</option>
              <option value="cancelled">cancelled</option>
              <option value="completed">completed</option>
              <option value="no_show">no_show</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="pms">PMS sync status</label>
            <select
              id="pms"
              value={pmsStatus}
              onChange={(event) => setPmsStatus(event.target.value)}
            >
              <option value="">All</option>
              <option value="synced">synced</option>
              <option value="pending">pending</option>
              <option value="pending_retry">pending_retry</option>
              <option value="failed">failed</option>
            </select>
          </div>
          <div className="actions">
            <button
              className="btn btn-primary"
              type="button"
              disabled={loading}
              onClick={() => void refresh()}
            >
              {loading ? "Loading…" : "Apply filters"}
            </button>
          </div>
        </div>
        {error ? <div className="error">{error}</div> : null}
      </section>

      <div className="layout">
        <section className="panel">
          <div className="table-wrap">
            {items.length === 0 ? (
              <div className="empty">No appointments match these filters.</div>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Patient</th>
                    <th>When</th>
                    <th>Status</th>
                    <th>PMS</th>
                    <th>Receipts</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr
                      key={item.appointment_id}
                      className={
                        selectedId === item.appointment_id ? "active" : ""
                      }
                      onClick={() => void openDetail(item.appointment_id)}
                    >
                      <td>
                        <strong>{item.patient_name}</strong>
                        <div className="muted mono">{item.patient_phone}</div>
                      </td>
                      <td>
                        {formatWhen(item.start_time)}
                        <div className="muted">{item.branch_name}</div>
                      </td>
                      <td>
                        <StatusBadge value={item.status} />
                      </td>
                      <td>
                        <StatusBadge value={item.pms_sync_status} />
                        <div className="muted">
                          {item.pms_sync_operation || "—"}
                        </div>
                      </td>
                      <td className="mono">{item.receipt_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <aside className="panel panel-pad">
          {!detail ? (
            <div className="empty">Select an appointment to inspect PMS events.</div>
          ) : (
            <>
              <div className="detail-block">
                <h2 style={{ marginTop: 0 }}>{detail.patient_name}</h2>
                <p className="muted" style={{ marginTop: 0 }}>
                  {detail.appointment_type_name} · {detail.practitioner_name}
                </p>
                <div className="detail-grid">
                  <div className="kv">
                    <span>Branch</span>
                    {detail.branch_name}
                  </div>
                  <div className="kv">
                    <span>Window</span>
                    {formatWhen(detail.start_time)} → {formatWhen(detail.end_time)}
                  </div>
                  <div className="kv">
                    <span>Appointment</span>
                    <StatusBadge value={detail.status} />
                  </div>
                  <div className="kv">
                    <span>PMS sync</span>
                    <StatusBadge value={detail.pms_sync_status} />
                  </div>
                  <div className="kv">
                    <span>Last operation</span>
                    {detail.pms_sync_operation || "—"}
                  </div>
                  <div className="kv">
                    <span>Attempts</span>
                    {detail.pms_sync_attempts}
                  </div>
                </div>
                {detail.pms_last_error ? (
                  <div className="error" style={{ marginTop: 12 }}>
                    {detail.pms_last_error}
                  </div>
                ) : null}
                <div className="actions" style={{ marginTop: 14 }}>
                  <button
                    className="btn btn-primary"
                    type="button"
                    disabled={!canRetry || retrying}
                    onClick={() => void onRetry()}
                  >
                    {retrying ? "Retrying…" : "Retry PMS sync"}
                  </button>
                </div>
              </div>

              <div className="detail-block">
                <h3>PMS event timeline</h3>
                {detail.receipts.length === 0 ? (
                  <p className="muted">No mock-PMS receipts yet.</p>
                ) : (
                  <div className="timeline">
                    {detail.receipts.map((receipt) => (
                      <div className="receipt" key={receipt.id}>
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            gap: 8,
                          }}
                        >
                          <StatusBadge value={receipt.operation} />
                          <span className="muted">
                            {formatWhen(receipt.received_at)}
                          </span>
                        </div>
                        <div className="mono muted" style={{ marginTop: 8 }}>
                          {receipt.idempotency_key}
                        </div>
                        <pre>{JSON.stringify(receipt.payload, null, 2)}</pre>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </aside>
      </div>

      <section className="panel panel-pad" style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0 }}>Recent PMS receipts</h3>
        {recentReceipts.length === 0 ? (
          <p className="muted">No receipts recorded yet.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Operation</th>
                  <th>Appointment</th>
                  <th>Idempotency key</th>
                </tr>
              </thead>
              <tbody>
                {recentReceipts.map((receipt) => (
                  <tr
                    key={receipt.id}
                    onClick={() => void openDetail(receipt.appointment_id)}
                  >
                    <td>{formatWhen(receipt.received_at)}</td>
                    <td>
                      <StatusBadge value={receipt.operation} />
                    </td>
                    <td className="mono">{receipt.appointment_id.slice(0, 8)}…</td>
                    <td className="mono">{receipt.idempotency_key}</td>
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
