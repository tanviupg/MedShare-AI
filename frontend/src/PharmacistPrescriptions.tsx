import { useCallback, useEffect, useState } from 'react'
import { API_BASE_URL } from './config'

type Item = { id: string; medicine_name: string; requested_quantity: number; unit: string; created_at: string; prescription: { status: string } }

export default function PharmacistPrescriptions({ token }: { token: string }) {
  const [items, setItems] = useState<Item[]>([])
  const [reason, setReason] = useState<Record<string, string>>({})
  const [reasonErrors, setReasonErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [fileUrl, setFileUrl] = useState('')
  const load = useCallback(async () => {
    const response = await fetch(`${API_BASE_URL}/pharmacist/prescriptions/pending`, { headers: { Authorization: `Bearer ${token}` } })
    const data = await response.json() as Item[] & { detail?: string }
    if (!response.ok) throw new Error(data.detail ?? 'Could not load pending prescriptions.')
    setItems(data)
  }, [token])
  useEffect(() => { void load().catch((cause: unknown) => setError(cause instanceof Error ? cause.message : 'Could not load pending prescriptions.')) }, [load])
  async function viewFile(id: string) {
    const response = await fetch(`${API_BASE_URL}/pharmacist/requests/${id}/prescription/file`, { headers: { Authorization: `Bearer ${token}` } })
    if (!response.ok) { setError('Could not open this prescription.'); return }
    if (fileUrl) URL.revokeObjectURL(fileUrl)
    setFileUrl(URL.createObjectURL(await response.blob()))
  }
  async function decide(id: string, decision: 'approve' | 'reject') {
    if (decision === 'reject' && !(reason[id] ?? '').trim()) {
      setReasonErrors((current) => ({ ...current, [id]: 'Rejection reason is required.' }))
      setError('')
      return
    }
    setReasonErrors((current) => ({ ...current, [id]: '' }))
    setBusy(id); setError('')
    try {
      const response = await fetch(`${API_BASE_URL}/pharmacist/requests/${id}/prescription/${decision}`, { method: 'POST', headers: { Authorization: `Bearer ${token}`, ...(decision === 'reject' ? { 'Content-Type': 'application/json' } : {}) }, body: decision === 'reject' ? JSON.stringify({ reason: reason[id] ?? '' }) : undefined })
      const data = await response.json() as { detail?: string }
      if (!response.ok) throw new Error(data.detail ?? `Could not ${decision} prescription.`)
      await load()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not update prescription.') }
    finally { setBusy('') }
  }
  return <section className="mt-8 text-left">
    <div className="mb-4 flex items-center justify-between border-b border-[#edf0ea] pb-4"><div><p className="text-xs font-semibold uppercase tracking-[.12em] text-[#71886d]">Clinic pharmacist</p><h2 className="mt-1 text-xl font-semibold">Prescription Verification</h2></div><button onClick={() => void load().catch((cause: unknown) => setError(cause instanceof Error ? cause.message : 'Could not refresh.'))} className="rounded-full border border-[#dce4d9] px-3 py-2 text-xs font-semibold">Refresh</button></div>
    {error && <p role="alert" className="mb-3 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
    {!items.length ? <p className="rounded-2xl border border-dashed border-[#dce4d9] px-5 py-8 text-center text-sm text-[#718078]">No prescriptions waiting for verification.</p> : <div className="space-y-3">{items.map((item) => <article key={item.id} className="rounded-2xl border border-[#e4e9e0] p-4"><h3 className="font-semibold">{item.medicine_name}</h3><p className="mt-1 text-sm text-[#718078]">{item.requested_quantity} {item.unit} requested · {new Date(item.created_at).toLocaleString()} · {item.prescription.status.replaceAll('_', ' ')}</p><button onClick={() => void viewFile(item.id)} className="mt-3 rounded-full border border-[#dce4d9] px-3 py-2 text-xs font-semibold">View prescription</button><div className="mt-3 flex flex-wrap items-end gap-2"><button disabled={busy === item.id} onClick={() => void decide(item.id, 'approve')} className="rounded-full bg-[#174e3f] px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">{busy === item.id ? 'Updating...' : 'Approve prescription'}</button><label className="min-w-48 flex-1 text-xs font-medium">Rejection reason <span className="text-red-700">* Required</span><input aria-invalid={Boolean(reasonErrors[item.id])} className="mt-1 w-full rounded-lg border border-[#dce4d9] px-3 py-2 text-sm" value={reason[item.id] ?? ''} onChange={(event) => { setReason((current) => ({ ...current, [item.id]: event.target.value })); setReasonErrors((current) => ({ ...current, [item.id]: '' })) }} maxLength={1000} placeholder="Explain why this prescription is rejected" />{reasonErrors[item.id] && <span role="alert" className="mt-1 block text-sm text-red-700">{reasonErrors[item.id]}</span>}</label><button disabled={busy === item.id} onClick={() => void decide(item.id, 'reject')} className="rounded-full border border-red-200 px-4 py-2 text-xs font-semibold text-red-700 disabled:opacity-50">{busy === item.id ? 'Updating...' : 'Reject'}</button></div></article>)}</div>}
    {fileUrl && <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4" onClick={() => { URL.revokeObjectURL(fileUrl); setFileUrl('') }}><div className="h-[85vh] w-full max-w-4xl rounded-xl bg-white p-3" onClick={(event) => event.stopPropagation()}><button className="mb-2 rounded-full border px-3 py-1 text-sm" onClick={() => { URL.revokeObjectURL(fileUrl); setFileUrl('') }}>Close</button><iframe title="Prescription file" src={fileUrl} className="h-[calc(100%-2rem)] w-full" /></div></div>}
  </section>
}
