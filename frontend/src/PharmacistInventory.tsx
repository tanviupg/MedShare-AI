import { useEffect, useState } from 'react'
import { ArrowLeft, PackageCheck } from 'lucide-react'
import { API_BASE_URL } from './config'

type InventoryItem = {
  id: string; donation_id: string; pharmacist_id: string; medicine_name: string; strength: string | null
  dosage_form: string | null; manufacturer: string | null; batch_number: string | null; expiry_date: string; common_use_category: string; prescription_required: boolean
  quantity_available: number; original_quantity: number; unit: string; status: string; created_at: string
  original_price: string | null; discount_percentage: string | null; patient_price: string | null
  source_donation: { id: string; donor_id: string; status: string; created_at: string }
  review: { decision: string; reason: string | null; reviewed_at: string; pharmacist_id: string }
}

export default function PharmacistInventory({ token, refreshKey, onPricingUpdated }: { token: string; refreshKey: number; onPricingUpdated: () => void }) {
  const [items, setItems] = useState<InventoryItem[]>([])
  const [selected, setSelected] = useState<InventoryItem | null>(null)
  const [error, setError] = useState('')
  const [savingRequirement, setSavingRequirement] = useState(false)
  const [savingPricing, setSavingPricing] = useState(false)
  const [originalPrice, setOriginalPrice] = useState('')
  const [discount, setDiscount] = useState('0')
  const [auth] = useState({ Authorization: `Bearer ${token}` })

  useEffect(() => {
    fetch(`${API_BASE_URL}/inventory`, { headers: auth }).then(async (response) => {
      const data = await response.json() as InventoryItem[] & { detail?: string }
      if (!response.ok) throw new Error(data.detail ?? 'Could not load inventory.')
      setItems(data)
    }).catch((cause) => setError(cause instanceof Error ? cause.message : 'Could not load inventory.'))
  }, [auth, refreshKey])

  async function open(item: InventoryItem) {
    setError('')
    try {
      const response = await fetch(`${API_BASE_URL}/inventory/${item.id}`, { headers: auth })
      const data = await response.json() as InventoryItem & { detail?: string }
      if (!response.ok) throw new Error(data.detail ?? 'Could not open inventory record.')
      setSelected(data)
      setOriginalPrice(data.original_price ?? '')
      setDiscount(data.discount_percentage ?? '0')
      setItems((current) => current.map((row) => row.id === data.id ? data : row))
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not open inventory record.') }
  }

  async function updateRequirement(value: string) {
    if (!selected) return
    setSavingRequirement(true); setError('')
    try {
      const response = await fetch(`${API_BASE_URL}/inventory/${selected.id}/common-use-category`, { method: 'PATCH', headers: { ...auth, 'Content-Type': 'application/json' }, body: JSON.stringify({ common_use_category: value }) })
      const data = await response.json() as InventoryItem & { detail?: string }
      if (!response.ok) throw new Error(data.detail ?? 'Could not update prescription configuration.')
      setSelected(data); setItems((current) => current.map((row) => row.id === data.id ? data : row))
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not update prescription configuration.') }
    finally { setSavingRequirement(false) }
  }

  async function updatePricing() {
    if (!selected) return
    const original = originalPrice.trim() === '' ? null : Number(originalPrice)
    const percent = discount.trim() === '' ? null : Number(discount)
    if (original !== null && (!Number.isFinite(original) || original < 0)) { setError('Enter a valid non-negative reference price.'); return }
    if (percent !== null && (!Number.isFinite(percent) || percent < 0 || percent > 100)) { setError('Discount must be between 0% and 100%.'); return }
    if ((original === null) !== (percent === null)) { setError('Set both price and discount, or clear both to leave pricing unconfigured.'); return }
    setSavingPricing(true); setError('')
    try {
      const response = await fetch(`${API_BASE_URL}/inventory/${selected.id}/pricing`, { method: 'PATCH', headers: { ...auth, 'Content-Type': 'application/json' }, body: JSON.stringify({ original_price: original, discount_percentage: percent }) })
      const data = await response.json() as InventoryItem & { detail?: string }
      if (!response.ok) throw new Error(data.detail ?? 'Could not update pricing.')
      setSelected(data); setItems((current) => current.map((row) => row.id === data.id ? data : row))
      onPricingUpdated()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not update pricing.') }
    finally { setSavingPricing(false) }
  }

  const preview = originalPrice.trim() && discount.trim() && Number.isFinite(Number(originalPrice)) && Number.isFinite(Number(discount)) && Number(originalPrice) >= 0 && Number(discount) >= 0 && Number(discount) <= 100
    ? (Number(originalPrice) * (1 - Number(discount) / 100)).toFixed(2) : null

  const expiry = (date: string) => Math.ceil((new Date(`${date}T00:00:00`).getTime() - new Date(new Date().toDateString()).getTime()) / 86400000)
  const statusStyle = (status: string) => status === 'AVAILABLE' ? 'bg-emerald-50 text-emerald-800' : status === 'EXPIRED' ? 'bg-red-50 text-red-700' : 'bg-slate-100 text-slate-600'

  return <div className="mt-8 text-left">
    <div className="mb-6 flex items-center justify-between border-b border-[#edf0ea] pb-5"><div><p className="text-xs font-semibold uppercase tracking-[.12em] text-[#71886d]">Clinic pharmacist</p><h2 className="mt-1 text-xl font-semibold">{selected ? 'Inventory details' : 'Clinic inventory'}</h2></div></div>
    {error && <p role="alert" className="mb-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
    {selected ? <><button onClick={() => setSelected(null)} className="mb-4 flex items-center gap-1.5 text-sm font-medium text-[#718078]"><ArrowLeft size={16} /> Back to inventory</button><article className="rounded-2xl border border-[#e4e9e0] p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-lg font-semibold">{selected.medicine_name}</h3><p className="mt-1 text-sm text-[#718078]">{[selected.strength, selected.dosage_form].filter(Boolean).join(' Â· ') || 'Medicine details'}</p></div><span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${statusStyle(selected.status)}`}>{selected.status}</span></div><dl className="mt-5 grid gap-4 text-sm sm:grid-cols-2">{[['Manufacturer', selected.manufacturer], ['Batch number', selected.batch_number], ['Expiry date', new Date(`${selected.expiry_date}T00:00:00`).toLocaleDateString()], ['Quantity available', `${selected.quantity_available} ${selected.unit}`], ['Original quantity', `${selected.original_quantity} ${selected.unit}`], ['Inventory ID', selected.id]].map(([label, value]) => <div key={label}><dt className="text-xs font-medium uppercase tracking-wide text-[#87938a]">{label}</dt><dd className="mt-1 break-all">{value || 'Not provided'}</dd></div>)}</dl><div className="mt-5 rounded-xl border border-[#e4e9e0] p-4"><label className="block text-sm font-semibold">Patient-facing common-use category<select disabled={savingRequirement} className="mt-2 w-full rounded-xl border border-[#dce4d9] bg-white px-3 py-2.5 text-sm font-normal" value={selected.common_use_category} onChange={(event) => void updateRequirement(event.target.value)}><option value="COLD">Cold ? prescription not required</option><option value="COUGH">Cough ? prescription not required</option><option value="FLU">Flu ? prescription not required</option><option value="FEVER">Fever ? prescription not required</option><option value="PAIN">Pain ? prescription required</option><option value="ALLERGY">Allergy ? prescription required</option><option value="OTHER">Other ? prescription required</option><option value="UNCLASSIFIED">Unclassified ? prescription required</option></select></label><p className="mt-2 text-xs text-[#718078]">Common-use category is pharmacist-configured information, not a diagnosis.</p></div><div className="mt-5 rounded-xl border border-[#e4e9e0] p-4"><h4 className="font-semibold">Optional patient pricing</h4><p className="mt-1 text-xs text-[#718078]">Donated medicine does not need a reference price. Leave price empty to keep it unpriced; enter ?0 to mark it free.</p><div className="mt-3 grid gap-3 sm:grid-cols-2"><label className="text-sm font-medium">Original/reference price (?)<input className="mt-1 w-full rounded-xl border border-[#dce4d9] px-3 py-2.5 font-normal" type="number" min="0" step="0.01" value={originalPrice} onChange={(e) => setOriginalPrice(e.target.value)} /></label><label className="text-sm font-medium">Discount (%)<input className="mt-1 w-full rounded-xl border border-[#dce4d9] px-3 py-2.5 font-normal" type="number" min="0" max="100" step="0.01" value={discount} onChange={(e) => setDiscount(e.target.value)} /></label></div><p className="mt-3 text-sm">Calculated patient price: <strong>{preview === null ? "Enter valid pricing values" : Number(preview) === 0 ? "Free" : `?${preview}`}</strong></p><button disabled={savingPricing} onClick={() => void updatePricing()} className="mt-3 rounded-full bg-[#174e3f] px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">{savingPricing ? "Saving�" : "Save pricing"}</button></div><div className="mt-5 rounded-xl bg-[#f7f8f5] p-4 text-sm"><h4 className="font-semibold">Source donation and review</h4><p className="mt-2">Donation {selected.source_donation.id} Â· {selected.source_donation.status}</p><p className="mt-1 text-[#718078]">Donor reference: {selected.source_donation.donor_id}</p><p className="mt-3">{selected.review.decision} by pharmacist {selected.review.pharmacist_id}</p><p className="mt-1 text-[#718078]">Reviewed {new Date(selected.review.reviewed_at).toLocaleString()}</p>{selected.review.reason && <p className="mt-2">Review note: {selected.review.reason}</p>}</div></article></> : items.length ? <div className="space-y-3">{items.map((item) => { const days = expiry(item.expiry_date); return <button key={item.id} onClick={() => open(item)} className="w-full rounded-2xl border border-[#e4e9e0] bg-white p-4 text-left transition hover:border-[#b7cbb1]"><span className="flex items-start justify-between gap-3"><span><span className="block font-semibold">{item.medicine_name}</span><span className="mt-1 block text-sm text-[#718078]">{[item.strength, item.dosage_form].filter(Boolean).join(' Â· ')}</span><span className="mt-1 block text-xs text-[#87938a]">Batch {item.batch_number || 'not provided'} Â· Expires {new Date(`${item.expiry_date}T00:00:00`).toLocaleDateString()}</span><span className={`mt-1 block text-xs font-medium ${days < 0 ? 'text-red-700' : days <= 90 ? 'text-amber-700' : 'text-[#718078]'}`}>{days < 0 ? 'Expired' : days <= 90 ? `Expires in ${days} days` : 'Expiry date recorded'} Â· {item.quantity_available} {item.unit}{item.quantity_available <= 5 ? ' Â· Low stock' : ''}</span></span><span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${statusStyle(item.status)}`}>{item.status}</span></span></button> })}</div> : <div className="rounded-2xl border border-dashed border-[#dce4d9] px-5 py-8 text-center"><PackageCheck className="mx-auto text-[#9aab96]" size={23} /><p className="mt-3 text-sm font-medium">No inventory yet</p><p className="mt-1 text-xs text-[#87938a]">Approved donations will appear here automatically.</p></div>}
  </div>
}
