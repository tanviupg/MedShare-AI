import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowLeft, Heart, LogOut, Plus, ShieldCheck } from 'lucide-react'
import { API_BASE_URL } from './config'
import PharmacistReview from './PharmacistReview'
import PharmacistInventory from './PharmacistInventory'
import PharmacistExpiryWaste from './PharmacistExpiryWaste'
import PatientDiscovery from './PatientDiscovery'
import PharmacistRequests from './PharmacistRequests'
import PharmacistPrescriptions from './PharmacistPrescriptions'
import PharmacistDispensing from './PharmacistDispensing'
import Notifications from './Notifications'
import PharmacistDashboard from './PharmacistDashboard'
import AdminClinicVerification from './AdminClinicVerification'
import AdminDashboard from './AdminDashboard'
import { safeApiErrorMessage } from './apiErrors.mjs'

type Role = 'DONOR' | 'PATIENT' | 'CLINIC_PHARMACIST' | 'ADMIN'
type SignupRole = Exclude<Role, 'ADMIN'>
type User = { id: string; name: string; email: string; role: Role; clinic_profile?: { clinic_name: string; verification_status: string; verification_rejection_reason: string | null } | null }
type AuthResult = { access_token: string; user: User }
type DonationStatus = 'PENDING_REVIEW' | 'APPROVED' | 'REJECTED' | 'CANCELLED'
type Donation = { id: string; status: DonationStatus; created_at: string }
type ClinicTab = 'Overview' | 'Donations' | 'Inventory' | 'Patient Requests' | 'Prescriptions' | 'Waste Management' | 'Notifications'
type AdminTab = 'Dashboard' | 'Clinic Verification'
const clinicTabs: ClinicTab[] = ['Overview', 'Donations', 'Inventory', 'Patient Requests', 'Prescriptions', 'Waste Management', 'Notifications']

const roleLabels: Record<Role, string> = { DONOR: 'Donor', PATIENT: 'Patient', CLINIC_PHARMACIST: 'Clinic / Pharmacist', ADMIN: 'Platform administrator' }
const successText: Record<Role, string> = { DONOR: 'Donor dashboard', PATIENT: 'Patient authentication successful.', CLINIC_PHARMACIST: 'Clinic/Pharmacist authentication successful.', ADMIN: 'Platform administrator' }
const inputClass = 'mt-1.5 w-full rounded-xl border border-[#dce4d9] bg-white px-3.5 py-3 text-sm outline-none transition focus:border-[#719a6c] focus:ring-2 focus:ring-[#719a6c]/15'
const statusStyle: Record<DonationStatus, string> = { PENDING_REVIEW: 'bg-amber-50 text-amber-800', APPROVED: 'bg-emerald-50 text-emerald-800', REJECTED: 'bg-red-50 text-red-700', CANCELLED: 'bg-slate-100 text-slate-600' }
const donorStatus: Record<DonationStatus, string> = { PENDING_REVIEW: 'Under clinic verification', APPROVED: 'Approved', REJECTED: 'Rejected', CANCELLED: 'Cancelled' }

function PhotoPreview({ file, alt }: { file: File; alt: string }) {
  const [url, setUrl] = useState('')
  useEffect(() => {
    const previewUrl = URL.createObjectURL(file)
    setUrl(previewUrl)
    return () => URL.revokeObjectURL(previewUrl)
  }, [file])
  return <img src={url} alt={alt} className="size-20 rounded-lg bg-[#f7f8f5] object-cover" />
}

function App() {
  const [mode, setMode] = useState<'login' | 'signup'>('signup')
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState(() => localStorage.getItem('medshare_token'))
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [role, setRole] = useState<SignupRole>('DONOR')
  const [donations, setDonations] = useState<Donation[]>([])
  const [view, setView] = useState<'list' | 'create' | 'submitted'>('list')
  const [donationError, setDonationError] = useState('')
  const [donationBusy, setDonationBusy] = useState(false)
  const [operationsRevision, setOperationsRevision] = useState(0)
  const [clinicTab, setClinicTab] = useState<ClinicTab>('Overview')
  const [adminTab, setAdminTab] = useState<AdminTab>('Dashboard')

  useEffect(() => {
    if (!token) return
    fetch(`${API_BASE_URL}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => response.ok ? response.json() as Promise<User> : null)
      .then((current) => { if (current) setUser(current); else { localStorage.removeItem('medshare_token'); setToken(null) } })
      .catch(() => setError('Could not connect to the authentication service.'))
  }, [token])

  useEffect(() => {
    if (!token || user?.role !== 'DONOR') return
    fetch(`${API_BASE_URL}/donations/mine`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => {
        if (!response.ok) throw new Error('Could not load your donations.')
        setDonations(await response.json() as Donation[])
      }).catch((reason) => setDonationError(reason instanceof Error ? reason.message : 'Could not load your donations.'))
  }, [token, user?.role])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setBusy(true)
    const data = new FormData(event.currentTarget)
    const payload: Record<string, unknown> = { email: data.get('email'), password: data.get('password') }
    if (mode === 'signup') {
      payload.name = data.get('name')
      payload.role = role
      payload.phone = data.get('phone') || null
      payload.city = data.get('city') || null
      if (role === 'CLINIC_PHARMACIST') payload.clinic_profile = {
        clinic_name: data.get('clinic_name'), address: data.get('address'), city: data.get('clinic_city'),
        license_number: data.get('license_number') || null, contact_number: data.get('contact_number') || null,
      }
    }
    try {
      const response = await fetch(`${API_BASE_URL}/auth/${mode}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      const result = await response.json() as AuthResult & { detail?: string }
      if (!response.ok) throw new Error(safeApiErrorMessage(result, 'Authentication failed'))
      localStorage.setItem('medshare_token', result.access_token)
      setToken(result.access_token)
      setUser(result.user)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not connect to the authentication service.') }
    finally { setBusy(false) }
  }

  function logout() {
    localStorage.removeItem('medshare_token')
    setToken(null)
    setUser(null)
    setMode('login')
    setView('list')
    setDonations([])
    setClinicTab('Overview')
    setAdminTab('Dashboard')
  }

  async function submitDonation(event: FormEvent<HTMLFormElement>, selectedPhotos: File[]) {
    event.preventDefault()
    if (!token) return
    setDonationError('')
    setDonationBusy(true)
    try {
      const retry = sessionStorage.getItem('medshare_donation_retry')
      const pending = retry ? JSON.parse(retry) as { donation: Donation; payload: { pickup_address: FormDataEntryValue | null; donor_expiry_date: FormDataEntryValue | null }; uploaded: string[]; failed: string[] } : null
      const chosenFiles = selectedPhotos.filter((file) => file.size > 0)
      const files = chosenFiles
      if (!files.length) throw new Error('Choose at least one failed medicine photo to retry.')
      const form = new FormData(event.currentTarget)
      const payload = { pickup_address: form.get('pickup_address'), donor_expiry_date: form.get('donor_expiry_date') || null }
      let donation: Donation
      if (pending) donation = pending.donation
      else {
        const response = await fetch(`${API_BASE_URL}/donations`, { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
        const result = await response.json() as Donation & { detail?: string }
        if (!response.ok) throw new Error(safeApiErrorMessage(result, 'Could not submit donation.'))
        donation = result
      }
      const uploaded: string[] = []
      const failed: string[] = []
      for (const [index, file] of files.entries()) {
        const images = new FormData()
        images.append('files', file)
        try {
          const finalPhoto = index === files.length - 1 && failed.length === 0
          const upload = await fetch(`${API_BASE_URL}/donations/${donation.id}/images?finalize=${finalPhoto}`, { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: images })
          if (!upload.ok) {
            if (pending && upload.status === 409) { uploaded.push(file.name); continue }
            throw new Error(safeApiErrorMessage(await upload.json(), 'Photo upload failed.'))
          }
          uploaded.push(file.name)
        } catch { failed.push(file.name) }
      }
      if (failed.length) {
        setDonations((current) => [donation, ...current.filter((item) => item.id !== donation.id)])
        sessionStorage.setItem('medshare_donation_retry', JSON.stringify({ donation, payload: pending?.payload ?? payload, uploaded: [...(pending?.uploaded ?? []), ...uploaded], failed }))
        setDonationError(`Donation ${donation.id} was created. Uploaded: ${uploaded.join(', ') || 'none'}. Failed: ${failed.join(', ')}. Choose the failed photos again to retry; the donation will not be recreated.`)
        setView('create')
        return
      }
      const refresh = await fetch(`${API_BASE_URL}/donations/${donation.id}`, { headers: { Authorization: `Bearer ${token}` } })
      if (refresh.ok) Object.assign(donation, await refresh.json())
      sessionStorage.removeItem('medshare_donation_retry')
      setDonations((current) => [donation, ...current.filter((item) => item.id !== donation.id)])
      setView('submitted')
    } catch (reason) { setDonationError(reason instanceof Error ? reason.message : 'Could not submit donation.') }
    finally { setDonationBusy(false) }
  }

  return <main className="min-h-screen bg-[#f7f8f5] px-5 py-10 text-[#18372e] sm:py-16">
    <div className={`mx-auto w-full ${user?.role === 'CLINIC_PHARMACIST' || user?.role === 'PATIENT' || user?.role === 'ADMIN' ? 'max-w-7xl' : 'max-w-xl'}`}>
      <a className="mx-auto mb-9 flex w-fit items-center gap-2.5" href="#home" aria-label="MedShare AI home">
        <span className="grid size-10 place-items-center rounded-2xl bg-[#174e3f] text-white"><Heart size={19} strokeWidth={2.5} /></span>
        <span className="text-lg font-semibold tracking-tight">medshare<span className="text-[#719a6c]">ai</span></span>
      </a>
      <section className={`rounded-[2rem] border border-[#e4e9e0] bg-white shadow-[0_24px_80px_-48px_rgba(27,63,49,.3)] ${user?.role === 'CLINIC_PHARMACIST' || user?.role === 'ADMIN' ? 'p-4 sm:p-7' : user?.role === 'PATIENT' ? 'p-4 sm:p-8' : 'p-6 sm:p-9'}`}>
        <div className="mb-7 flex items-center gap-2 text-xs font-semibold uppercase tracking-[.12em] text-[#71886d]"><ShieldCheck size={16} /> Secure account access</div>
        {user ? <div>
          {user.role === 'CLINIC_PHARMACIST' && token ? <>
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#edf0ea] pb-3"><p className="text-sm text-[#718078]">Signed in as <b className="text-[#18372e]">{user.name}</b> · {user.clinic_profile?.clinic_name || roleLabels[user.role]}</p><button onClick={logout} className="rounded-full px-3 py-2 text-sm font-medium text-[#718078] hover:bg-[#f5f7f2] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#719a6c]">Log out</button></div>
            <div className={`mt-4 rounded-xl p-4 text-sm ${user.clinic_profile?.verification_status === 'VERIFIED' ? 'bg-[#edf5e9] text-[#416b43]' : user.clinic_profile?.verification_status === 'REJECTED' ? 'bg-red-50 text-red-800' : 'bg-amber-50 text-amber-900'}`}>
              <p>Clinic verification: <b>{user.clinic_profile?.verification_status ?? 'PENDING'}</b></p>
              {user.clinic_profile?.verification_status === 'PENDING' && <p className="mt-1">Your clinic profile is waiting for a platform review.</p>}
              {user.clinic_profile?.verification_rejection_reason && <p className="mt-1">Review reason: {user.clinic_profile.verification_rejection_reason}</p>}
            </div>
            <nav aria-label="Clinic operations" role="tablist" className="sticky top-0 z-10 mt-3 flex flex-wrap gap-1 border-b border-[#edf0ea] bg-white/95 py-2 text-xs font-semibold text-[#55704f]">
              {clinicTabs.map((tab, index) => <button key={tab} id={`clinic-tab-${index}`} type="button" role="tab" aria-selected={clinicTab === tab} aria-controls={`clinic-panel-${index}`} tabIndex={clinicTab === tab ? 0 : -1} onClick={() => setClinicTab(tab)} onKeyDown={(event) => {
                if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
                  event.preventDefault()
                  const direction = event.key === 'ArrowRight' ? 1 : -1
                  const nextIndex = (index + direction + clinicTabs.length) % clinicTabs.length
                  setClinicTab(clinicTabs[nextIndex])
                  document.getElementById(`clinic-tab-${nextIndex}`)?.focus()
                }
              }} className={`rounded-full px-3 py-2 transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#719a6c] ${clinicTab === tab ? 'bg-[#e7efe2] text-[#174e3f]' : 'hover:bg-[#f5f8f3]'}`}>{tab}</button>)}
            </nav>
            <div id="clinic-panel-0" role="tabpanel" aria-labelledby="clinic-tab-0" hidden={clinicTab !== 'Overview'}><PharmacistDashboard token={token} refreshKey={operationsRevision} onNavigate={setClinicTab} /></div>
            <div id="clinic-panel-1" role="tabpanel" aria-labelledby="clinic-tab-1" hidden={clinicTab !== 'Donations'}><PharmacistReview token={token} onLogout={logout} onReviewComplete={() => setOperationsRevision((revision) => revision + 1)} /></div>
            <div id="clinic-panel-2" role="tabpanel" aria-labelledby="clinic-tab-2" hidden={clinicTab !== 'Inventory'}><PharmacistInventory token={token} refreshKey={operationsRevision} onPricingUpdated={() => setOperationsRevision((revision) => revision + 1)} /></div>
            <div id="clinic-panel-3" role="tabpanel" aria-labelledby="clinic-tab-3" hidden={clinicTab !== 'Patient Requests'}><PharmacistRequests token={token} /><PharmacistDispensing token={token} /></div>
            <div id="clinic-panel-4" role="tabpanel" aria-labelledby="clinic-tab-4" hidden={clinicTab !== 'Prescriptions'}><PharmacistPrescriptions token={token} /></div>
            <div id="clinic-panel-5" role="tabpanel" aria-labelledby="clinic-tab-5" hidden={clinicTab !== 'Waste Management'}><PharmacistExpiryWaste token={token} /></div>
            <div id="clinic-panel-6" role="tabpanel" aria-labelledby="clinic-tab-6" hidden={clinicTab !== 'Notifications'}><Notifications token={token} standalone /></div>
          </> : user.role === 'ADMIN' && token ? <><div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#edf0ea] pb-3"><p className="text-sm text-[#718078]">Signed in as <b className="text-[#18372e]">{user.name}</b> · {roleLabels[user.role]}</p><button onClick={logout} className="rounded-full px-3 py-2 text-sm font-medium text-[#718078] hover:bg-[#f5f7f2]">Log out</button></div><div className="mt-4 flex justify-end"><Notifications token={token} /></div><><nav aria-label="Admin sections" className="mt-4 flex flex-wrap gap-2 border-b border-[#edf0ea] pb-3"><button type="button" aria-current={adminTab === "Dashboard" ? "page" : undefined} onClick={() => setAdminTab("Dashboard")} className={adminTab === "Dashboard" ? "rounded-full bg-[#e7efe2] px-4 py-2 text-sm font-semibold text-[#174e3f]" : "rounded-full px-4 py-2 text-sm font-semibold text-[#718078]"}>Dashboard</button><button type="button" aria-current={adminTab === "Clinic Verification" ? "page" : undefined} onClick={() => setAdminTab("Clinic Verification")} className={adminTab === "Clinic Verification" ? "rounded-full bg-[#e7efe2] px-4 py-2 text-sm font-semibold text-[#174e3f]" : "rounded-full px-4 py-2 text-sm font-semibold text-[#718078]"}>Clinic Verification</button></nav>{adminTab === "Dashboard" ? <AdminDashboard token={token} /> : <AdminClinicVerification token={token} />}</></> : user.role === 'DONOR' ? <><div className="text-center"><span className="mx-auto grid size-14 place-items-center rounded-2xl bg-[#e7efe2] text-[#63855b]"><Heart size={24} /></span><h1 className="mt-5 text-2xl font-semibold tracking-tight">{successText[user.role]}</h1><p className="mt-2 text-sm text-[#718078]">Signed in as {user.name} Â· {roleLabels[user.role]}</p></div>{token && <div className="mt-4 flex justify-end"><Notifications token={token} /></div>}<DonorDashboard donations={donations} view={view} setView={setView} error={donationError} busy={donationBusy} onSubmit={submitDonation} onLogout={logout} /></> : <><div className="text-center"><span className="mx-auto grid size-14 place-items-center rounded-2xl bg-[#e7efe2] text-[#63855b]"><Heart size={24} /></span><h1 className="mt-5 text-2xl font-semibold tracking-tight">{successText[user.role]}</h1><p className="mt-2 text-sm text-[#718078]">Signed in as {user.name} Â· {roleLabels[user.role]}</p></div>{token && <div className="mt-4 flex justify-end"><Notifications token={token} /></div>}{token ? <PatientDiscovery token={token} onLogout={logout} /> : null}</>}
        </div> : <>
          <h1 className="text-2xl font-semibold tracking-tight">{mode === 'signup' ? 'Join MedShare AI' : 'Welcome back'}</h1>
          <p className="mt-2 text-sm leading-6 text-[#718078]">{mode === 'signup' ? 'Create a secure account to get started.' : 'Sign in to your MedShare AI account.'}</p>
          <form className="mt-6 space-y-4" onSubmit={submit}>
            {mode === 'signup' && <><label className="block text-sm font-medium">Full name<input className={inputClass} name="name" autoComplete="name" required minLength={1} maxLength={120} /></label><label className="block text-sm font-medium">I am a<select className={inputClass} value={role} onChange={(event) => setRole(event.target.value as SignupRole)}><option value="DONOR">Donor</option><option value="PATIENT">Patient</option><option value="CLINIC_PHARMACIST">Clinic / Pharmacist</option></select></label></>}
            <label className="block text-sm font-medium">Email address<input className={inputClass} name="email" type="email" autoComplete="email" required maxLength={320} /></label>
            <label className="block text-sm font-medium">Password<input className={inputClass} name="password" type="password" autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} required minLength={mode === 'signup' ? 8 : 1} maxLength={72} /></label>
            {mode === 'signup' && <><div className="grid gap-4 sm:grid-cols-2"><label className="block text-sm font-medium">Phone (optional)<input className={inputClass} name="phone" type="tel" maxLength={40} /></label><label className="block text-sm font-medium">City (optional)<input className={inputClass} name="city" maxLength={120} /></label></div>{role === 'CLINIC_PHARMACIST' && <div className="space-y-4 rounded-2xl bg-[#f5f7f2] p-4"><p className="text-sm font-semibold">Clinic details</p><label className="block text-sm font-medium">Clinic name<input className={inputClass} name="clinic_name" required maxLength={160} /></label><label className="block text-sm font-medium">Address<input className={inputClass} name="address" required maxLength={500} /></label><div className="grid gap-4 sm:grid-cols-2"><label className="block text-sm font-medium">Clinic city<input className={inputClass} name="clinic_city" required maxLength={120} /></label><label className="block text-sm font-medium">License number (optional)<input className={inputClass} name="license_number" maxLength={100} /></label></div><label className="block text-sm font-medium">Contact number (optional)<input className={inputClass} name="contact_number" maxLength={40} /></label></div>}</>}
            {error && <p role="alert" className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
            <button disabled={busy} className="w-full rounded-full bg-[#174e3f] px-5 py-3.5 text-sm font-semibold text-white transition hover:bg-[#103d31] disabled:opacity-60">{busy ? 'Please waitâ€¦' : mode === 'signup' ? 'Create account' : 'Log in'}</button>
          </form>
          <p className="mt-6 text-center text-sm text-[#718078]">{mode === 'signup' ? 'Already have an account?' : 'New to MedShare AI?'} <button onClick={() => { setMode(mode === 'signup' ? 'login' : 'signup'); setError('') }} className="font-semibold text-[#174e3f] underline underline-offset-4">{mode === 'signup' ? 'Log in' : 'Create account'}</button></p>
        </>}
      </section>
      <p className="mt-6 text-center text-xs text-[#87938a]">Carefully shared. Professionally reviewed.</p>
    </div>
  </main>
}

function DonorDashboard({ donations, view, setView, error, busy, onSubmit, onLogout }: { donations: Donation[]; view: 'list' | 'create' | 'submitted'; setView: (view: 'list' | 'create' | 'submitted') => void; error: string; busy: boolean; onSubmit: (event: FormEvent<HTMLFormElement>, files: File[]) => void; onLogout: () => void }) {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [qualityWarnings, setQualityWarnings] = useState<Record<string, string>>({})
  const [cameraError, setCameraError] = useState('')
  const [cameraActive, setCameraActive] = useState(false)
  const [retakeIndex, setRetakeIndex] = useState<number | null>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)

  useEffect(() => () => streamRef.current?.getTracks().forEach((track) => track.stop()), [])

  function inspectPhoto(file: File) {
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) return 'Use a JPEG, PNG, or WebP photo.'
    if (file.size > 5 * 1024 * 1024) return 'Each photo must be 5 MB or smaller. Retake or choose a smaller photo.'
    const image = new Image()
    image.onload = () => {
      const canvas = document.createElement('canvas'); canvas.width = 64; canvas.height = 64
      const context = canvas.getContext('2d'); if (!context) return
      context.drawImage(image, 0, 0, 64, 64)
      const pixels = context.getImageData(0, 0, 64, 64).data
      let luminance = 0; let variation = 0
      for (let i = 0; i < pixels.length; i += 4) { const y = .2126 * pixels[i] + .7152 * pixels[i + 1] + .0722 * pixels[i + 2]; luminance += y; variation += y * y }
      luminance /= 4096
      const deviation = Math.sqrt(Math.max(0, variation / 4096 - luminance * luminance))
      if (luminance < 35 || deviation < 12) setQualityWarnings((current) => ({ ...current, [file.name]: `${file.name} may be too dark or blurry. Retake it in good light with the printed details in focus.` }))
      else setQualityWarnings((current) => { const next = { ...current }; delete next[file.name]; return next })
      URL.revokeObjectURL(image.src)
    }
    image.src = URL.createObjectURL(file)
    return ''
  }

  function addPhotos(incoming: File[]) {
    setCameraError('')
    const accepted: File[] = []
    for (const file of incoming) {
      const warning = inspectPhoto(file)
      if (warning) setCameraError(warning)
      else accepted.push(file)
    }
    setSelectedFiles((current) => {
      const next = [...current]
      for (const file of accepted) {
        if (next.length >= 8) { setCameraError('A donation can include up to 8 photos.'); break }
        if (retakeIndex !== null && next[retakeIndex]) next[retakeIndex] = file
        else next.push(file)
      }
      return next
    })
    setRetakeIndex(null)
  }

  async function startCamera(index: number | null = null) {
    setCameraError(''); setRetakeIndex(index)
    if (!navigator.mediaDevices?.getUserMedia) { setCameraError('Camera access is not supported here. Use Upload from Gallery instead.'); return }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false })
      streamRef.current?.getTracks().forEach((track) => track.stop())
      streamRef.current = stream
      setCameraActive(true)
      requestAnimationFrame(() => { if (videoRef.current) videoRef.current.srcObject = stream })
    } catch {
      setCameraError('Camera permission was not granted or no camera is available. Allow camera access in your browser settings, or upload a photo from your gallery.')
      setRetakeIndex(null)
    }
  }

  function stopCamera() { streamRef.current?.getTracks().forEach((track) => track.stop()); streamRef.current = null; setCameraActive(false) }

  function capturePhoto() {
    const video = videoRef.current
    if (!video || !video.videoWidth || !video.videoHeight) { setCameraError('The camera is not ready yet. Please wait and try again.'); return }
    const canvas = document.createElement('canvas'); canvas.width = video.videoWidth; canvas.height = video.videoHeight
    const context = canvas.getContext('2d'); if (!context) return
    context.drawImage(video, 0, 0)
    canvas.toBlob((blob) => {
      if (!blob) { setCameraError('Could not capture this photo. Please try again.'); return }
      const photo = new File([blob], `medicine-photo-${Date.now()}.jpg`, { type: 'image/jpeg' })
      if (photo.size > 5 * 1024 * 1024) { setCameraError('This camera photo exceeds 5 MB. Move closer and retake it.'); return }
      addPhotos([photo]); stopCamera()
    }, 'image/jpeg', 0.92)
  }

  return <div className="mt-8 text-left">
    <div className="mb-6 flex items-center justify-between border-b border-[#edf0ea] pb-5"><div><p className="text-xs font-semibold uppercase tracking-[.12em] text-[#71886d]">Donor dashboard</p><h2 className="mt-1 text-xl font-semibold">{view === 'create' ? 'Donate unused medicine' : view === 'submitted' ? 'Donation submitted' : 'My donations'}</h2></div><button onClick={onLogout} aria-label="Log out" className="rounded-full p-2 text-[#718078] hover:bg-[#f5f7f2]"><LogOut size={18} /></button></div>
    {view === 'submitted' ? <div className="rounded-2xl border border-[#dce9d6] bg-[#f5f9f2] p-5"><h3 className="font-semibold">Thank you for donating</h3><p className="mt-1 text-sm leading-6 text-[#718078]">Your photos and pickup information are submitted. Our clinic pharmacist will identify and verify the medicine. Follow the status in My donations.</p><button onClick={() => setView('list')} className="mt-5 rounded-full bg-[#174e3f] px-5 py-2.5 text-sm font-semibold text-white">View my donations</button></div> : view === 'create' ? <>
      <button onClick={() => setView('list')} className="mb-4 flex items-center gap-1.5 text-sm font-medium text-[#718078]"><ArrowLeft size={16} /> Back to my donations</button>
      <form onSubmit={(event) => onSubmit(event, selectedFiles)} className="space-y-4"><p className="text-sm leading-6 text-[#718078]">Upload photos and provide a pickup address. You do not need to identify the medicine; our clinic pharmacist will.</p>
        <p className="rounded-xl bg-[#f5f7f2] p-3 text-sm leading-6 text-[#52675d]">Photograph the full strip or box and its printed medicine details, including batch and expiry where available. Loose pills or cut blister fragments without traceable information may not be accepted. Photos that are too dark, blurry, or unreadable may need to be retaken. Photo checks only flag possible readability issues; they do not identify or authenticate medicine.</p>
        <div className="space-y-3"><p className="text-sm font-medium">Medicine photos <span className="font-normal text-[#718078]">(up to 8, JPEG/PNG/WebP, 5 MB each)</span></p><div className="flex flex-wrap gap-2"><button type="button" onClick={() => void startCamera()} className="rounded-full bg-[#174e3f] px-4 py-2.5 text-sm font-semibold text-white">Take Photo</button><label className="cursor-pointer rounded-full border border-[#cad7c5] bg-[#fbfcfa] px-4 py-2.5 text-sm font-semibold text-[#52675d]">Upload from Gallery<input className="sr-only" type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={(event) => { addPhotos(Array.from(event.target.files ?? [])); event.currentTarget.value = '' }} /></label></div>
          {cameraActive && <div className="rounded-2xl border border-[#dce4d9] bg-[#f7f8f5] p-3"><video ref={videoRef} autoPlay playsInline muted className="max-h-80 w-full rounded-xl object-contain" /><div className="mt-3 flex gap-2"><button type="button" onClick={capturePhoto} className="rounded-full bg-[#174e3f] px-4 py-2 text-sm font-semibold text-white">Capture photo</button><button type="button" onClick={stopCamera} className="rounded-full border border-[#cad7c5] px-4 py-2 text-sm font-semibold">Cancel</button></div><p className="mt-2 text-xs text-[#718078]">Frame the full strip or box, then capture printed details, batch, expiry, and tablet packaging clearly.</p></div>}
          {cameraError && <p role="alert" className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900">{cameraError}</p>}
          {selectedFiles.map((file, index) => <div key={`${file.name}-${index}`} className="flex items-center gap-3 rounded-xl border border-[#e4e9e0] p-3"><PhotoPreview file={file} alt={`Preview of ${file.name}`} /><div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">Photo {index + 1}: {file.name}</p><p className="text-xs text-[#718078]">Check that printed details and packaging are readable.</p>{qualityWarnings[file.name] && <p className="mt-1 text-xs text-amber-800">{qualityWarnings[file.name]}</p>}</div><button type="button" onClick={() => void startCamera(index)} className="text-xs font-semibold text-[#174e3f]">Retake</button><button type="button" onClick={() => setSelectedFiles((current) => current.filter((_, currentIndex) => currentIndex !== index))} className="text-xs font-semibold text-red-700">Remove</button></div>)}
        </div>
        <label className="block text-sm font-medium">Pickup address<input className={inputClass} name="pickup_address" autoComplete="street-address" required maxLength={500} placeholder="Where can the clinic collect the medicine?" /></label>
        <label className="block text-sm font-medium">Expiry date (if known)<input className={inputClass} type="date" name="donor_expiry_date" min={new Date().toISOString().slice(0, 10)} /></label>
        {error && <p role="alert" className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
        <button disabled={busy} className="w-full rounded-full bg-[#174e3f] px-5 py-3.5 text-sm font-semibold text-white disabled:opacity-60">{busy ? 'Submitting donation?' : 'Submit donation'}</button><p className="text-center text-xs leading-5 text-[#87938a]">Our clinic pharmacist will identify and verify the medicine from your photos.</p>
      </form>
    </> : <>
      <p className="mb-5 text-sm leading-6 text-[#718078]">Donate unused medicine by sharing photos and pickup information.</p><button onClick={() => setView('create')} className="mb-7 flex w-full items-center justify-center gap-2 rounded-full bg-[#174e3f] px-5 py-3 text-sm font-semibold text-white hover:bg-[#103d31]"><Plus size={17} /> Donate unused medicine</button>
      {error && <p role="alert" className="mb-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}<h3 className="mb-3 text-sm font-semibold">My donations <span className="ml-1 font-normal text-[#87938a]">{donations.length}</span></h3>
      {donations.length ? <div className="space-y-3">{donations.map((donation) => <article key={donation.id} className="rounded-2xl border border-[#e4e9e0] p-4"><div className="flex items-center justify-between gap-3"><p className="text-sm text-[#718078]">Submitted {new Date(donation.created_at).toLocaleDateString()}</p><span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${statusStyle[donation.status]}`}>{donorStatus[donation.status]}</span></div></article>)}</div> : <div className="rounded-2xl border border-dashed border-[#dce4d9] px-5 py-8 text-center"><p className="text-sm font-medium">No donations yet</p><p className="mt-1 text-xs text-[#87938a]">Your submissions will appear here.</p></div>}
    </>}
  </div>
}

export default App
