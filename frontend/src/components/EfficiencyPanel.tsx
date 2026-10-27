import { AGENTS } from '../agents'
import type { Efficiency } from '../types'
import { ratingClass } from './ScoreBadge'

function Gauge({ score, rating }: { score: number; rating: string }) {
  const r = 42
  const c = 2 * Math.PI * r
  return (
    <svg className={`gauge gauge-${ratingClass(rating)}`} viewBox="0 0 100 100" role="img" aria-label={`Efficiency ${score} out of 100`}>
      <circle cx="50" cy="50" r={r} className="gauge-track" />
      <circle cx="50" cy="50" r={r} className="gauge-fill" strokeDasharray={`${(score / 100) * c} ${c}`} transform="rotate(-90 50 50)" />
      <text x="50" y="53" textAnchor="middle" className="gauge-num">{score}</text>
      <text x="50" y="68" textAnchor="middle" className="gauge-of">/ 100</text>
    </svg>
  )
}

function Meter({ label, value, budget }: { label: string; value: number; budget: number }) {
  const over = value > budget
  return (
    <div className="meter">
      <span className="meter-label">{label}</span>
      <span className={`meter-value${over ? ' over' : ''}`}>{value} <span className="muted">/ {budget}</span></span>
      <span className="meter-bar"><span style={{ width: `${Math.min(100, (value / Math.max(budget, value)) * 100)}%` }} className={over ? 'over' : ''} /></span>
    </div>
  )
}

export default function EfficiencyPanel({ efficiency: e, running, resolved }: { efficiency: Efficiency | null; running: boolean; resolved: boolean }) {
  return (
    <section className="panel" aria-labelledby="eff-h">
      <div className="panel-head">
        <h3 id="eff-h">Efficiency</h3>
        {e && !resolved && <span className="muted small">Final once the ticket resolves</span>}
      </div>
      {running || !e ? (
        <p className="muted">{running ? 'Scored when the run finishes.' : 'Run the team to score it against the plan.'}</p>
      ) : (
        <>
          <div className="eff-top">
            <Gauge score={e.score} rating={e.rating} />
            <div>
              <span className={`rating rating-${ratingClass(e.rating)}`}>{e.rating}</span>
              <p className="small">
                Specialists used:{' '}
                {e.specialists.map((a) => (
                  <span key={a} className="mini-agent" style={{ '--agent': AGENTS[a].color } as React.CSSProperties}>{AGENTS[a].label}</span>
                ))}
              </p>
              <p className="small muted">Plan called for {e.planned_specialists.length} · {e.delegations.map((d) => d.split(' -> ').map((a) => AGENTS[a as keyof typeof AGENTS]?.label ?? a).join(' → ')).join(' · ')}</p>
            </div>
          </div>
          <Meter label="Delegations" value={e.delegations.length} budget={e.budget.delegations} />
          <Meter label="MCP tool calls" value={e.mcp_tool_calls} budget={e.budget.toolCalls} />
          <Meter label="Model requests" value={e.model_requests} budget={e.budget.modelRequests} />

          <h4 className="improve-h">How to do better next time</h4>
          <ul className="improve">
            {e.improvements.map((t, i) => (
              <li key={i}>
                {t.points > 0 && <span className="improve-pts">+{t.points}</span>}
                <span>{t.tip}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
