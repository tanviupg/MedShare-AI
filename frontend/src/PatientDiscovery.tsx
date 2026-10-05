import { useEffect, useState } from 'react'
import { CalendarDays, ImageOff, MapPin, PackageCheck, Search, ShieldCheck, Upload, X } from 'lucide-react'
import { API_BASE_URL } from './config'

type Medicine = {
  medicine_id: string
  medicine_name: string
  common_use_category: string
  expiry_date: string
  availability: number
  availability_unit: string
  clinic_name: string
  clinic_city: string
  prescription_required: boolean
  original_price: string | null
  discount_percentage: string | null
  patient_price: string | null
  images: { image_url: string }[]
}
type PageResult = { items: Medicine[]; total: number; page: number; page_size: number }
type MedicineRequest = {
  id: string
  medicine_name: string
  common_use_category: string
  clinic_name: string
  requested_quantity: number
  unit: string
  pickup_address: string | null
  status: string
  created_at: string
  fulfilled_at: string | null
  pickup_code: string | null
  prescription_required: boolean | null
  prescription_status: string | null
  prescription_rejection_reason: string | null
  price_original_snapshot: string | null
  discount_snapshot: string | null
  patient_price_snapshot: string | null
  payment_status: string | null
}
type Checkout = {
  request_id: string
  medicine_name: string
  quantity: number
  unit: string
  clinic_name: string
  original_price: string
  discount_percentage: string
  patient_price: string
  amount: string
  currency: string
  payment_status: string
  payment_method: string | null
  is_free: boolean
  demo_payment: boolean
}

const categoryLabels: Record<string, string> = {
  COLD: 'Cold',
  COUGH: 'Cough',
  FLU: 'Flu',
  FEVER: 'Fever',
  PAIN: 'Pain',
  ALLERGY: 'Allergy',
  OTHER: 'Other',
  UNCLASSIFIED: 'Unclassified',
}
const inputClass = 'w-full rounded-xl border border-[#dce4d9] bg-white px-3.5 py-3 text-sm outline-none focus:border-[#719a6c] focus:ring-2 focus:ring-[#719a6c]/15'
const buttonClass = 'rounded-full bg-[#174e3f] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#103d31] disabled:opacity-50'

function categoryLabel(category: string) {
  return categoryLabels[category] ?? 'Unclassified'
}

function priceLabel(medicine: Medicine) {
  if (medicine.original_price === null || medicine.patient_price === null) return 'Price not configured'
  return Number(medicine.patient_price) === 0 ? 'Free' : `₹${medicine.patient_price}`
}

export default function PatientDiscovery({ token, onLogout }: { token: string; onLogout: () => void }) {
  const [name, setName] = useState('')
  const [category, setCategory] = useState('')
  const [city, setCity] = useState('')
  const [clinic, setClinic] = useState('')
  const [page, setPage] = useState(1)
  const [discoveryRevision, setDiscoveryRevision] = useState(0)
  const [result, setResult] = useState<PageResult | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<'search' | 'requests'>('search')
  const [requests, setRequests] = useState<MedicineRequest[]>([])
  const [requestsLoading, setRequestsLoading] = useState(false)
  const [requestQuantity, setRequestQuantity] = useState<Record<string, number>>({})
  const [requestBusy, setRequestBusy] = useState<string | null>(null)
  const [requestMessage, setRequestMessage] = useState('')
  const [pickupAddresses, setPickupAddresses] = useState<Record<string, string>>({})
  const [prescriptionFiles, setPrescriptionFiles] = useState<Record<string, File | undefined>>({})
  const [requestFiles, setRequestFiles] = useState<Record<string, File | undefined>>({})
  const [fileError, setFileError] = useState('')
  const [checkouts, setCheckouts] = useState<Record<string, Checkout>>({})
  const [checkoutBusy, setCheckoutBusy] = useState<string | null>(null)
  const [imageUrls, setImageUrls] = useState<Record<string, string>>({})
  const [selectedMedicine, setSelectedMedicine] = useState<Medicine | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    const params = new URLSearchParams({ page: String(page), page_size: '12' })
    if (name.trim()) params.set('q', name.trim())
    if (category) params.set('category', category)
    if (city.trim()) params.set('city', city.trim())
    if (clinic.trim()) params.set('clinic', clinic.trim())
    setLoading(true)
    setError('')
    fetch(`${API_BASE_URL}/patient/medicines?${params}`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    }).then(async (response) => {
      const body = await response.json() as PageResult & { detail?: string }
      if (!response.ok) throw new Error(body.detail ?? 'Could not load available medicines.')
      setResult(body)
    }).catch((reason: unknown) => {
      if (reason instanceof Error && reason.name !== 'AbortError') {
        setError(reason.message || 'Could not connect to the medicine search.')
      }
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false)
    })
    return () => controller.abort()
  }, [token, name, category, city, clinic, page, discoveryRevision])

  useEffect(() => {
    const controller = new AbortController()
    const objectUrls: string[] = []
    setImageUrls({})

    const images = result?.items.flatMap((medicine) => {
      const image = medicine.images[0]
      return image ? [{ key: `${medicine.medicine_id}:${image.image_url}`, url: image.image_url }] : []
    }) ?? []

    void Promise.all(images.map(async ({ key, url }) => {
      try {
        const response = await fetch(`${API_BASE_URL}${url}`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        })
        if (!response.ok) return
        const blob = await response.blob()
        if (!blob.type.startsWith('image/')) return
        const objectUrl = URL.createObjectURL(blob)
        if (controller.signal.aborted) {
          URL.revokeObjectURL(objectUrl)
          return
        }
        objectUrls.push(objectUrl)
        setImageUrls((current) => ({ ...current, [key]: objectUrl }))
      } catch {
        // Keep the package-photo placeholder when the protected image is unavailable.
      }
    }))

    return () => {
      controller.abort()
      objectUrls.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [result, token])

  function changeFilter(setter: (value: string) => void, value: string) {
    setter(value)
    setPage(1)
    setSelectedMedicine(null)
  }

  function clearFilters() {
    setName('')
    setCategory('')
    setCity('')
    setClinic('')
    setPage(1)
    setSelectedMedicine(null)
  }

  async function loadRequests() {
    setTab('requests')
    setRequestMessage('')
    setRequestsLoading(true)
    try {
      const response = await fetch(`${API_BASE_URL}/patient/requests`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      const data = await response.json() as MedicineRequest[] & { detail?: string }
      if (!response.ok) throw new Error(data.detail ?? 'Could not load your requests.')
      setRequests(data)
    } catch (cause) {
      setRequestMessage(cause instanceof Error ? cause.message : 'Could not load your requests.')
    } finally {
      setRequestsLoading(false)
    }
  }

  async function requestMedicine(item: Medicine) {
    const quantity = requestQuantity[item.medicine_id] ?? 1
    const needsPrescription = item.prescription_required === true
    const pickupAddress = pickupAddresses[item.medicine_id]?.trim() ?? ''
    if (!pickupAddress) {
      setRequestMessage('Enter the pickup/contact address for this request.')
      return
    }
    if (needsPrescription) {
      const prescription = prescriptionFiles[item.medicine_id]
      if (!prescription) {
        setRequestMessage('Upload a prescription before submitting this request.')
        return
      }
      setRequestBusy(item.medicine_id)
      setRequestMessage('')
      setFileError('')
      try {
        const formData = new FormData()
        formData.append('medicine_id', item.medicine_id)
        formData.append('requested_quantity', String(quantity))
        formData.append('pickup_address', pickupAddress)
        formData.append('file', prescription)
        const response = await fetch(`${API_BASE_URL}/patient/requests/with-prescription`, {
          method: 'POST',
          headers: { Authorization: ['Bearer', token].join(' ') },
          body: formData,
        })
        const data = await response.json() as MedicineRequest & { detail?: string }
        if (!response.ok) throw new Error(data.detail ?? 'Could not submit the medicine request.')
        setRequestMessage('Request and prescription submitted for pharmacist review.')
        setPrescriptionFiles((current) => ({ ...current, [item.medicine_id]: undefined }))
        setPickupAddresses((current) => ({ ...current, [item.medicine_id]: '' }))
        setSelectedMedicine(null)
        setDiscoveryRevision((current) => current + 1)
      } catch (cause) {
        setRequestMessage(cause instanceof Error ? cause.message : 'Could not submit request.')
      } finally {
        setRequestBusy(null)
      }
      return
    }
    setRequestBusy(item.medicine_id)
    setRequestMessage('')
    setFileError('')
    try {
      const response = await fetch(`${API_BASE_URL}/patient/requests`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ medicine_id: item.medicine_id, requested_quantity: quantity, pickup_address: pickupAddress }),
      })
      const data = await response.json() as MedicineRequest & { detail?: string }
      if (!response.ok) throw new Error(data.detail ?? 'Could not submit the medicine request.')

      const prescription = prescriptionFiles[item.medicine_id]
      if (needsPrescription && prescription) {
        const formData = new FormData()
        formData.append('file', prescription)
        try {
          const upload = await fetch(`${API_BASE_URL}/patient/requests/${data.id}/prescription`, {
            method: 'POST',
            headers: { Authorization: `Bearer ${token}` },
            body: formData,
          })
          const uploaded = await upload.json() as { detail?: string }
          if (!upload.ok) {
            setRequestMessage(`Request created, but the prescription could not be uploaded: ${uploaded.detail ?? 'Upload it from My Requests.'}`)
          } else {
            setRequestMessage('Request and prescription submitted for review.')
            setPrescriptionFiles((current) => ({ ...current, [item.medicine_id]: undefined }))
          }
        } catch {
          setRequestMessage('Request created, but the prescription could not be uploaded. Upload it from My Requests.')
        }
      } else if (needsPrescription) {
        setRequestMessage('Request created. An approved doctor prescription is required before pharmacist approval; upload it in My Requests.')
      } else {
        setRequestMessage(`Request submitted for ${data.requested_quantity} ${data.unit} of ${data.medicine_name}.`)
      }
      setPickupAddresses((current) => ({ ...current, [item.medicine_id]: '' }))
      setSelectedMedicine(null)
      setDiscoveryRevision((current) => current + 1)
    } catch (cause) {
      setRequestMessage(cause instanceof Error ? cause.message : 'Could not submit request.')
    } finally {
      setRequestBusy(null)
    }
  }

  function selectPrescription(file: File | undefined, key: string, target: 'new' | 'existing') {
    setFileError('')
    if (file && (file.size > 10 * 1024 * 1024 || !['application/pdf', 'image/jpeg', 'image/png'].includes(file.type))) {
      setFileError('Choose a PDF, JPEG, or PNG file up to 10 MB.')
      return
    }
    const setter = target === 'new' ? setPrescriptionFiles : setRequestFiles
    setter((current) => ({ ...current, [key]: file }))
  }

  async function uploadForRequest(item: MedicineRequest) {
    const file = requestFiles[item.id]
    if (!file) return
    setRequestBusy(item.id)
    setRequestMessage('')
    try {
      const formData = new FormData()
      formData.append('file', file)
      const response = await fetch(`${API_BASE_URL}/patient/requests/${item.id}/prescription`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      })
      const body = await response.json() as { detail?: string }
      if (!response.ok) throw new Error(body.detail ?? 'Could not upload prescription.')
      setRequestFiles((current) => ({ ...current, [item.id]: undefined }))
      await loadRequests()
      setRequestMessage('Prescription uploaded for pharmacist verification.')
    } catch (cause) {
      setRequestMessage(cause instanceof Error ? cause.message : 'Could not upload prescription.')
    } finally {
      setRequestBusy(null)
    }
  }

  async function openCheckout(item: MedicineRequest, pay = false) {
    setCheckoutBusy(item.id)
    setRequestMessage('')
    try {
      const response = await fetch(`${API_BASE_URL}/patient/checkout/${item.id}${pay ? '/demo-pay' : ''}`, {
        method: pay ? 'POST' : 'GET',
        headers: { Authorization: `Bearer ${token}` },
      })
      const body = await response.json() as Checkout & { detail?: string }
      if (!response.ok) throw new Error(body.detail ?? 'Could not open checkout.')
      setCheckouts((current) => ({ ...current, [item.id]: body }))
      if (pay) {
        setRequestMessage('Your demo payment was recorded. No real money was charged.')
        await loadRequests()
      }
    } catch (cause) {
      setRequestMessage(cause instanceof Error ? cause.message : 'Could not open checkout.')
    } finally {
      setCheckoutBusy(null)
    }
  }

  const filterActive = Boolean(name || category || city || clinic)

  return <div className="mt-8 text-left">
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3 border-b border-[#edf0ea] pb-5">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[.12em] text-[#71886d]">Patient medicine discovery</p>
        <h2 className="mt-1 text-2xl font-semibold tracking-tight">Find available medicines</h2>
        <p className="mt-1 text-sm text-[#718078]">Pharmacist-reviewed medicines from verified clinics.</p>
      </div>
      <button onClick={onLogout} className="rounded-full border border-[#dce4d9] px-4 py-2 text-sm font-semibold hover:border-[#174e3f]">Log out</button>
    </div>

    <div className="mb-6 flex flex-wrap gap-2">
      <button onClick={() => setTab('search')} className={`rounded-full px-4 py-2 text-sm font-semibold ${tab === 'search' ? 'bg-[#174e3f] text-white' : 'border border-[#dce4d9]'}`}>Find medicine</button>
      <button onClick={() => void loadRequests()} className={`rounded-full px-4 py-2 text-sm font-semibold ${tab === 'requests' ? 'bg-[#174e3f] text-white' : 'border border-[#dce4d9]'}`}>My Requests</button>
    </div>

    {tab === 'requests' ? <>
      {requestMessage && <p role="status" className="mb-4 rounded-xl bg-[#f5f7f2] px-4 py-3 text-sm">{requestMessage}</p>}
      {fileError && <p role="alert" className="mb-4 text-sm text-red-700">{fileError}</p>}
      {requestsLoading ? <p className="py-10 text-center text-sm text-[#718078]">Loading your requests…</p> : requests.length ? <div className="space-y-3">
        {requests.map((item) => {
          const checkout = checkouts[item.id]
          const paymentStatus = checkout?.payment_status ?? item.payment_status
          const free = Number(item.patient_price_snapshot) === 0
          return <article key={item.id} className="rounded-2xl border border-[#e4e9e0] bg-white p-4 sm:p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="font-semibold">{item.medicine_name}</h3>
                <p className="mt-1 text-sm text-[#718078]">Common use: {categoryLabel(item.common_use_category)}</p>
                <p className="mt-1 text-sm text-[#718078]">{item.requested_quantity} {item.unit} requested · {item.clinic_name}</p>
                {item.pickup_address && <p className="mt-1 text-sm text-[#718078]">Pickup address: {item.pickup_address}</p>}
                <p className="mt-1 text-xs text-[#87938a]">Requested {new Date(item.created_at).toLocaleString()}</p>
                <p className="mt-3 text-sm">Prescription: {item.prescription_required === false ? 'Not required' : (item.prescription_status ?? 'Approved doctor prescription required')}</p>
                {item.prescription_required === true && (!item.prescription_status || item.prescription_status === 'REJECTED') && <div className="mt-3 flex flex-wrap items-center gap-2">
                  <input type="file" accept="application/pdf,image/jpeg,image/png" aria-label="Choose prescription file" onChange={(event) => selectPrescription(event.target.files?.[0], item.id, 'existing')} className="max-w-full text-xs" />
                  <button disabled={!requestFiles[item.id] || requestBusy === item.id} onClick={() => void uploadForRequest(item)} className={`${buttonClass} px-3 py-2 text-xs`}>Upload prescription</button>
                  {requestFiles[item.id] && <span className="text-xs text-[#718078]">{requestFiles[item.id]?.name}</span>}
                </div>}
                {item.patient_price_snapshot !== null && <p className="mt-3 text-sm">
                  Price: <span className="font-semibold">{free ? 'Free' : `₹${item.patient_price_snapshot} each`}</span>
                  {' · '}Payment: <span className="font-semibold">{free ? 'Free' : paymentStatus ?? 'Not started'}</span>
                </p>}
                {item.patient_price_snapshot === null && <p className="mt-3 text-sm text-[#718078]">Price was not configured for this request.</p>}
                {item.status === 'APPROVED' && <div className="mt-3 rounded-xl border border-[#dce9d6] bg-[#f5f9f2] p-3 text-sm">
                  <p className="flex items-center gap-2 font-semibold text-[#174e3f]"><PackageCheck size={16} /> Ready for pickup</p>
                  <p className="mt-1">Reserved: {item.requested_quantity} {item.unit}</p>
                  {item.pickup_code && <p>Pickup code: <span className="font-mono font-bold tracking-wider">{item.pickup_code}</span></p>}
                  {item.patient_price_snapshot === null
                    ? <p className="mt-2 text-amber-800">Checkout is unavailable because no price was configured.</p>
                    : <button disabled={checkoutBusy === item.id} onClick={() => void openCheckout(item)} className={`${buttonClass} mt-3 px-3 py-2 text-xs`}>
                      {checkout?.is_free ? 'Free — no payment required' : paymentStatus === 'PAID' ? 'Payment recorded' : 'View payment details'}
                    </button>}
                  {checkout && <div className="mt-3 rounded-xl border border-[#dce9d6] bg-white p-3">
                    <p className="font-semibold">Checkout details</p>
                    <p className="mt-1">{checkout.quantity} {checkout.unit} · {checkout.is_free ? 'Free' : `₹${checkout.amount} total`}</p>
                    <p>Payment status: {checkout.is_free ? 'Free — no payment required' : checkout.payment_status}</p>
                    {!checkout.is_free && checkout.payment_status !== 'PAID' && <button disabled={checkoutBusy === item.id} onClick={() => void openCheckout(item, true)} className={`${buttonClass} mt-3 px-3 py-2 text-xs`}>
                      {checkoutBusy === item.id ? 'Processing…' : 'Complete demo payment'}
                    </button>}
                    <p className="mt-2 text-xs text-[#718078]">Prototype payment flow; no real money is charged.</p>
                  </div>}
                </div>}
                {item.status === 'FULFILLED' && <div className="mt-3 rounded-xl bg-[#f5f7f2] p-3 text-sm">
                  <p className="font-semibold">Fulfilled</p>
                  <p className="mt-1">{item.requested_quantity} {item.unit} dispensed{item.fulfilled_at ? ` · ${new Date(item.fulfilled_at).toLocaleString()}` : ''}</p>
                </div>}
              </div>
              <span className="h-fit rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold">{item.status === 'APPROVED' ? 'READY FOR PICKUP' : item.status.replaceAll('_', ' ')}</span>
            </div>
          </article>
        })}
      </div> : <div className="rounded-2xl border border-dashed border-[#dce4d9] px-5 py-9 text-center text-sm text-[#718078]">No medicine requests yet.</div>}
    </> : <>
      <p className="mb-5 max-w-3xl text-sm leading-6 text-[#718078]">Browse available stock reviewed by clinic pharmacists. Common-use categories are not diagnoses or treatment recommendations.</p>
      <div className="grid gap-3 rounded-2xl border border-[#e4e9e0] bg-[#fbfcfa] p-4 sm:grid-cols-2 lg:grid-cols-3">
        <label className="relative sm:col-span-2 lg:col-span-3">
          <Search size={17} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#87938a]" />
          <input className={`${inputClass} pl-10`} value={name} onChange={(event) => changeFilter(setName, event.target.value)} placeholder="Search medicine name" aria-label="Search medicine name" />
        </label>
        <label className="text-xs font-semibold text-[#55704f]">Common-use category
          <select className={`${inputClass} mt-1.5`} value={category} onChange={(event) => changeFilter(setCategory, event.target.value)}>
            <option value="">All categories</option>
            {Object.entries(categoryLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label className="text-xs font-semibold text-[#55704f]">Clinic city
          <input className={`${inputClass} mt-1.5`} value={city} onChange={(event) => changeFilter(setCity, event.target.value)} placeholder="Filter by city" aria-label="Filter by clinic city" />
        </label>
        <label className="text-xs font-semibold text-[#55704f]">Clinic
          <input className={`${inputClass} mt-1.5`} value={clinic} onChange={(event) => changeFilter(setClinic, event.target.value)} placeholder="Filter by clinic name" aria-label="Filter by clinic name" />
        </label>
        <div className="flex items-end justify-between gap-3 sm:col-span-2 lg:col-span-3">
          <p className="rounded-full bg-[#edf5e9] px-3 py-2 text-xs font-semibold text-[#416b43]">Availability: Available now</p>
          <button onClick={clearFilters} disabled={!filterActive} className="rounded-full border border-[#dce4d9] px-4 py-2 text-sm font-semibold text-[#55704f] disabled:opacity-50">Clear filters</button>
        </div>
      </div>

      {error && <p role="alert" className="mt-5 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
      {loading ? <p className="py-10 text-center text-sm text-[#718078]">Looking for available medicine…</p> : result && <>
        <div className="mb-3 mt-6 flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-medium text-[#718078]">{result.total} {result.total === 1 ? 'medicine' : 'medicines'} available</p>
          <p className="flex items-center gap-1.5 text-xs text-[#718078]"><ShieldCheck size={14} /> Approved donations · verified clinics · in-date stock</p>
        </div>
        {result.items.length ? <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {result.items.map((item) => {
            const image = item.images[0]
            const imageKey = image ? `${item.medicine_id}:${image.image_url}` : ''
            const imageUrl = imageUrls[imageKey]
            const prescription = item.prescription_required === true
            return <article key={item.medicine_id} className="flex flex-col overflow-hidden rounded-2xl border border-[#e4e9e0] bg-white shadow-sm transition hover:-translate-y-0.5 hover:shadow-md">
              <div className="relative isolate flex h-44 w-full shrink-0 items-center justify-center overflow-hidden bg-[#f3f6f1]">
                {imageUrl ? <img className="block max-h-full max-w-full object-contain p-3" src={imageUrl} alt={`${item.medicine_name} package`} /> : <div className="flex flex-col items-center gap-2 text-[#9aa79a]"><ImageOff size={30} /><span className="text-xs">Package photo unavailable</span></div>}
              </div>
              <div className="relative z-0 min-w-0 flex-1 bg-white p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className="truncate text-lg font-semibold">{item.medicine_name}</h3>
                    <p className="mt-1 text-sm text-[#55704f]">Common use: {categoryLabel(item.common_use_category)}</p>
                  </div>
                  <span className="shrink-0 rounded-full bg-[#edf5e9] px-2.5 py-1 text-xs font-semibold text-[#416b43]">Available</span>
                </div>
                <p className="mt-3 flex items-center gap-1.5 text-sm text-[#718078]"><MapPin size={15} />{item.clinic_name} · {item.clinic_city}</p>
                <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                  <p className="flex items-center gap-1.5 text-[#718078]"><CalendarDays size={15} />Expires {new Date(`${item.expiry_date}T00:00:00`).toLocaleDateString()}</p>
                  <p className="text-right font-medium">{item.availability} {item.availability_unit} available</p>
                </div>
                <p className="mt-3 text-sm font-semibold">{priceLabel(item)}{Number(item.patient_price) > 0 ? ' each' : ''}</p>
                {prescription && <p className="mt-2 text-xs font-medium text-amber-800">Doctor prescription required</p>}
                <button onClick={() => setSelectedMedicine(item)} className={`${buttonClass} mt-4 w-full`}>View details / Request medicine</button>
              </div>
            </article>
          })}
        </div> : <div className="rounded-2xl border border-dashed border-[#dce4d9] px-5 py-10 text-center">
          <h3 className="font-semibold">{result.total === 0 ? 'No available medicines found' : 'No medicines on this page'}</h3>
          <p className="mt-1 text-sm text-[#87938a]">{result.total === 0 ? 'There are currently no medicines matching these filters.' : 'Go back to a previous page to view the available results.'}</p>
          {result.total === 0 && filterActive && <button onClick={clearFilters} className="mt-4 rounded-full border border-[#dce4d9] px-4 py-2 text-sm font-semibold">Clear filters</button>}
          {result.total > 0 && page > 1 && <button onClick={() => setPage(page - 1)} className="mt-4 rounded-full border border-[#dce4d9] px-4 py-2 text-sm font-semibold">Previous page</button>}
        </div>}
        {result.total > result.page_size && <div className="mt-5 flex items-center justify-between">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="rounded-full border border-[#dce4d9] px-4 py-2 text-sm disabled:opacity-40">Previous</button>
          <span className="text-sm text-[#718078]">Page {page} of {Math.ceil(result.total / result.page_size)}</span>
          <button disabled={page >= Math.ceil(result.total / result.page_size)} onClick={() => setPage(page + 1)} className="rounded-full border border-[#dce4d9] px-4 py-2 text-sm disabled:opacity-40">Next</button>
        </div>}
      </>}
    </>}

    {tab === 'search' && requestMessage && <p role="status" className="mt-4 rounded-xl bg-[#f5f7f2] px-4 py-3 text-sm">{requestMessage}</p>}

    {selectedMedicine && <div className="fixed inset-0 z-50 flex items-center justify-center overflow-hidden bg-[#153b31]/45 p-3 sm:p-4" onMouseDown={(event) => {
      if (event.target === event.currentTarget) setSelectedMedicine(null)
    }}>
      <section role="dialog" aria-modal="true" aria-labelledby="medicine-detail-title" className="flex max-h-[calc(100dvh-1.5rem)] w-full max-w-2xl flex-col overflow-hidden rounded-3xl bg-white shadow-2xl sm:max-h-[calc(100dvh-2rem)]">
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-[#edf0ea] p-5 sm:p-7">
          <div className="min-w-0"><p className="text-xs font-semibold uppercase tracking-[.12em] text-[#71886d]">Medicine details</p><h2 id="medicine-detail-title" className="mt-1 break-words text-2xl font-semibold">{selectedMedicine.medicine_name}</h2></div>
          <button onClick={() => setSelectedMedicine(null)} aria-label="Close medicine details" className="shrink-0 rounded-full border border-[#dce4d9] p-2"><X size={18} /></button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 pb-5 sm:px-7 sm:pb-7">
          {(() => {
          const image = selectedMedicine.images[0]
          const imageKey = image ? `${selectedMedicine.medicine_id}:${image.image_url}` : ''
          const imageUrl = imageUrls[imageKey]
          const prescription = selectedMedicine.prescription_required === true
          const quantity = requestQuantity[selectedMedicine.medicine_id] ?? 1
          return <>
            <div className="mt-5 flex h-48 w-full shrink-0 items-center justify-center overflow-hidden rounded-2xl bg-[#f3f6f1] sm:h-64">
              {imageUrl ? <img className="block h-full w-full object-contain p-4" src={imageUrl} alt={`${selectedMedicine.medicine_name} package`} /> : <div className="flex flex-col items-center gap-2 text-[#9aa79a]"><ImageOff size={34} /><span className="text-sm">Package photo unavailable</span></div>}
            </div>
            <div className="mt-5 min-w-0">
              <div className="grid min-w-0 grid-cols-1 gap-3 min-[420px]:grid-cols-2">
                <p className="min-w-0 break-words"><span className="text-sm text-[#718078]">Common use</span><br /><span className="font-medium">{categoryLabel(selectedMedicine.common_use_category)}</span></p>
                <p className="min-w-0 break-words"><span className="text-sm text-[#718078]">Expiry date</span><br /><span className="font-medium">{new Date(`${selectedMedicine.expiry_date}T00:00:00`).toLocaleDateString()}</span></p>
                <p className="min-w-0 break-words"><span className="text-sm text-[#718078]">Availability</span><br /><span className="font-medium">{selectedMedicine.availability} {selectedMedicine.availability_unit} available</span></p>
                <p className="min-w-0 break-words"><span className="text-sm text-[#718078]">Price</span><br /><span className="font-medium">{priceLabel(selectedMedicine)}{Number(selectedMedicine.patient_price) > 0 ? ' each' : ''}</span></p>
                <p className="min-w-0 break-words min-[420px]:col-span-2"><span className="text-sm text-[#718078]">Clinic</span><br /><span className="font-medium">{selectedMedicine.clinic_name} · {selectedMedicine.clinic_city}</span></p>
              </div>
              <div className={`mt-4 rounded-xl p-3 text-sm ${prescription ? 'bg-amber-50 text-amber-900' : 'bg-[#edf5e9] text-[#416b43]'}`}>
                {prescription ? <><p className="font-semibold">Approved doctor prescription required</p><p className="mt-1 break-words">This category requires a prescription verified by the clinic before the request can be approved. Common-use categories are not diagnoses.</p></> : <><p className="font-semibold">Prescription not required for a direct request</p><p className="mt-1 break-words">This common-use category is not a diagnosis or treatment recommendation.</p></>}
              </div>
            </div>
            <div className="mt-5 min-w-0">
              <label className="block text-sm font-medium">Pickup/contact address
                <textarea className={`${inputClass} mt-2 min-h-20 resize-y`} value={pickupAddresses[selectedMedicine.medicine_id] ?? ''} maxLength={500} required aria-label="Pickup/contact address" onChange={(event) => {
                  setPickupAddresses((current) => ({
                    ...current,
                    [selectedMedicine.medicine_id]: event.target.value,
                  }))
                  setRequestMessage('')
                }} placeholder="Where should the clinic prepare this request for pickup?" />
                <span className="mt-1 block break-words text-xs font-normal text-[#718078]">This address is attached to this request and visible only to you and the responsible clinic.</span>
              </label>
              {prescription && <div className="mt-4">
                <p className="mb-2 break-words text-sm font-medium">Prescription file <span className="text-red-700">Required</span></p>
                <label htmlFor={`prescription-upload-${selectedMedicine.medicine_id}`} className="flex min-h-32 cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-[#b9cbb5] bg-[#fbfcfa] px-4 py-5 text-center transition hover:border-[#719a6c] hover:bg-[#f5f8f3] focus-within:ring-2 focus-within:ring-[#719a6c]/25">
                  <input id={`prescription-upload-${selectedMedicine.medicine_id}`} className="sr-only" type="file" accept="application/pdf,image/jpeg,image/png" required onChange={(event) => selectPrescription(event.target.files?.[0], selectedMedicine.medicine_id, 'new')} />
                  <Upload size={22} aria-hidden="true" className="mb-2 text-[#55704f]" />
                  <span className="max-w-full break-all text-sm font-semibold text-[#174e3f]">{prescriptionFiles[selectedMedicine.medicine_id]?.name ?? 'Click to upload prescription'}</span>
                  <span className="mt-1 text-xs text-[#718078]">PDF, JPG or PNG • Max 10 MB</span>
                </label>
                {fileError && <p role="alert" className="mt-2 break-words text-sm text-red-700">{fileError}</p>}
              </div>}
              {requestMessage && <p role="alert" className="mt-3 break-words rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{requestMessage}</p>}
              {fileError && <p role="alert" className="mt-3 break-words text-sm text-red-700">{fileError}</p>}
              <div className="mt-5 flex flex-wrap items-end justify-between gap-4">
                <label className="text-sm font-medium">Request quantity
                  <input className="mt-1 block w-32 rounded-xl border border-[#dce4d9] bg-white px-3 py-2.5" type="number" min="1" max={selectedMedicine.availability} value={quantity} onChange={(event) => setRequestQuantity((current) => ({
                    ...current,
                    [selectedMedicine.medicine_id]: Math.max(1, Math.min(selectedMedicine.availability, Number(event.target.value))),
                  }))} />
                </label>
                <button disabled={requestBusy === selectedMedicine.medicine_id || selectedMedicine.availability < 1} onClick={() => void requestMedicine(selectedMedicine)} className={buttonClass}>
                  {requestBusy === selectedMedicine.medicine_id ? 'Submitting…' : 'Request medicine'}
                </button>
              </div>
            </div>
          </>
          })()}
        </div>
      </section>
    </div>}
  </div>
}
