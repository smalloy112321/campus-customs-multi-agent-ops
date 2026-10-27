import type { Actor, AgentEvent, AgentName } from './types'

// Each agent gets a name, a role line, initials and a color so you can follow them in the feed.
export const AGENTS: Record<AgentName, { label: string; role: string; initials: string; color: string }> = {
  boss: { label: 'The Boss', role: 'Routes the ticket, makes the final call', initials: 'B', color: '#00356b' },
  inventory: { label: 'Inventory', role: 'Stock by SKU and size, restock vendor', initials: 'IN', color: '#1f6f78' },
  accounting: { label: 'Accounting', role: 'Cash, invoices, margins, payment requests', initials: 'AC', color: '#2e6b3a' },
  facilities: { label: 'Facilities', role: 'Lease, rent, landlord', initials: 'FA', color: '#8a5a12' },
  customer_service: { label: 'Customer Service', role: 'Drafts customer replies', initials: 'CS', color: '#6b3fa0' },
}
export const AGENT_ORDER: AgentName[] = ['boss', 'inventory', 'accounting', 'facilities', 'customer_service']

export function actorLabel(a: Actor | null | undefined): string {
  if (!a) return ''
  if (a === 'human') return 'You'
  if (a === 'system') return 'Desk'
  return AGENTS[a].label
}

export const TICKET_TYPE: Record<string, string> = {
  customer_order: 'Customer order',
  rent_notice: 'Rent notice',
  price_override: 'Price request',
}

export const STATUS_LABEL: Record<string, string> = {
  open: 'Open',
  in_progress: 'In progress',
  waiting_approval: 'Needs your approval',
  waiting_vendor: 'Waiting on vendor',
  resolved: 'Resolved',
  declined: 'Declined',
}

// Plain-English names for MCP tools, so the feed reads like a story rather than a log.
export const TOOL_LABEL: Record<string, string> = {
  get_shop_today: 'checked the shop date',
  get_ticket: 'read the ticket',
  list_open_tickets: 'listed open tickets',
  check_stock: 'counted stock',
  check_availability: 'checked availability',
  check_pricing: 'checked pricing',
  check_vendor_status: 'checked the vendor',
  check_rent_due: 'checked the lease',
  check_cash: 'checked cash',
  list_pending_approvals: 'checked pending approvals',
  update_ticket: 'updated the ticket',
  save_draft: 'saved a draft',
  create_purchase_order: 'drafted a purchase order',
  request_payment: 'requested a payment',
  delegate: 'delegated',
}

export const money = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: n % 1 ? 2 : 0 })

export function shopDate(iso: string | undefined): string {
  if (!iso) return ''
  return new Date(`${iso}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

/** Events belonging to the most recent agent run on a ticket. */
export function latestRun(events: AgentEvent[]): AgentEvent[] {
  const starts = events.filter((e) => e.event === 'run_start' && e.depth === 0 && e.run_id.startsWith('ticket-'))
  if (!starts.length) return []
  const runId = starts[starts.length - 1].run_id
  return events.filter((e) => e.run_id === runId)
}

export type AgentStatus = 'idle' | 'working' | 'done'

/** Who has been called in this run, and who is still working. */
export function agentStatuses(run: AgentEvent[]): Record<AgentName, AgentStatus> {
  const status = Object.fromEntries(AGENT_ORDER.map((a) => [a, 'idle'])) as Record<AgentName, AgentStatus>
  const open: Partial<Record<AgentName, number>> = {}
  for (const e of run) {
    if (!(e.agent in AGENTS)) continue
    const a = e.agent as AgentName
    if (e.event === 'run_start') open[a] = (open[a] ?? 0) + 1
    if (e.event === 'run_end' || e.event === 'error') open[a] = (open[a] ?? 1) - 1
    status[a] = (open[a] ?? 0) > 0 ? 'working' : 'done'
  }
  return status
}
