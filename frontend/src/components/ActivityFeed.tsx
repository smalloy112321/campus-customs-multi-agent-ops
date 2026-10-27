import { useEffect, useRef } from 'react'
import { actorLabel, AGENTS, TOOL_LABEL } from '../agents'
import type { AgentEvent, AgentName } from '../types'

function color(agent: string) {
  return agent in AGENTS ? AGENTS[agent as AgentName].color : '#55606e'
}

function time(ts: string) {
  return new Date(ts).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', second: '2-digit' })
}

function describeCall(c: { tool: string; args: Record<string, unknown> }) {
  if (c.tool === 'delegate') return `asked ${actorLabel(c.args.to as AgentName)}`
  return TOOL_LABEL[c.tool] ?? c.tool
}

/** Turn one audit event into a feed line, or null for steps that add nothing for a human. */
function Line({ e }: { e: AgentEvent }) {
  const who = actorLabel(e.agent)
  let title: React.ReactNode = null
  let body: React.ReactNode = null

  if (e.event === 'run_start') {
    title = e.parent_agent ? <><b>{actorLabel(e.parent_agent)}</b> handed work to <b>{who}</b></> : <><b>{who}</b> picked up the ticket</>
    body = e.parent_agent && e.task ? <p className="feed-task">{e.task}</p> : null
  } else if (e.event === 'model_response' && (e.tool_calls.length || e.said.length)) {
    title = <><b>{who}</b> {e.tool_calls.map(describeCall).join(', ') || 'said'}</>
    body = (
      <>
        {e.tool_calls.length > 0 && (
          <ul className="chips">
            {e.tool_calls.map((c, i) => (
              <li key={i} className={`chip${c.tool === 'delegate' ? ' chip-delegate' : ''}`}>
                <code>{c.tool === 'delegate' ? `delegate → ${c.args.to}` : c.tool}</code>
              </li>
            ))}
          </ul>
        )}
        {e.said.map((s, i) => <p key={i} className="feed-said">{s}</p>)}
      </>
    )
  } else if (e.event === 'model_request' && e.tool_results.some((r) => r.tool !== 'delegate')) {
    const results = e.tool_results.filter((r) => r.tool !== 'delegate')
    return (
      <li className="feed-item feed-result" style={{ marginLeft: e.depth * 22 }}>
        <details>
          <summary>{results.length === 1 ? `${results[0].tool} answered` : `${results.length} tools answered`}</summary>
          {results.map((r, i) => <pre key={i}><b>{r.tool}</b> {r.result}</pre>)}
        </details>
      </li>
    )
  } else if (e.event === 'run_end') {
    title = <><b>{who}</b> {e.parent_agent ? `reported back to ${actorLabel(e.parent_agent)}` : 'made the call'}</>
    body = e.said[0] ? <p className="feed-said feed-report">{e.said[0]}</p> : null
  } else if (e.event === 'delegation_refused' || e.event === 'error') {
    title = <><b>{who}</b> {e.event === 'error' ? 'hit an error' : 'had a delegation refused'}</>
    body = <p className="feed-said">{String(e.detail?.reason ?? e.detail?.error ?? '')}</p>
  } else {
    return null
  }

  return (
    <li className={`feed-item feed-${e.event}`} style={{ marginLeft: e.depth * 22, '--agent': color(e.agent) } as React.CSSProperties}>
      <span className="feed-dot" aria-hidden="true" />
      <div className="feed-content">
        <div className="feed-title"><span>{title}</span><time>{time(e.timestamp)}</time></div>
        {body}
      </div>
    </li>
  )
}

export default function ActivityFeed({ events, running }: { events: AgentEvent[]; running: boolean }) {
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (running) end.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [events.length, running])

  return (
    <section className="panel feed-panel" aria-labelledby="feed-h">
      <div className="panel-head">
        <h3 id="feed-h">Agent activity</h3>
        {running && <span className="pill pill-live"><span className="dot" aria-hidden="true" />Live</span>}
      </div>
      {events.length === 0 ? (
        <p className="muted">
          {running ? 'Waiting for the Boss to pick up the ticket…' : 'No run yet. Start the agent team to watch each agent think, call tools and hand off work here.'}
        </p>
      ) : (
        <ol className="feed">
          {events.map((e) => <Line key={e.index} e={e} />)}
          {running && <li className="feed-item feed-typing"><span className="typing" aria-label="Agents working"><i /><i /><i /></span></li>}
        </ol>
      )}
      <div ref={end} />
    </section>
  )
}
