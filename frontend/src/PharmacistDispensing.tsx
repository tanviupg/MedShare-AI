import { useCallback, useEffect, useState } from 'react'
import { API_BASE_URL } from './config'

type DispensingItem = { request_id: string; medicine_name: string; strength: string | null; dosage_form: string | null; clinic_name: string; quantity: number; unit: string; pickup_code: string; status: string; requested_at: string; dispensed_at: string | null; patient_name: string; patient_city: string | null; patient_phone: string | null; prescription_required: boolean | null; prescription_status: string | null }

export default function PharmacistDispensing({ token }: { token: string }) {
  const [items, setItems] = useState<DispensingItem[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const load = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/pharmacist/dispensing`, { headers: { Authorization: `Bearer ${token}` } })
      const data = await response.json() as DispensingItem[] & { detail?: string }
      if (!response.ok) throw new Error(data.detail ?? 'Could not load pickup requests.')
      setItems(data); setError('')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not load pickup requests.') }
  }, [token])
  useEffect(() => { void load() }, [load])
  async function dispense(item: DispensingItem) {
    const medicine = [item.medicine_name, item.strength].filter(Boolean).join(' ')
    if (!window.confirm(`Confirm dispensing ${item.quantity} ${item.unit} of ${medicine} to ${item.patient_name}?`)) return
    setBusy(item.request_id); setError('')
    try {
      const response = await fetch(`${API_BASE_URL}/pharmacist/requests/${item.request_id}/dispense`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
      const data = await response.json() as DispensingItem & { detail?: string }
      if (!response.ok) throw new Error(data.detail ?? 'Could not record dispensing.')
      setItems((current) => current.filter((row) => row.request_id !== item.request_id))
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not record dispensing.') }
    finally { setBusy('') }
  }
  return <section className="mt-8 text-left">
    <div className="mb-5 flex items-center justify-between border-b border-[#edf0ea] pb-4"><div><p className="text-xs font-semibold uppercase tracking-[.12em] text-[#71886d]">Clinic pharmacist</p><h2 className="mt-1 text-xl font-semibold">Dispensing / Pickup</h2></div><button onClick={() => void load()} className="rounded-full border border-[#dce4d9] px-3 py-2 text-xs font-semibold">Refresh</button></div>
    {error && <p role="alert" className="mb-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
    {items.length ? <div className="space-y-3">{items.map((item) => <article key={item.request_id} className="rounded-2xl border border-[#dce9d6] bg-[#fbfcfa] p-4"><div className="flex flex-wrap justify-between gap-3"><div><h3 className="font-semibold">{item.medicine_name} {item.strength ?? ''}</h3><p className="mt-1 text-sm text-[#52675d]">{[item.dosage_form, `${item.quantity} ${item.unit} reserved`].filter(Boolean).join(' · ')}</p><p className="mt-1 text-sm text-[#718078]">Patient: {item.patient_name}{item.patient_city ? ` · ${item.patient_city}` : ''}{item.patient_phone ? ` · ${item.patient_phone}` : ''}</p><p className="mt-1 text-xs text-[#87938a]">Requested {new Date(item.requested_at).toLocaleString()} · Prescription {item.prescription_required === false ? 'not required' : item.prescription_status ?? 'not verified'}</p><p className="mt-2 text-sm">Pickup code: <span className="font-mono font-bold tracking-wider">{item.pickup_code}</span></p></div><span className="h-fit rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-800">APPROVED · RESERVED</span></div><button disabled={busy === item.request_id} onClick={() => void dispense(item)} className="mt-4 rounded-full bg-[#174e3f] px-4 py-2.5 text-xs font-semibold text-white disabled:opacity-50">{busy === item.request_id ? 'Recording…' : 'Mark as Dispensed'}</button></article>)}</div> : <p className="rounded-2xl border border-dashed border-[#dce4d9] px-5 py-8 text-center text-sm text-[#718078]">No reserved requests are waiting for pickup.</p>}
  </section>
}
