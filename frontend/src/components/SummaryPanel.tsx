import { actorLabel, AGENTS, money, STATUS_LABEL } from '../agents'
import type { Summary } from '../types'

export default function SummaryPanel({ summary, running }: { summary: Summary | null; running: boolean }) {
  const board = summary?.board
  return (
    <section className="panel" aria-labelledby="sum-h">
      <div className="panel-head"><h3 id="sum-h">What the team did</h3></div>
      {running ? (
        <p className="muted">The summary appears when the Boss makes the call.</p>
      ) : !summary?.ran ? (
        <p className="muted">No run yet.</p>
      ) : (
        <>
          {summary.boss && (
            <blockquote className="boss-call" style={{ '--agent': AGENTS.boss.color } as React.CSSProperties}>
              <span className="boss-label">The Boss’s call · {STATUS_LABEL[summary.boss.final_status] ?? summary.boss.final_status}</span>
              {summary.boss.decision}
            </blockquote>
          )}
          <ul className="reports">
            {summary.reports?.map((r, i) => (
              <li key={i} style={{ '--agent': AGENTS[r.agent].color } as React.CSSProperties}>
                <span className="report-who">{AGENTS[r.agent].label}</span>
                <span className="report-text">{r.summary}</span>
              </li>
            ))}
          </ul>

          {board && (board.payment_requests.length > 0 || board.drafts.length > 0 || board.purchase_orders.length > 0) && (
            <div className="on-board">
              <h4>On the board</h4>
              <ul>
                {board.payment_requests.map((p) => (
                  <li key={`p${p.id}`}>
                    <span className={`pill pill-${p.status === 'approved' ? 'done' : p.status === 'pending' ? 'warn' : 'open'}`}>{p.status}</span>
                    Payment #{p.id}: {money(p.amount)} to {p.payee}
                  </li>
                ))}
                {board.purchase_orders.map((po) => (
                  <li key={`po${po.id}`}><span className="pill pill-open">{po.status}</span>PO #{po.id}: {po.qty} × {po.sku} {po.size}</li>
                ))}
                {board.drafts.map((d) => (
                  <li key={`d${d.id}`}>
                    <details>
                      <summary><span className="pill pill-open">draft · not sent</span>To {d.recipient}: “{d.subject}” <span className="muted">by {actorLabel(d.author)}</span></summary>
                      <p className="draft-body">{d.body}</p>
                    </details>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  )
}
