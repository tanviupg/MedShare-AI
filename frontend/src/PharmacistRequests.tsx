import { useCallback, useEffect, useState } from 'react'
import { API_BASE_URL } from './config'

type RequestItem = { id: string; medicine_name: string; strength: string | null; patient_name: string; patient_city: string | null; patient_phone: string | null; pickup_address: string | null; requested_quantity: number; unit: string; inventory_available: number; expiry_date: string; status: string; rejection_reason: string | null; created_at: string }

export default function PharmacistRequests({ token }: { token: string }) {
  const [items, setItems] = useState<RequestItem[]>([])
  const [error, setError] = useState('')
  const [reason, setReason] = useState<Record<string, string>>({})
  const [reasonErrors, setReasonErrors] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState('')
  const load = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/pharmacist/requests`, { headers: { Authorization: `Bearer ${token}` } })
      const data = await response.json() as RequestItem[] & { detail?: string }
      if (!response.ok) throw new Error(data.detail ?? 'Could not load medicine requests.')
      setItems(data); setError('')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not load medicine requests.') }
  }, [token])
  useEffect(() => { void load() }, [load])
  async function decide(item: RequestItem, action: 'approve' | 'reject') {
    if (action === 'reject' && !(reason[item.id] ?? '').trim()) {
      setReasonErrors((current) => ({ ...current, [item.id]: 'Rejection reason is required.' }))
      setError('')
      return
    }
    setReasonErrors((current) => ({ ...current, [item.id]: '' }))
    setBusy(item.id); setError('')
    try {
      const response = await fetch(`${API_BASE_URL}/pharmacist/requests/${item.id}/${action}`, { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: action === 'reject' ? JSON.stringify({ reason: reason[item.id] ?? '' }) : undefined })
      const data = await response.json() as RequestItem & { detail?: string }
      if (!response.ok) throw new Error(data.detail ?? `Could not ${action} request.`)
      setItems((current) => current.map((row) => row.id === item.id ? data : row))
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not update request.') }
    finally { setBusy('') }
  }
  const pending = items.filter((item) => item.status === 'PENDING')
  const history = items.filter((item) => item.status !== 'PENDING')
  return <div className="mt-8 text-left">
    <div className="mb-6 flex items-center justify-between border-b border-[#edf0ea] pb-5"><div><p className="text-xs font-semibold uppercase tracking-[.12em] text-[#71886d]">Clinic pharmacist</p><h2 className="mt-1 text-xl font-semibold">Medicine Requests</h2></div><button onClick={() => void load()} className="rounded-full border border-[#dce4d9] px-3 py-2 text-xs font-semibold">Refresh</button></div>
    {error && <p role="alert" className="mb-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
    {!items.length ? <p className="rounded-2xl border border-dashed border-[#dce4d9] px-5 py-8 text-center text-sm text-[#718078]">No medicine requests for your clinic.</p> : <>
      <h3 className="mb-3 text-sm font-semibold">Pending review <span className="text-[#87938a]">{pending.length}</span></h3>
      <div className="space-y-3">{pending.map((item) => <article key={item.id} className="rounded-2xl border border-[#eadfbe] bg-[#fffdf7] p-4"><div className="flex flex-wrap justify-between gap-3"><div><h4 className="font-semibold">{item.medicine_name} {item.strength ?? ''}</h4><p className="mt-1 text-sm text-[#52675d]">{item.requested_quantity} {item.unit} requested · {item.inventory_available} available</p><p className="mt-1 text-sm text-[#718078]">Patient: {item.patient_name}{item.patient_city ? ` · ${item.patient_city}` : ''}{item.patient_phone ? ` · ${item.patient_phone}` : ''}</p><p className="mt-1 text-sm text-[#718078]">Pickup/contact address: {item.pickup_address ?? 'Not provided for this older request'}</p><p className="mt-1 text-xs text-[#87938a]">{new Date(item.created_at).toLocaleString()} · Expires {new Date(`${item.expiry_date}T00:00:00`).toLocaleDateString()}</p></div><span className="h-fit rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold">PENDING</span></div><div className="mt-4 flex flex-wrap items-end gap-2"><button disabled={busy === item.id || item.inventory_available < item.requested_quantity} onClick={() => void decide(item, 'approve')} className="rounded-full bg-[#174e3f] px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">{busy === item.id ? 'Updating...' : 'Approve and reserve'}</button><label className="min-w-48 flex-1 text-xs font-medium">Reason for rejection <span className="text-red-700">* Required</span><input aria-invalid={Boolean(reasonErrors[item.id])} className="mt-1 w-full rounded-lg border border-[#dce4d9] px-3 py-2 text-sm" value={reason[item.id] ?? ''} onChange={(event) => { setReason((current) => ({ ...current, [item.id]: event.target.value })); setReasonErrors((current) => ({ ...current, [item.id]: '' })) }} maxLength={1000} placeholder="Explain why the request is rejected" />{reasonErrors[item.id] && <span role="alert" className="mt-1 block text-sm text-red-700">{reasonErrors[item.id]}</span>}</label><button disabled={busy === item.id} onClick={() => void decide(item, 'reject')} className="rounded-full border border-red-200 px-4 py-2 text-xs font-semibold text-red-700 disabled:opacity-50">{busy === item.id ? 'Updating...' : 'Reject'}</button></div></article>)}</div>
      {history.length > 0 && <><h3 className="mb-3 mt-7 text-sm font-semibold">Reviewed requests</h3><div className="space-y-3">{history.map((item) => <article key={item.id} className="rounded-2xl border border-[#e4e9e0] p-4"><div className="flex justify-between gap-3"><div><h4 className="font-semibold">{item.medicine_name} · {item.patient_name}</h4><p className="mt-1 text-sm text-[#718078]">{item.requested_quantity} {item.unit} · {new Date(item.created_at).toLocaleString()}</p><p className="mt-1 text-sm text-[#718078]">Pickup/contact address: {item.pickup_address ?? 'Not provided for this older request'}</p>{item.rejection_reason && <p className="mt-1 text-sm text-red-700">Reason: {item.rejection_reason}</p>}</div><span className="text-xs font-semibold">{item.status}</span></div></article>)}</div></>}
    </>}
  </div>
}
