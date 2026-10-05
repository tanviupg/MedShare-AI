import { useEffect, useState } from 'react'
import { ArrowLeft, Check, FileImage, LogOut } from 'lucide-react'
import { API_BASE_URL } from './config'

type Image = { id: string; original_filename: string; download_url: string }
type Extraction = { fields: Record<string, string | number | null>; raw_ocr_text: string | null; confidence: Record<string, number | null>; overall_confidence: number | null; provider: string; is_mock: boolean; status: string; error_message?: string | null }
type ExtractionResponse = { items: Extraction[]; detail?: string }
type CommonUseCategory = 'COLD' | 'COUGH' | 'FLU' | 'FEVER' | 'PAIN' | 'ALLERGY' | 'OTHER' | 'UNCLASSIFIED'
type VerifiedDetails = { medicine_name: string; strength: string; dosage_form: string; packaging_type: string; manufacturer: string; batch_number: string; expiry_date: string; quantity: string; unit: string; common_use_category: CommonUseCategory }
type Donation = { id: string; medicine_name: string | null; strength: string | null; dosage_form: string | null; packaging_type: string | null; manufacturer: string | null; batch_number: string | null; expiry_date: string | null; donor_expiry_date: string | null; pickup_address: string | null; quantity: number | null; unit: string | null; details_confirmed: boolean; status: 'PENDING_REVIEW' | 'APPROVED' | 'REJECTED' | 'CANCELLED'; images: Image[] }
const categories: { value: CommonUseCategory; label: string }[] = [
  { value: 'COLD', label: 'Cold' }, { value: 'COUGH', label: 'Cough' }, { value: 'FLU', label: 'Flu' },
  { value: 'FEVER', label: 'Fever' }, { value: 'PAIN', label: 'Pain' }, { value: 'ALLERGY', label: 'Allergy' },
  { value: 'OTHER', label: 'Other' }, { value: 'UNCLASSIFIED', label: 'Unclassified' },
]
const inputClass = 'mt-1.5 w-full rounded-xl border border-[#dce4d9] bg-white px-3.5 py-3 text-sm outline-none transition focus:border-[#719a6c] focus:ring-2 focus:ring-[#719a6c]/15'

function mapExtractionToVerified(current: VerifiedDetails, fields: Extraction['fields']): VerifiedDetails {
  const value = (field: string) => fields[field] == null ? '' : String(fields[field])
  return {
    ...current,
    medicine_name: value('medicine_name'),
    strength: value('strength'),
    dosage_form: value('dosage_form'),
    manufacturer: value('manufacturer'),
    batch_number: value('batch_number'),
    expiry_date: value('expiry_date'),
    quantity: value('quantity'),
    packaging_type: value('packaging_type'),
  }
}

function hasCompleteVerifiedDetails(details: VerifiedDetails): boolean {
  const today = new Date().toISOString().slice(0, 10)
  return Boolean(
    details.medicine_name.trim()
    && details.expiry_date >= today
    && Number.isInteger(Number(details.quantity))
    && Number(details.quantity) > 0
    && details.unit.trim(),
  )
}

export default function PharmacistReview({ token, onLogout, onReviewComplete }: { token: string; onLogout: () => void; onReviewComplete: () => void }) {
  const [queue, setQueue] = useState<Donation[]>([])
  const [selected, setSelected] = useState<Donation | null>(null)
  const [images, setImages] = useState<Record<string, string>>({})
  const [reason, setReason] = useState('')
  const [reasonError, setReasonError] = useState('')
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [ocrBusy, setOcrBusy] = useState(false)
  const [extractions, setExtractions] = useState<Extraction[]>([])
  const [verified, setVerified] = useState<VerifiedDetails | null>(null)
  const [physicalChecked, setPhysicalChecked] = useState(false)
  const auth = { Authorization: `Bearer ${token}` }

  async function refresh() {
    const url = `${API_BASE_URL}/donations/review-queue`
    const response = await fetch(url, { headers: auth })
    const data = await response.json() as Donation[] & { detail?: string }
    if (!response.ok) throw new Error(data.detail ?? 'Could not load the review queue.')
    setQueue(data)
  }
  useEffect(() => {
    refresh().catch((cause) => setError(cause instanceof Error ? cause.message : 'Could not load the review queue.'))
  }, [token])

  async function open(donation: Donation) {
    setError(''); setMessage(''); setReasonError(''); setFieldErrors({})
    try {
      const response = await fetch(`${API_BASE_URL}/donations/${donation.id}/review`, { headers: auth })
      const data = await response.json() as Donation & { detail?: string }
      if (!response.ok) throw new Error(data.detail ?? 'Could not open donation.')
      setSelected(data); setReason('')
      setExtractions([])
      setVerified({
        medicine_name: data.medicine_name ?? '',
        strength: data.strength ?? '',
        dosage_form: data.dosage_form ?? '',
        packaging_type: data.packaging_type ?? '',
        manufacturer: data.manufacturer ?? '',
        batch_number: data.batch_number ?? '',
        expiry_date: data.expiry_date ?? data.donor_expiry_date ?? '',
        quantity: String(data.quantity ?? ''),
        unit: data.unit ?? 'units',
        common_use_category: 'UNCLASSIFIED',
      })
      const extractionResponse = await fetch(`${API_BASE_URL}/donations/${data.id}/extraction`, { headers: auth })
      if (extractionResponse.ok) {
        const rows = (await extractionResponse.json() as ExtractionResponse).items
        setExtractions(rows)
        const fields = rows.find((item) => item.status === 'COMPLETED')?.fields
        if (fields) setVerified((current) => current ? mapExtractionToVerified(current, fields) : current)
      }
      setPhysicalChecked(false)
      for (const image of data.images) {
        const result = await fetch(`${API_BASE_URL}${image.download_url}`, { headers: auth })
        if (result.ok) {
          const url = URL.createObjectURL(await result.blob())
          setImages((current) => ({ ...current, [`${data.id}:${image.id}`]: url }))
        }
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not open donation.') }
  }

  async function runOCR() {
    if (!selected || selected.images.length === 0) return
    setOcrBusy(true); setError(''); setMessage('')
    try {
      const response = await fetch(`${API_BASE_URL}/donations/${selected.id}/extract`, { method: 'POST', headers: auth })
      const result = await response.json() as ExtractionResponse
      if (!response.ok) throw new Error(result.detail ?? 'Could not run OCR.')
      const rows = result.items
      setExtractions(rows)
      const fields = rows.find((item) => item.status === 'COMPLETED')?.fields
      if (fields) setVerified((current) => current ? mapExtractionToVerified(current, fields) : current)
      setMessage('OCR finished. Compare the extracted information with the photos and verify every field manually.')
    } catch (cause) {
      setError(`${cause instanceof Error ? cause.message : 'Could not run OCR.'} You can continue with manual verification.`)
    } finally { setOcrBusy(false) }
  }

  async function review(decision: 'APPROVED' | 'REJECTED') {
    if (!selected) return
    if (decision === 'REJECTED' && !reason.trim()) {
      setReasonError('Rejection reason is required.')
      setError('')
      return
    }
    setReasonError('')
    if (decision === 'APPROVED' && verified) {
      const required: Record<string, string> = {
        medicine_name: 'Medicine name is required.',
        expiry_date: 'Verified expiry date is required.',
        quantity: 'Enter a quantity greater than zero.',
        unit: 'Quantity unit is required.',
      }
      const nextErrors: Record<string, string> = {}
      for (const [key, message] of Object.entries(required)) {
        if (!verified[key as keyof VerifiedDetails].trim() || (key === 'quantity' && (!Number.isInteger(Number(verified.quantity)) || Number(verified.quantity) <= 0))) nextErrors[key] = message
      }
      setFieldErrors(nextErrors)
      if (Object.keys(nextErrors).length) {
        setError('Complete the required fields before approving this donation.')
        return
      }
    }
    setBusy(true); setError('')
    try {
      const attachVerifiedDetails = Boolean(verified && (decision === 'APPROVED' || (physicalChecked && hasCompleteVerifiedDetails(verified))))
      const response = await fetch(`${API_BASE_URL}/donations/${selected.id}/review`, { method: 'POST', headers: { ...auth, 'Content-Type': 'application/json' }, body: JSON.stringify({ decision, reason: reason.trim() || null, physical_package_checked: physicalChecked, verified_details: attachVerifiedDetails && verified ? { ...verified, quantity: Number(verified.quantity) } : null }) })
      const data = await response.json() as { detail?: string }
      if (!response.ok) throw new Error(data.detail ?? 'Could not save review.')
      setMessage(decision === 'REJECTED' ? 'Donation rejected successfully.' : 'Donation approved successfully and added to inventory.')
      setError('')
      setSelected(null)
      onReviewComplete()
      await refresh().catch((cause) => setError(`Review succeeded, but the queue could not be refreshed: ${cause instanceof Error ? cause.message : 'Please refresh the queue.'}`))
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save review.') }
    finally { setBusy(false) }
  }

  return <div className="mt-8 text-left">
    <div className="mb-6 flex items-center justify-between border-b border-[#edf0ea] pb-5"><div><p className="text-xs font-semibold uppercase tracking-[.12em] text-[#71886d]">Clinic pharmacist</p><h2 className="mt-1 text-xl font-semibold">{selected ? 'Verify donation' : 'Pending donations'}</h2></div><button onClick={onLogout} aria-label="Log out" className="rounded-full p-2 text-[#718078] hover:bg-[#f5f7f2]"><LogOut size={18} /></button></div>
    {message && <p role="status" className="mb-4 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{message}</p>}{error && !selected && <p role="alert" className="mb-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
    {selected ? <><button onClick={() => setSelected(null)} className="mb-4 flex items-center gap-1.5 text-sm font-medium text-[#718078]"><ArrowLeft size={16} /> Back to queue</button><article className="rounded-2xl border border-[#e4e9e0] p-5">
      <div><h3 className="text-lg font-semibold">Medicine donation</h3><p className="mt-1 text-sm text-[#718078]">Pickup address: {selected.pickup_address || 'Not provided'}</p><p className="mt-1 text-sm text-[#718078]">Donor-reported expiry: {selected.donor_expiry_date ? new Date(`${selected.donor_expiry_date}T00:00:00`).toLocaleDateString() : 'Not provided'}</p></div>
      <div className="mt-5"><h4 className="text-sm font-semibold">Original uploaded medicine photos</h4>{selected.images.length ? <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">{selected.images.map((image) => <div key={image.id} className="overflow-hidden rounded-xl border border-[#e4e9e0] bg-[#f7f8f5]"><div className="grid aspect-square place-items-center">{images[`${selected.id}:${image.id}`] ? <a className="size-full" target="_blank" rel="noreferrer" href={images[`${selected.id}:${image.id}`]}><img className="size-full object-contain" src={images[`${selected.id}:${image.id}`]} alt="Uploaded medicine package" /></a> : <FileImage className="text-[#9aab96]" />}</div></div>)}</div> : <p className="mt-2 text-sm text-[#718078]">No photos were submitted.</p>}</div>
      <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="font-semibold">AI/OCR extracted information</p><p className="mt-1 text-xs">Compare each result against the uploaded photos and physical package. OCR alone cannot approve a donation.</p></div><button type="button" onClick={() => void runOCR()} disabled={ocrBusy || selected.images.length === 0} className="rounded-full border border-amber-300 bg-white px-4 py-2 text-sm font-semibold text-amber-900 disabled:opacity-60">{ocrBusy ? 'Running OCR...' : 'Run OCR'}</button></div>{extractions.length ? extractions.map((item, index) => <div key={index} className="mt-3 border-t border-amber-200 pt-3 text-xs"><p>Photo {index + 1}: {item.is_mock ? 'Mock provider; no OCR was performed.' : item.provider === 'gemini' ? 'Gemini-assisted result; calibrated OCR confidence scores are not available.' : typeof item.overall_confidence === 'number' ? `Overall confidence ${Math.round(item.overall_confidence * 100)}%.` : 'Confidence unavailable.'}</p>{item.raw_ocr_text && <div className="mt-2 rounded-lg bg-white/70 p-2"><p className="font-semibold">Recognized package text</p><pre className="mt-1 whitespace-pre-wrap font-sans">{item.raw_ocr_text}</pre></div>}<dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1">{Object.entries(item.fields).map(([field, value]) => <div key={field}><dt className="inline font-medium">{field.replaceAll('_', ' ')}: </dt><dd className="inline">{value ?? 'Not detected'}</dd></div>)}</dl>{!item.is_mock && item.provider !== 'gemini' && <p className="mt-1">Field confidence: {Object.entries(item.fields).map(([field]) => `${field.replaceAll('_', ' ')} ${Math.round((item.confidence[field] ?? 0) * 100)}%`).join(' · ')}</p>}{item.status === 'FAILED' && <p className="mt-1 font-semibold">{item.error_message ?? 'OCR could not read this image. Please verify the package manually.'}</p>}<p className="mt-1">{item.provider === 'gemini' ? 'Gemini does not provide per-field confidence; verify all values against the package.' : `Uncertain fields: ${Object.entries(item.confidence).filter(([field, score]) => field !== 'overall_confidence' && (score == null || score < 0.5)).map(([field]) => field.replaceAll('_', ' ')).join(', ') || 'none'}.`}</p></div>) : <p className="mt-2 text-xs">OCR has not been run. You may run OCR or continue with manual package verification.</p>}</div>
      {verified && <fieldset className="mt-5 rounded-xl border border-[#e4e9e0] p-4"><legend className="px-2 text-sm font-semibold">Pharmacist-verified medicine information</legend><p className="mb-3 text-xs text-[#718078]">Review and correct these fields after checking the package.</p><div className="grid gap-3 sm:grid-cols-2">{([['medicine_name', 'Medicine name', 'text'], ['strength', 'Strength', 'text'], ['dosage_form', 'Dosage form', 'text'], ['packaging_type', 'Packaging type', 'text'], ['manufacturer', 'Manufacturer', 'text'], ['batch_number', 'Batch number', 'text'], ['expiry_date', 'Verified expiry date', 'date'], ['quantity', 'Verified quantity', 'number'], ['unit', 'Quantity unit', 'text']] as const).map(([key, label, type]) => { const required = ['medicine_name', 'expiry_date', 'quantity', 'unit'].includes(key); return <label key={key} className="block text-sm font-medium">{label} {required ? <span className="text-red-700">* Required</span> : <span className="text-[#718078]">(Optional)</span>}<input className={inputClass} type={type} min={type === 'number' ? '1' : undefined} placeholder={key === 'expiry_date' ? 'Select the verified expiry date' : undefined} value={verified[key]} onChange={(event) => { setVerified((current) => current ? { ...current, [key]: event.target.value } : current); setFieldErrors((current) => ({ ...current, [key]: '' })) }} /></label>})}<label className="block text-sm font-medium">Patient-facing common use <span className="text-red-700">* Required</span><select className={inputClass} value={verified.common_use_category} onChange={(event) => setVerified((current) => current ? { ...current, common_use_category: event.target.value as CommonUseCategory } : current)}>{categories.map((category) => <option key={category.value} value={category.value}>{category.label}</option>)}</select></label></div>{Object.entries(fieldErrors).map(([key, message]) => message && <p key={key} role="alert" className="mt-2 text-sm text-red-700">{message}</p>)}<p className="mt-2 text-xs text-[#718078]">Cold, Cough, Flu, and Fever permit a request without a prescription under the current product rule. All other categories require one. This is a common-use classification, not a diagnosis.</p></fieldset>}
      <label className="mt-5 flex items-start gap-2 rounded-xl border border-[#dce9d6] bg-[#f5f9f2] p-4 text-sm leading-6 text-[#55704f]"><input className="mt-1" type="checkbox" checked={physicalChecked} onChange={(event) => setPhysicalChecked(event.target.checked)} /><span>I physically cross-checked the medicine and package against the photos and verified information. <b className="text-red-700">Required for approval.</b> For rejection, incomplete verified details are not submitted. I understand the pharmacist is the final authority.</span></label>
      <label className="mt-4 block text-sm font-medium">Rejection reason <span className="text-red-700">* Required to reject</span> <span className="text-[#718078]">(Optional for approval)</span><textarea className={`${inputClass} min-h-24 resize-y`} value={reason} onChange={(event) => { setReason(event.target.value); setReasonError('') }} maxLength={2000} placeholder="Enter a clear reason if rejecting this donation" />{reasonError && <span role="alert" className="mt-1 block text-sm text-red-700">{reasonError}</span>}</label>
      {selected && error && <p role="alert" className="mt-3 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
      <div className="mt-4 grid gap-3 sm:grid-cols-2"><button disabled={busy || !physicalChecked || !verified} onClick={() => void review('APPROVED')} className="rounded-full bg-[#174e3f] px-5 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60">{busy ? 'Saving review...' : 'Approve verified donation'}</button><button disabled={busy} onClick={() => void review('REJECTED')} className="rounded-full border border-red-200 px-5 py-3 text-sm font-semibold text-red-700 disabled:cursor-not-allowed disabled:opacity-60">{busy ? 'Saving review...' : 'Reject donation'}</button></div>
    </article></> : queue.length ? <div className="space-y-3">{queue.map((donation) => <button key={donation.id} onClick={() => void open(donation)} className="w-full rounded-2xl border border-[#e4e9e0] bg-white p-4 text-left transition hover:border-[#b7cbb1]"><span className="flex items-start justify-between gap-3"><span><span className="block font-semibold">Medicine donation ? {donation.pickup_address || 'Pickup address not provided'}</span><span className="mt-1 block text-sm text-[#718078]">Donor-reported expiry: {donation.donor_expiry_date ? new Date(`${donation.donor_expiry_date}T00:00:00`).toLocaleDateString() : 'Not provided'}</span><span className="mt-1 block text-xs text-[#87938a]">{donation.images.length} photo{donation.images.length === 1 ? '' : 's'} ? awaiting pharmacist verification</span></span><span className="shrink-0 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800">Pending review</span></span></button>)}</div> : <div className="rounded-2xl border border-dashed border-[#dce4d9] px-5 py-8 text-center"><Check className="mx-auto text-[#9aab96]" size={23} /><p className="mt-3 text-sm font-medium">Queue is clear</p><p className="mt-1 text-xs text-[#87938a]">New image-first donations will appear here.</p></div>}
  </div>

}
