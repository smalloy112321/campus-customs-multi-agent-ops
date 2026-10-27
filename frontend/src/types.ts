// Shapes returned by the FastAPI backend (backend/main.py).

export type AgentName = 'boss' | 'inventory' | 'accounting' | 'facilities' | 'customer_service'
export type Actor = AgentName | 'system' | 'human'

export interface Efficiency {
  score: number
  rating: 'Efficient' | 'Acceptable' | 'Needs tuning'
  run_id: string
  specialists: AgentName[]
  planned_specialists: AgentName[]
  delegations: string[]
  mcp_tool_calls: number
  model_requests: number
  budget: { delegations: number; toolCalls: number; modelRequests: number }
  missing_required_tools: string[]
  unexpected_tool_calls: string[]
  repeated_calls: number
  penalties: Record<string, number>
  calls_by_agent: Partial<Record<AgentName, number>>
  improvements: { points: number; tip: string }[]
}

export interface RunState {
  ticket_id: number
  state: 'running' | 'done' | 'error'
  started_at: string
  finished_at: string | null
  error: string | null
}

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  sku: string | null
  size: string | null
  qty: number | null
  lease_id: number | null
  invoice_id: number | null
  status: string
  notes: string | null
  created_at: string
  state: 'open' | 'resolved'
  efficiency: Efficiency | null
  run: RunState | null
}

export interface PaymentRequest {
  id: number
  kind: 'invoice' | 'rent' | 'purchase_order'
  ref_id: number
  payee: string
  amount: number
  account: string
  ticket_id: number | null
  requested_by: AgentName
  reason: string
  status: 'pending' | 'approved' | 'rejected'
  created_at: string
}

export interface Cash {
  account: string
  balance: number
  as_of: string
  pending_requests_total: number
  balance_if_all_pending_approved: number
  payments_made: { id: number; kind: string; ref_id: number; amount: number; paid_at: string; approved_by: string }[]
}

export interface AgentEvent {
  index: number
  timestamp: string
  run_id: string
  ticket_id: number | null
  agent: Actor
  parent_agent: AgentName | null
  depth: number
  step: number
  event: string
  model: string | null
  said: string[]
  tool_calls: { tool: string; args: Record<string, unknown> }[]
  tool_results: { tool: string; result: string }[]
  task?: string
  output?: Record<string, unknown>
  detail?: Record<string, unknown>
}

export interface Draft {
  id: number
  audience: string
  recipient: string
  subject: string
  body: string
  author: AgentName
  status: string
}

export interface Board {
  ticket: Ticket
  ticket_updates: { id: number; agent: string; status: string | null; note: string; created_at: string }[]
  drafts: Draft[]
  purchase_orders: { id: number; vendor_id: number; sku: string; size: string; qty: number; total_cost: number; status: string }[]
  payment_requests: PaymentRequest[]
}

export interface Summary {
  ticket_id: number
  ran: boolean
  run_id?: string
  started_at?: string
  finished_at?: string
  boss?: { decision: string; final_status: string; rationale: string; next_steps_for_human: string[]; blockers: string[] } | null
  reports?: { agent: AgentName; parent_agent: AgentName | null; summary: string; recommendation: string; blockers: string[] }[]
  board: Board
}

export interface Health {
  ok: boolean
  model: string
  active_run: number | null
  shop_today: string
}
