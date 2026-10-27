import { money, shopDate } from '../agents'
import type { Cash, Health } from '../types'
import Logo from './Logo'

interface Props {
  cash: Cash | null
  health: Health | null
  approvalsCount: number
  onReset: () => void
  resetDisabled: boolean
}

export default function Header({ cash, health, approvalsCount, onReset, resetDisabled }: Props) {
  return (
    <header className="site-header">
      <div className="announce">
        Operations desk · Shop date {health ? shopDate(health.shop_today) : '…'} · Agents run on {health?.model ?? 'gpt-6-luna'}
      </div>
      <div className="header-inner">
        <div className="brand">
          <Logo className="brand-logo" />
          <div>
            <p className="eyebrow eyebrow-dark">Multi-agent operations</p>
            <h1 className="brand-title">Operations Desk</h1>
          </div>
        </div>

        <div className="header-actions">
          <div className="cash-card" aria-live="polite">
            <span className="cash-label">Checking balance</span>
            <span className="cash-amount">{cash ? money(cash.balance) : '…'}</span>
            {cash && (
              <span className="cash-sub">
                {cash.pending_requests_total > 0
                  ? `${money(cash.pending_requests_total)} waiting for approval · ${money(cash.balance_if_all_pending_approved)} after`
                  : 'Nothing waiting for approval'}
              </span>
            )}
          </div>
          {approvalsCount > 0 && (
            <span className="approval-badge" title="Payments waiting for you">
              {approvalsCount} to approve
            </span>
          )}
          <button type="button" className="btn btn-ghost-dark" onClick={onReset} disabled={resetDisabled}
            title={resetDisabled ? 'Wait for the current run to finish' : 'Put the database back to the original values'}>
            Reset shop
          </button>
        </div>
      </div>
    </header>
  )
}
