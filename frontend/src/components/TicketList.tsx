import { STATUS_LABEL, TICKET_TYPE } from '../agents'
import type { Ticket } from '../types'
import ScoreBadge from './ScoreBadge'

interface Props {
  tickets: Ticket[]
  selectedId: number | null
  onSelect: (id: number) => void
  activeRun: number | null
  loading: boolean
}

export default function TicketList({ tickets, selectedId, onSelect, activeRun, loading }: Props) {
  return (
    <nav className="ticket-rail" aria-label="Tickets">
      <h2 className="rail-title">The board</h2>
      {loading && !tickets.length && <p className="muted">Loading tickets…</p>}
      <ul className="ticket-list">
        {tickets.map((t) => {
          const running = activeRun === t.id
          return (
            <li key={t.id}>
              <button
                type="button"
                className={`ticket-card${t.id === selectedId ? ' selected' : ''}`}
                aria-current={t.id === selectedId ? 'true' : undefined}
                onClick={() => onSelect(t.id)}
              >
                <span className="ticket-top">
                  <span className="ticket-id">#{t.id}</span>
                  <span className="ticket-type">{TICKET_TYPE[t.type] ?? t.type}</span>
                </span>
                <span className="ticket-subject">{t.subject}</span>
                <span className="ticket-requester">{t.requester}</span>
                <span className="ticket-bottom">
                  {running ? (
                    <span className="pill pill-live"><span className="dot" aria-hidden="true" />Agents working</span>
                  ) : (
                    <span className={`pill pill-${t.state === 'resolved' ? 'done' : t.status === 'waiting_approval' ? 'warn' : 'open'}`}>
                      {STATUS_LABEL[t.status] ?? t.status}
                    </span>
                  )}
                  {t.efficiency && <ScoreBadge score={t.efficiency.score} rating={t.efficiency.rating} />}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
