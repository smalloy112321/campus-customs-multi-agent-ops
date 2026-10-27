import { AGENT_ORDER, AGENTS, type AgentStatus } from '../agents'
import type { AgentName } from '../types'

const STATE_TEXT: Record<AgentStatus, string> = { idle: 'Not called', working: 'Working…', done: 'Reported back' }

export default function AgentRoster({ statuses, hasRun }: { statuses: Record<AgentName, AgentStatus>; hasRun: boolean }) {
  return (
    <ul className="roster" aria-label="Agent team">
      {AGENT_ORDER.map((a) => {
        const s = statuses[a]
        return (
          <li key={a} className={`roster-item roster-${s}`} style={{ '--agent': AGENTS[a].color } as React.CSSProperties}>
            <span className="avatar" aria-hidden="true">{AGENTS[a].initials}</span>
            <span className="roster-text">
              <span className="roster-name">{AGENTS[a].label}</span>
              <span className="roster-state">{hasRun ? STATE_TEXT[s] : AGENTS[a].role}</span>
            </span>
          </li>
        )
      })}
    </ul>
  )
}
