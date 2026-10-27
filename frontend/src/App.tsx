import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import type { Cash, Health, PaymentRequest, Ticket } from './types'
import Header from './components/Header'
import Hero from './components/Hero'
import TicketList from './components/TicketList'
import TicketWorkspace from './components/TicketWorkspace'

const IDLE_POLL_MS = 5000
const RUNNING_POLL_MS = 1500

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [cash, setCash] = useState<Cash | null>(null)
  const [approvals, setApprovals] = useState<PaymentRequest[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [approver, setApprover] = useState(() => localStorage.getItem('approver') ?? '')

  const refresh = useCallback(async () => {
    try {
      const [t, c, a, h] = await Promise.all([api.tickets(), api.cash(), api.approvals(), api.health()])
      setTickets(t.tickets)
      setCash(c)
      setApprovals(a.pending)
      setHealth(h)
      setError(null)
      setSelectedId((id) => id ?? t.tickets[0]?.id ?? null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoaded(true)
    }
  }, [])

  const activeRun = health?.active_run ?? null
  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, activeRun ? RUNNING_POLL_MS : IDLE_POLL_MS)
    return () => clearInterval(timer)
  }, [refresh, activeRun])

  useEffect(() => localStorage.setItem('approver', approver), [approver])

  const selected = useMemo(() => tickets.find((t) => t.id === selectedId) ?? null, [tickets, selectedId])

  async function reset() {
    if (!confirm('Reset the shop database to its original values? Tickets, cash and drafts go back to the start. The audit trail is kept.')) return
    try {
      await api.reset()
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div className="app">
      <a className="skip-link" href="#workspace">Skip to the ticket workspace</a>
      <Header cash={cash} health={health} approvalsCount={approvals.length} onReset={reset} resetDisabled={!!activeRun} />
      <Hero tickets={tickets} approvalsCount={approvals.length} />

      {error && (
        <div className="banner banner-error" role="alert">
          <strong>Backend problem.</strong> {error}
        </div>
      )}

      <main className="desk">
        <TicketList tickets={tickets} selectedId={selectedId} onSelect={setSelectedId} activeRun={activeRun} loading={!loaded} />
        <section id="workspace" className="workspace" aria-live="polite">
          {selected ? (
            <TicketWorkspace
              key={selected.id}
              ticket={selected}
              activeRun={activeRun}
              approvals={approvals.filter((a) => a.ticket_id === selected.id)}
              cash={cash}
              approver={approver}
              onApproverChange={setApprover}
              onChanged={refresh}
              offline={!!error}
            />
          ) : (
            <div className="empty-state">{loaded ? 'No tickets on the board.' : 'Loading the board…'}</div>
          )}
        </section>
      </main>

      <footer className="footer">
        Campus Customs Operations Desk · every agent runs on {health?.model ?? 'gpt-6-luna'} via Portkey · drafts are never sent ·
        payments move only when you approve
      </footer>
    </div>
  )
}
