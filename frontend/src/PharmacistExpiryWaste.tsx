import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { API_BASE_URL } from './config'

type WasteReason = 'EXPIRED' | 'DAMAGED' | 'REJECTED_DONATION'
type WasteStatus = 'DISPOSAL_PENDING' | 'COLLECTED' | 'DISPOSED'
type Item = {
  id: string
  medicine_name: string
  strength: string | null
  quantity_available?: number
  quantity?: number
  unit: string
  expiry_date?: string
  days_remaining?: number
  status?: string
  reason?: WasteReason
  notes?: string | null
  disposal_reference?: string
  created_at?: string
  donation_id?: string | null
  inventory_id?: string | null
  collected_at?: string | null
  collected_by?: string | null
  handoff_reference?: string | null
  disposed_at?: string | null
  disposed_by?: string | null
  disposal_notes?: string | null
}

type WasteDraft = { item: Item; source: 'inventory' | 'donation'; quantity: string; reason: WasteReason; notes: string }
type TransitionDraft = { item: Item; action: 'collect' | 'dispose'; confirmed: boolean; reference: string; notes: string }
type ApiError = { detail?: string }

const paths = {
  expiring: '/pharmacist/inventory/expiring',
  expired: '/pharmacist/inventory/expired',
  waste: '/pharmacist/waste',
  rejected: '/pharmacist/donations/rejected-for-disposal',
} as const
type Tab = keyof typeof paths
const tabs: { key: Tab; label: string }[] = [
  { key: 'expiring', label: 'Expiring Soon' },
  { key: 'expired', label: 'Expired Medicines' },
  { key: 'waste', label: 'Waste / Disposal' },
  { key: 'rejected', label: 'Rejected Donations' },
]
const fieldClass = 'mt-1.5 w-full rounded-xl border border-[#dce4d9] bg-white px-3.5 py-2.5 text-sm outline-none transition focus:border-[#719a6c] focus:ring-2 focus:ring-[#719a6c]/15'
const actionClass = 'rounded-full bg-[#174e3f] px-4 py-2 text-xs font-semibold text-white transition hover:bg-[#103d31] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#719a6c] disabled:cursor-not-allowed disabled:opacity-50'
const secondaryClass = 'rounded-full border border-[#dce4d9] px-4 py-2 text-xs font-semibold text-[#31574b] transition hover:bg-[#f5f7f2] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#719a6c] disabled:cursor-not-allowed disabled:opacity-50'
const statusText: Record<WasteStatus, string> = {
  DISPOSAL_PENDING: 'Disposal pending',
  COLLECTED: 'Collected',
  DISPOSED: 'Disposed',
}

function displayDate(value?: string | null): string {
  return value ? new Date(value).toLocaleString() : 'Not recorded'
}

export default function PharmacistExpiryWaste({ token }: { token: string }) {
  const [tab, setTab] = useState<Tab>('expiring')
  const [rows, setRows] = useState<Item[]>([])
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [reload, setReload] = useState(0)
  const [wasteDraft, setWasteDraft] = useState<WasteDraft | null>(null)
  const [transitionDraft, setTransitionDraft] = useState<TransitionDraft | null>(null)
  const [fieldError, setFieldError] = useState('')
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    fetch(`${API_BASE_URL}${paths[tab]}`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => {
        const data = await response.json() as Item[] & ApiError
        if (!response.ok) throw new Error(data.detail ?? 'Could not load waste records.')
        if (active) setRows(data)
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : 'Could not load waste records.')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [tab, reload, token])

  function selectTab(next: Tab) {
    setTab(next)
    setSuccess('')
    setError('')
    setFieldError('')
    setWasteDraft(null)
    setTransitionDraft(null)
  }

  function beginWasteEntry(item: Item, source: WasteDraft['source']) {
    const reason: WasteReason = source === 'donation' ? 'REJECTED_DONATION' : item.status === 'EXPIRED' ? 'EXPIRED' : 'DAMAGED'
    setWasteDraft({ item, source, quantity: '', reason, notes: '' })
    setTransitionDraft(null)
    setFieldError('')
    setError('')
    setSuccess('')
  }

  function beginTransition(item: Item, action: TransitionDraft['action']) {
    setTransitionDraft({ item, action, confirmed: false, reference: '', notes: '' })
    setWasteDraft(null)
    setFieldError('')
    setError('')
    setSuccess('')
  }

  async function submitWaste(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!wasteDraft) return
    const maxQuantity = wasteDraft.item.quantity_available ?? wasteDraft.item.quantity ?? 0
    const quantity = Number(wasteDraft.quantity)
    if (!Number.isInteger(quantity) || quantity <= 0 || quantity > maxQuantity) {
      setFieldError(`Enter a whole quantity from 1 to ${maxQuantity}.`)
      return
    }
    setBusy(true)
    setError('')
    setFieldError('')
    try {
      const endpoint = wasteDraft.source === 'donation'
        ? `/pharmacist/donations/${wasteDraft.item.id}/waste`
        : `/pharmacist/inventory/${wasteDraft.item.id}/waste`
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ reason: wasteDraft.reason, quantity, notes: wasteDraft.notes.trim() || null }),
      })
      const result = await response.json() as Item & ApiError
      if (!response.ok) throw new Error(result.detail ?? 'Could not record this waste.')
      setWasteDraft(null)
      setSuccess(`Waste recorded successfully. Reference ${result.disposal_reference}; status: ${statusText[result.status as WasteStatus] ?? result.status}.`)
      setReload((value) => value + 1)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not record this waste.')
    } finally {
      setBusy(false)
    }
  }

  async function submitTransition(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!transitionDraft) return
    const expected = transitionDraft.action === 'collect' ? 'DISPOSAL_PENDING' : 'COLLECTED'
    if (transitionDraft.item.status !== expected) {
      setError(`This record is ${transitionDraft.item.status?.replaceAll('_', ' ').toLowerCase() ?? 'no longer available'} and cannot be ${transitionDraft.action === 'collect' ? 'collected' : 'marked disposed'} from this state.`)
      return
    }
    if (!transitionDraft.confirmed) {
      setFieldError(transitionDraft.action === 'collect'
        ? 'Confirm that the authorized handoff has taken place.'
        : 'Confirm that disposal has taken place.')
      return
    }
    setBusy(true)
    setError('')
    setFieldError('')
    try {
      const { item, action, reference, notes } = transitionDraft
      const response = await fetch(`${API_BASE_URL}/pharmacist/waste/${item.id}/${action}`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ reference: reference.trim() || null, ...(action === 'dispose' ? { notes: notes.trim() || null } : {}) }),
      })
      const result = await response.json() as Item & ApiError
      if (!response.ok) throw new Error(result.detail ?? `Could not mark this record ${action === 'collect' ? 'collected' : 'disposed'}.`)
      setTransitionDraft(null)
      setSuccess(`Waste record ${action === 'collect' ? 'marked collected' : 'marked disposed'} successfully. Status: ${statusText[result.status as WasteStatus] ?? result.status}.`)
      setReload((value) => value + 1)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not update the disposal status.')
    } finally {
      setBusy(false)
    }
  }

  const startForm = (item: Item) => wasteDraft?.item.id === item.id
  const startTransition = (item: Item) => transitionDraft?.item.id === item.id

  return <section className="mt-8 text-left">
    <div className="mb-4 border-b border-[#edf0ea] pb-4">
      <p className="text-xs font-semibold uppercase tracking-[.12em] text-[#71886d]">Clinic pharmacist</p>
      <h2 className="mt-1 text-xl font-semibold">Expiry &amp; Waste</h2>
      <p className="mt-1 text-sm text-[#718078]">Record eligible stock or rejected donations, then track each waste record through collection and disposal.</p>
    </div>
    <nav aria-label="Expiry and waste sections" className="mb-4 flex flex-wrap gap-2">
      {tabs.map(({ key, label }) => <button key={key} type="button" aria-pressed={tab === key} onClick={() => selectTab(key)} className={`rounded-full px-3 py-2 text-xs font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#719a6c] ${tab === key ? 'bg-[#174e3f] text-white' : 'bg-[#f5f7f2] text-[#52645b]'}`}>{label}</button>)}
    </nav>
    {success && <p role="status" className="mb-4 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{success}</p>}
    {error && <p role="alert" className="mb-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
    {loading && <p role="status" className="mb-4 text-sm text-[#718078]">Loading {tabs.find(({ key }) => key === tab)?.label.toLowerCase()}...</p>}
    {!loading && rows.map((item) => <article key={item.id} className="mb-3 rounded-2xl border border-[#e4e9e0] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="break-words font-semibold">{item.medicine_name}{item.strength ? ` · ${item.strength}` : ''}</h3>
          <p className="mt-1 text-sm text-[#718078]">
            {tab === 'waste' ? `${item.quantity} ${item.unit} recorded` : `${item.quantity_available ?? item.quantity} ${item.unit} available`}
            {item.expiry_date && ` · Expires ${new Date(`${item.expiry_date}T00:00:00`).toLocaleDateString()}`}
          </p>
          {item.days_remaining !== undefined && <p className="mt-1 text-xs text-[#87938a]">{item.days_remaining} days remaining</p>}
          {tab === 'waste' && <>
            <p className="mt-1 text-sm text-[#52645b]">Reason: {item.reason?.replaceAll('_', ' ') ?? 'Not recorded'} · Reference: {item.disposal_reference ?? 'Not recorded'}</p>
            <p className="mt-1 text-xs text-[#718078]">Recorded {displayDate(item.created_at)} · Collected {displayDate(item.collected_at)} · Disposed {displayDate(item.disposed_at)}</p>
            {(item.collected_by || item.disposed_by) && <p className="mt-1 break-all text-xs text-[#718078]">{item.collected_by && `Collected by staff ${item.collected_by}`}{item.collected_by && item.disposed_by ? ' · ' : ''}{item.disposed_by && `Disposed by staff ${item.disposed_by}`}</p>}
            {item.handoff_reference && <p className="mt-1 text-xs text-[#718078]">Handoff / disposal reference: {item.handoff_reference}</p>}
            {item.notes && <p className="mt-1 whitespace-pre-wrap text-sm text-[#52645b]">Notes: {item.notes}</p>}
            {item.disposal_notes && <p className="mt-1 whitespace-pre-wrap text-sm text-[#52645b]">Disposal notes: {item.disposal_notes}</p>}
          </>}
        </div>
        <span className="h-fit rounded-full bg-[#f5f7f2] px-2.5 py-1 text-xs font-semibold text-[#52645b]">
          {tab === 'waste' && item.status
            ? statusText[item.status as WasteStatus] ?? item.status.replaceAll('_', ' ')
            : item.status?.replaceAll('_', ' ') ?? (tab === 'expiring' ? 'EXPIRING' : 'REJECTED')}
        </span>
      </div>

      {tab === 'expired' && <div className="mt-3">
        {startForm(item) ? <WasteEntryForm draft={wasteDraft!} busy={busy} fieldError={fieldError} onChange={setWasteDraft} onCancel={() => { setWasteDraft(null); setFieldError('') }} onSubmit={submitWaste} />
          : <button type="button" disabled={busy} onClick={() => beginWasteEntry(item, 'inventory')} className={actionClass}>Record Waste</button>}
      </div>}
      {tab === 'rejected' && <div className="mt-3">
        {startForm(item) ? <WasteEntryForm draft={wasteDraft!} busy={busy} fieldError={fieldError} onChange={setWasteDraft} onCancel={() => { setWasteDraft(null); setFieldError('') }} onSubmit={submitWaste} />
          : <button type="button" disabled={busy} onClick={() => beginWasteEntry(item, 'donation')} className={actionClass}>Record for Disposal</button>}
      </div>}
      {tab === 'waste' && item.status === 'DISPOSAL_PENDING' && <div className="mt-3">
        {startTransition(item) ? <WasteTransitionForm draft={transitionDraft!} busy={busy} fieldError={fieldError} onChange={setTransitionDraft} onCancel={() => { setTransitionDraft(null); setFieldError('') }} onSubmit={submitTransition} />
          : <button type="button" disabled={busy} onClick={() => beginTransition(item, 'collect')} className={actionClass}>Mark Collected</button>}
      </div>}
      {tab === 'waste' && item.status === 'COLLECTED' && <div className="mt-3">
        {startTransition(item) ? <WasteTransitionForm draft={transitionDraft!} busy={busy} fieldError={fieldError} onChange={setTransitionDraft} onCancel={() => { setTransitionDraft(null); setFieldError('') }} onSubmit={submitTransition} />
          : <button type="button" disabled={busy} onClick={() => beginTransition(item, 'dispose')} className={actionClass}>Mark Disposed</button>}
      </div>}
    </article>)}
    {!loading && !error && !rows.length && <p className="rounded-2xl border border-dashed border-[#dce4d9] px-5 py-8 text-center text-sm text-[#718078]">No records in this section.</p>}
  </section>
}

function WasteEntryForm({ draft, busy, fieldError, onChange, onCancel, onSubmit }: {
  draft: WasteDraft
  busy: boolean
  fieldError: string
  onChange: (draft: WasteDraft | null) => void
  onCancel: () => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
}) {
  const maxQuantity = draft.item.quantity_available ?? draft.item.quantity ?? 0
  return <form onSubmit={onSubmit} className="space-y-3 rounded-xl bg-[#f7f8f5] p-4">
    <h4 className="font-semibold">Record waste</h4>
    <label className="block text-sm font-medium">Quantity * <span className="text-red-700">Required</span>
      <input className={fieldClass} type="number" min="1" max={maxQuantity} step="1" required value={draft.quantity} onChange={(event) => onChange({ ...draft, quantity: event.target.value })} />
      <span className="mt-1 block text-xs text-[#718078]">Whole units only; no more than {maxQuantity} {draft.item.unit}.</span>
    </label>
    <label className="block text-sm font-medium">Reason * <span className="text-red-700">Required</span>
      {draft.source === 'donation'
        ? <span className={`${fieldClass} block bg-[#f0f2ee]`}>Rejected donation</span>
        : <select className={fieldClass} required value={draft.reason} onChange={(event) => onChange({ ...draft, reason: event.target.value as WasteReason })}>
          <option value="EXPIRED">Expired</option>
          <option value="DAMAGED">Damaged</option>
        </select>}
    </label>
    <label className="block text-sm font-medium">Notes (Optional)
      <textarea className={`${fieldClass} min-h-20 resize-y`} maxLength={2000} value={draft.notes} onChange={(event) => onChange({ ...draft, notes: event.target.value })} placeholder="Additional waste record notes" />
    </label>
    {fieldError && <p role="alert" className="text-sm text-red-700">{fieldError}</p>}
    <div className="flex flex-wrap gap-2">
      <button type="submit" disabled={busy || maxQuantity < 1} className={actionClass}>{busy ? 'Recording...' : 'Submit Waste Record'}</button>
      <button type="button" disabled={busy} onClick={onCancel} className={secondaryClass}>Cancel</button>
    </div>
  </form>
}

function WasteTransitionForm({ draft, busy, fieldError, onChange, onCancel, onSubmit }: {
  draft: TransitionDraft
  busy: boolean
  fieldError: string
  onChange: (draft: TransitionDraft | null) => void
  onCancel: () => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
}) {
  const collecting = draft.action === 'collect'
  return <form onSubmit={onSubmit} className="space-y-3 rounded-xl bg-[#f7f8f5] p-4">
    <h4 className="font-semibold">{collecting ? 'Confirm waste handoff' : 'Confirm disposal'}</h4>
    <p className="text-sm text-[#718078]">{collecting ? 'Mark this record collected after the authorized handoff has taken place.' : 'Mark this record disposed after disposal has taken place.'}</p>
    <label className="block text-sm font-medium">{collecting ? 'Handoff reference' : 'Disposal reference'} (Optional)
      <input className={fieldClass} maxLength={120} value={draft.reference} onChange={(event) => onChange({ ...draft, reference: event.target.value })} placeholder={collecting ? 'Handoff reference' : 'Disposal reference'} />
    </label>
    {!collecting && <label className="block text-sm font-medium">Disposal notes (Optional)
      <textarea className={`${fieldClass} min-h-20 resize-y`} maxLength={2000} value={draft.notes} onChange={(event) => onChange({ ...draft, notes: event.target.value })} placeholder="Notes about this recorded disposal" />
    </label>}
    <label className="flex items-start gap-2 text-sm text-[#31574b]">
      <input type="checkbox" className="mt-1" checked={draft.confirmed} onChange={(event) => onChange({ ...draft, confirmed: event.target.checked })} />
      <span>{collecting ? 'The authorized handoff has taken place. * Required' : 'Disposal has taken place. * Required'}</span>
    </label>
    {fieldError && <p role="alert" className="text-sm text-red-700">{fieldError}</p>}
    <div className="flex flex-wrap gap-2">
      <button type="submit" disabled={busy} className={actionClass}>{busy ? 'Saving...' : collecting ? 'Confirm Collection' : 'Confirm Disposal'}</button>
      <button type="button" disabled={busy} onClick={onCancel} className={secondaryClass}>Cancel</button>
    </div>
  </form>
}
