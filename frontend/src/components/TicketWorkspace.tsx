import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { agentStatuses, latestRun, STATUS_LABEL, TICKET_TYPE } from '../agents'
import type { AgentEvent, Cash, Efficiency, PaymentRequest, Summary, Ticket } from '../types'
import ActivityFeed from './ActivityFeed'
import AgentRoster from './AgentRoster'
import ApprovalCard from './ApprovalCard'
import EfficiencyPanel from './EfficiencyPanel'
import SummaryPanel from './SummaryPanel'

interface Props {
  ticket: Ticket
  activeRun: number | null
  approvals: PaymentRequest[]
  cash: Cash | null
  approver: string
  onApproverChange: (name: string) => void
  onChanged: () => Promise<void>
}

export default function TicketWorkspace({ ticket, activeRun, approvals, cash, approver, onApproverChange, onChanged }: Props) {
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [summary, setSummary] = useState<Summary | null>(null)
  const [efficiency, setEfficiency] = useState<Efficiency | null>(null)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const running = activeRun === ticket.id
  const otherRunning = activeRun !== null && !running
  const resolved = ticket.state === 'resolved'

  const loadEvents = useCallback(async () => {
    try {
      setEvents(latestRun((await api.events(ticket.id)).events))
    } catch (e) {
      setError((e as Error).message)
    }
  }, [ticket.id])

  const loadResults = useCallback(async () => {
    try {
      setSummary(await api.summary(ticket.id))
    } catch (e) {
      setError((e as Error).message)
    }
    // 404 just means this ticket hasn't been run yet.
    setEfficiency(await api.efficiency(ticket.id).catch(() => null))
  }, [ticket.id])

  // Poll the feed fast while this ticket runs; load everything once when it settles.
  useEffect(() => {
    loadEvents()
    if (!running) {
      loadResults()
      return
    }
    const timer = setInterval(loadEvents, 1200)
    return () => clearInterval(timer)
  }, [running, loadEvents, loadResults, ticket.status])

  // When a run on this ticket ends, refresh the whole board once.
  const wasRunning = useRef(running)
  useEffect(() => {
    if (wasRunning.current && !running) onChanged()
    wasRunning.current = running
  }, [running, onChanged])

  async function start() {
    setStarting(true)
    setError(null)
    try {
      await api.run(ticket.id)
      await onChanged()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setStarting(false)
    }
  }

  async function afterDecision() {
    await onChanged()
    await loadResults()
  }

  const statuses = useMemo(() => agentStatuses(events), [events])
  const runError = ticket.run?.state === 'error' ? ticket.run.error : null

  return (
    <article className="ticket-workspace">
      <header className="ws-header">
        <div>
          <p className="eyebrow eyebrow-dark">
            Ticket #{ticket.id} · {TICKET_TYPE[ticket.type] ?? ticket.type}
          </p>
          <h2 className="ws-title">{ticket.subject}</h2>
          <p className="ws-meta">
            From <strong>{ticket.requester}</strong>
            {ticket.sku && <> · {ticket.sku}{ticket.size ? `, size ${ticket.size}` : ''}{ticket.qty ? ` × ${ticket.qty}` : ''}</>}
            {ticket.notes && <> · “{ticket.notes}”</>}
          </p>
        </div>
        <div className="ws-actions">
          <span className={`pill pill-lg pill-${resolved ? 'done' : running ? 'live' : ticket.status === 'waiting_approval' ? 'warn' : 'open'}`}>
            {running ? <><span className="dot" aria-hidden="true" />Agents working</> : STATUS_LABEL[ticket.status] ?? ticket.status}
          </span>
          {!resolved && (
            <button
              type="button"
              className="btn btn-primary"
              onClick={start}
              disabled={running || otherRunning || starting || approvals.length > 0}
              title={
                otherRunning ? `Ticket ${activeRun} is running; runs go one at a time`
                  : approvals.length ? 'Approve or reject the pending payment first' : undefined
              }
            >
              {running || starting ? 'Running…' : events.length ? 'Run agents again' : 'Run agent team'}
            </button>
          )}
        </div>
      </header>

      {(error || runError) && <div className="banner banner-error" role="alert">{error ?? `The run stopped: ${runError}`}</div>}

      <AgentRoster statuses={statuses} hasRun={events.length > 0} />

      {approvals.map((req) => (
        <ApprovalCard key={req.id} request={req} cash={cash} approver={approver}
          onApproverChange={onApproverChange} onDecided={afterDecision} />
      ))}

      <div className="ws-grid">
        <ActivityFeed events={events} running={running} />
        <div className="ws-side">
          <SummaryPanel summary={summary} running={running} />
          <EfficiencyPanel efficiency={running ? null : efficiency} running={running} resolved={resolved} />
        </div>
      </div>
    </article>
  )
}
