// Thin client for the FastAPI routes in backend/main.py.
import type { AgentEvent, Cash, Efficiency, Health, PaymentRequest, Summary, Ticket } from './types'

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { 'content-type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new ApiError(0, `Can't reach the backend at ${API_BASE}. Is uvicorn running?`)
  }
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(res.status, body?.detail ?? `Request failed (${res.status})`)
  return body as T
}

export const api = {
  health: () => request<Health>('/api/health'),
  tickets: () => request<{ tickets: Ticket[]; active_run: number | null }>('/api/tickets'),
  summary: (id: number) => request<Summary>(`/api/tickets/${id}/summary`),
  efficiency: (id: number) => request<Efficiency>(`/api/tickets/${id}/efficiency`),
  run: (id: number) => request(`/api/tickets/${id}/run`, { method: 'POST' }),
  events: (ticketId: number) => request<{ events: AgentEvent[] }>(`/api/events?ticket_id=${ticketId}&limit=500`),
  approvals: () => request<{ pending: PaymentRequest[] }>('/api/approvals'),
  approve: (id: number, approvedBy: string) =>
    request<{ new_balance: number; ticket_resolved: boolean }>(`/api/approvals/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ approved_by: approvedBy, note: 'Approved on the operations desk' }),
    }),
  reject: (id: number, rejectedBy: string) =>
    request(`/api/approvals/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ approved_by: rejectedBy, note: 'Rejected on the operations desk' }),
    }),
  cash: () => request<Cash>('/api/cash'),
  reset: () => request('/api/reset', { method: 'POST' }),
}
