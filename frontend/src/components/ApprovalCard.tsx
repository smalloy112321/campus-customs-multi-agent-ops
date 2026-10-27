import { useState } from 'react'
import { api } from '../api'
import { actorLabel, money } from '../agents'
import type { Cash, PaymentRequest } from '../types'

const KIND: Record<PaymentRequest['kind'], string> = {
  invoice: 'Vendor invoice',
  rent: 'Rent',
  purchase_order: 'Purchase order',
}

interface Props {
  request: PaymentRequest
  cash: Cash | null
  approver: string
  onApproverChange: (name: string) => void
  onDecided: () => Promise<void>
}

export default function ApprovalCard({ request, cash, approver, onApproverChange, onDecided }: Props) {
  const [busy, setBusy] = useState<'approve' | 'reject' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const after = cash ? cash.balance - request.amount : null
  const short = after !== null && after < 0
  const nameId = `approver-${request.id}`

  async function decide(action: 'approve' | 'reject') {
    if (!approver.trim()) {
      setError('Type your name first. Every payment records who approved it.')
      return
    }
    setBusy(action)
    setError(null)
    try {
      await (action === 'approve' ? api.approve(request.id, approver.trim()) : api.reject(request.id, approver.trim()))
      await onDecided()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="approval" aria-labelledby={`ap-${request.id}`}>
      <div className="approval-main">
        <p className="eyebrow eyebrow-gold">Needs your approval</p>
        <h3 id={`ap-${request.id}`} className="approval-title">
          {KIND[request.kind]} · {money(request.amount)} to {request.payee}
        </h3>
        <p className="approval-reason">{request.reason}</p>
        <p className="approval-meta">
          Prepared by {actorLabel(request.requested_by)} · request #{request.id} · from {request.account}
          {after !== null && <> · checking after: <strong className={short ? 'neg' : ''}>{money(after)}</strong></>}
        </p>
        {short && <p className="approval-warn">Not enough cash. The pay step will refuse this, because balances can't go negative.</p>}
      </div>
      <div className="approval-actions">
        <label htmlFor={nameId} className="field-label">Approving as</label>
        <input id={nameId} className="field" value={approver} placeholder="Your name"
          onChange={(e) => onApproverChange(e.target.value)} autoComplete="name" />
        <div className="approval-buttons">
          <button type="button" className="btn btn-gold" onClick={() => decide('approve')} disabled={!!busy}>
            {busy === 'approve' ? 'Paying…' : `Approve ${money(request.amount)}`}
          </button>
          <button type="button" className="btn btn-ghost-dark" onClick={() => decide('reject')} disabled={!!busy}>
            {busy === 'reject' ? 'Rejecting…' : 'Reject'}
          </button>
        </div>
        {error && <p className="approval-error" role="alert">{error}</p>}
      </div>
    </section>
  )
}
