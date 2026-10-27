import heroImage from '../assets/hero-yale-fans.jpg'
import type { Ticket } from '../types'

export default function Hero({ tickets, approvalsCount }: { tickets: Ticket[]; approvalsCount: number }) {
  const resolved = tickets.filter((t) => t.state === 'resolved').length
  const open = tickets.length - resolved
  return (
    <section className="hero">
      <img
        className="hero-image"
        src={heroImage}
        alt="Yale fans cheering in the stands, holding a Let's Go Yale banner and a Boola Boola sign"
      />
      <div className="hero-inner">
        <div>
          <p className="eyebrow">Campus Customs · New Haven</p>
          <h2 className="hero-title">Five agents run the shop. You sign off on the money.</h2>
        </div>
        <dl className="hero-stats">
          <div><dt>Open</dt><dd>{open}</dd></div>
          <div><dt>Needs you</dt><dd>{approvalsCount}</dd></div>
          <div><dt>Resolved</dt><dd>{resolved}</dd></div>
        </dl>
      </div>
    </section>
  )
}
