import { useEffect, useState } from 'react'
import { API_BASE_URL } from './config'
import { safeApiErrorMessage } from './apiErrors.mjs'

type ClinicVerification = {
  id: string
  clinic_name: string
  address: string
  city: string
  license_number: string | null
  contact_number: string | null
  created_at: string
  verification_status: 'PENDING' | 'VERIFIED' | 'REJECTED'
  verification_decided_at: string | null
  reviewer_name: string | null
  verification_rejection_reason: string | null
}

type ClinicTab = 'Pending' | 'Approved' | 'Rejected'

const buttonClass = 'rounded-full px-4 py-2.5 text-sm font-semibold disabled:opacity-50'

export default function AdminClinicVerification({ token }: { token: string }) {
  const [clinics, setClinics] = useState<ClinicVerification[]>([])
  const [tab, setTab] = useState<ClinicTab>('Pending')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busyId, setBusyId] = useState<string | null>(null)
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [refreshVersion, setRefreshVersion] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    const status = tab === 'Approved' ? 'VERIFIED' : tab.toUpperCase()
    const endpoint = `${API_BASE_URL}/admin/clinic-verifications/history?status=${status}`
    fetch(endpoint, {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    }).then(async (response) => {
      const body = await response.json() as ClinicVerification[] & { detail?: string }
      if (!response.ok) throw new Error(safeApiErrorMessage(body, 'Could not load pending clinic reviews.'))
      setClinics(body)
    }).catch((cause: unknown) => {
      if (cause instanceof Error && cause.name !== 'AbortError') {
        setError(cause.message || 'Could not load pending clinic reviews.')
      }
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false)
    })
    return () => controller.abort()
  }, [token, refreshVersion, tab])

  async function decide(clinic: ClinicVerification, decision: 'approve' | 'reject') {
    const reason = reasons[clinic.id]?.trim() ?? ''
    if (decision === 'reject' && !reason) {
      setError('Enter a reason before rejecting this clinic.')
      return
    }
    setBusyId(clinic.id)
    setError('')
    setMessage('')
    try {
      const response = await fetch(`${API_BASE_URL}/admin/clinic-verifications/${clinic.id}/${decision}`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          ...(decision === 'reject' ? { 'Content-Type': 'application/json' } : {}),
        },
        ...(decision === 'reject' ? { body: JSON.stringify({ reason }) } : {}),
      })
      const body = await response.json() as { detail?: string }
      if (!response.ok) throw new Error(safeApiErrorMessage(body, `Could not ${decision} this clinic.`))
      setClinics((current) => current.filter((item) => item.id !== clinic.id))
      setMessage(`${clinic.clinic_name} marked ${decision === 'approve' ? 'verified' : 'rejected'}.`)
      setReasons((current) => {
        const next = { ...current }
        delete next[clinic.id]
        return next
      })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : `Could not ${decision} this clinic.`)
    } finally {
      setBusyId(null)
    }
  }

  return <section className="mt-6">
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Clinic verification</h1>
        <p className="mt-1 text-sm text-[#718078]">Current status and latest decision details. This is not a complete audit history.</p>
      </div>
      <button onClick={() => setRefreshVersion((version) => version + 1)} disabled={loading} className={`${buttonClass} border border-[#dce4d9] text-[#55704f]`}>Refresh</button>
    </div>
    <nav aria-label="Clinic verification status" className="mb-4 flex flex-wrap gap-2">{(['Pending', 'Approved', 'Rejected'] as const).map((item) => <button key={item} type="button" aria-pressed={tab === item} onClick={() => setTab(item)} className={`${buttonClass} ${tab === item ? 'bg-[#174e3f] text-white' : 'border border-[#dce4d9] text-[#55704f]'}`}>{item}</button>)}</nav>
    {error && <p role="alert" className="mb-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
    {message && <p role="status" className="mb-4 rounded-xl bg-[#edf5e9] px-4 py-3 text-sm text-[#416b43]">{message}</p>}
    {loading ? <p className="py-10 text-center text-sm text-[#718078]">Loading pending clinics…</p> : clinics.length === 0 ? (
      <p className="rounded-2xl border border-dashed border-[#dce4d9] px-5 py-10 text-center text-sm text-[#718078]">No clinics are waiting for review.</p>
    ) : <div className="grid gap-4 lg:grid-cols-2">
      {clinics.map((clinic) => <article key={clinic.id} className="rounded-2xl border border-[#e4e9e0] bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h2 className="text-lg font-semibold">{clinic.clinic_name}</h2>
          <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${clinic.verification_status === 'PENDING' ? 'bg-amber-50 text-amber-800' : clinic.verification_status === 'VERIFIED' ? 'bg-emerald-50 text-emerald-800' : 'bg-red-50 text-red-800'}`}>{clinic.verification_status === 'VERIFIED' ? 'Approved' : clinic.verification_status === 'REJECTED' ? 'Rejected' : 'Pending'}</span>
        </div>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          <div><dt className="text-xs font-semibold text-[#718078]">Address</dt><dd className="mt-1">{clinic.address}</dd></div>
          <div><dt className="text-xs font-semibold text-[#718078]">City</dt><dd className="mt-1">{clinic.city}</dd></div>
          <div><dt className="text-xs font-semibold text-[#718078]">License number</dt><dd className="mt-1">{clinic.license_number || 'Not provided'}</dd></div>
          <div><dt className="text-xs font-semibold text-[#718078]">Clinic contact</dt><dd className="mt-1">{clinic.contact_number || 'Not provided'}</dd></div>
        </dl>
        <p className="mt-3 text-xs text-[#87938a]">Submitted {new Date(clinic.created_at).toLocaleDateString()}</p>
        {clinic.verification_status !== 'PENDING' && <div className="mt-4 rounded-xl bg-[#f7f8f5] p-3 text-sm"><p className="font-semibold">Latest decision details</p><p className="mt-1 text-xs text-[#718078]">Decided {clinic.verification_decided_at ? new Date(clinic.verification_decided_at).toLocaleString() : 'date unavailable'} · Reviewer: {clinic.reviewer_name || 'Unavailable'}</p>{clinic.verification_status === 'REJECTED' && clinic.verification_rejection_reason && <p className="mt-2 whitespace-pre-wrap">Reason: {clinic.verification_rejection_reason}</p>}</div>}
        {clinic.verification_status === 'PENDING' && <div className="mt-5 flex flex-wrap items-end gap-3">
          <button onClick={() => void decide(clinic, 'approve')} disabled={busyId !== null} className={`${buttonClass} bg-[#174e3f] text-white hover:bg-[#103d31]`}>
            {busyId === clinic.id ? 'Saving…' : 'Approve clinic'}
          </button>
          <label className="min-w-56 flex-1 text-xs font-semibold text-[#55704f]">Rejection reason
            <textarea value={reasons[clinic.id] ?? ''} onChange={(event) => setReasons((current) => ({ ...current, [clinic.id]: event.target.value }))} maxLength={1000} rows={2} className="mt-1.5 w-full rounded-xl border border-[#dce4d9] bg-white px-3 py-2 text-sm font-normal text-[#18372e] outline-none focus:border-[#719a6c] focus:ring-2 focus:ring-[#719a6c]/15" placeholder="Required to reject" />
          </label>
          <button onClick={() => void decide(clinic, 'reject')} disabled={busyId !== null || !(reasons[clinic.id] ?? '').trim()} className={`${buttonClass} border border-red-200 text-red-700 hover:bg-red-50`}>
            {busyId === clinic.id ? 'Saving…' : 'Reject clinic'}
          </button>
        </div>}
      </article>)}
    </div>}
  </section>
}
