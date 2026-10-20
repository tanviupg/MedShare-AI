import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowLeft, ArrowUpRight, Boxes, Camera, Eye, EyeOff, FileText, Heart, HeartHandshake, ImagePlus, Inbox, LayoutDashboard, ListChecks, MapPin, Pill, Recycle, ShieldCheck, Stethoscope, Upload, Users } from 'lucide-react'
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
import { DonationUploadError, uploadDonationPhoto } from './donationUpload.mjs'
import LandingPage from './LandingPage'
import { HelpingHands } from './HelpingHands'
import './auth-page.css'
import './donor-dashboard.css'
import './clinic-dashboard.css'
import './admin-dashboard.css'

type Role = 'DONOR' | 'PATIENT' | 'CLINIC_PHARMACIST' | 'ADMIN'
type SignupRole = Exclude<Role, 'ADMIN'>
type User = { id: string; name: string; email: string; role: Role; clinic_profile?: { clinic_name: string; verification_status: string; verification_rejection_reason: string | null } | null }
type AuthResult = { access_token: string; user: User }
type DonationStatus = 'PENDING_REVIEW' | 'APPROVED' | 'REJECTED' | 'CANCELLED'
type Donation = { id: string; status: DonationStatus; created_at: string }
type ClinicTab = 'Overview' | 'Donations' | 'Inventory' | 'Patient Requests' | 'Prescriptions' | 'Waste Management'
type AdminTab = 'Dashboard' | 'Clinic Verification'
type PublicRole = { value: SignupRole; name: string; description: string; action: string; number: string; icon: typeof HeartHandshake }
const clinicTabs: ClinicTab[] = ['Overview', 'Donations', 'Inventory', 'Patient Requests', 'Prescriptions', 'Waste Management']
const publicRoles: PublicRole[] = [
  { value: 'DONOR', name: 'Donor', description: 'Give unused medicine a chance to help someone else.', action: 'Share a little care', number: '01', icon: HeartHandshake },
  { value: 'PATIENT', name: 'Patient', description: 'Find the medicine you need, with dignity and support.', action: 'Find your medicine', number: '02', icon: Pill },
  { value: 'CLINIC_PHARMACIST', name: 'Clinic / Pharmacist', description: 'Bring trusted care from generous hands to those in need.', action: 'Connect the care', number: '03', icon: Stethoscope },
]

const roleLabels: Record<Role, string> = { DONOR: 'Donor', PATIENT: 'Patient', CLINIC_PHARMACIST: 'Clinic / Pharmacist', ADMIN: 'Platform administrator' }
const successText: Record<Role, string> = { DONOR: 'Donor dashboard', PATIENT: 'Patient authentication successful.', CLINIC_PHARMACIST: 'Clinic/Pharmacist authentication successful.', ADMIN: 'Platform administrator' }

function PhotoPreview({ file, alt }: { file: File; alt: string }) {
  const [url, setUrl] = useState('')
  useEffect(() => {
    const previewUrl = URL.createObjectURL(file)
    setUrl(previewUrl)
    return () => URL.revokeObjectURL(previewUrl)
  }, [file])
  return <img src={url} alt={alt} className="donor-photo-preview" />
}

function App() {
  const [mode, setMode] = useState<'login' | 'signup'>('signup')
  const [showAuth, setShowAuth] = useState(false)
  const [showRoleSelection, setShowRoleSelection] = useState(false)
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState(() => localStorage.getItem('medshare_token'))
  const [authLoading, setAuthLoading] = useState(() => Boolean(localStorage.getItem('medshare_token')))
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [role, setRole] = useState<SignupRole>('DONOR')
  const [donations, setDonations] = useState<Donation[]>([])
  const [donationsLoading, setDonationsLoading] = useState(false)
  const [view, setView] = useState<'list' | 'create' | 'submitted'>('list')
  const [donationError, setDonationError] = useState('')
  const [donationBusy, setDonationBusy] = useState(false)
  const [operationsRevision, setOperationsRevision] = useState(0)
  const [clinicTab, setClinicTab] = useState<ClinicTab>('Overview')
  const [adminTab, setAdminTab] = useState<AdminTab>('Dashboard')
  const [donorFormRevision, setDonorFormRevision] = useState(0)

  useEffect(() => {
    if (!token) return
    let active = true
    setAuthLoading(true)
    fetch(`${API_BASE_URL}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => response.ok ? response.json() as Promise<User> : null)
      .then((current) => {
        if (!active) return
        if (current) setUser(current)
        else {
          localStorage.removeItem('medshare_token')
          setToken(null)
          setUser(null)
          setMode('login')
          setShowAuth(true)
        }
      })
      .catch(() => {
        if (!active) return
        setError('Could not connect to the authentication service.')
        setMode('login')
        setShowAuth(true)
      })
      .finally(() => { if (active) setAuthLoading(false) })
    return () => { active = false }
  }, [token])

  useEffect(() => {
    if (!token || user?.role !== 'DONOR') return
    const controller = new AbortController()
    setDonationsLoading(true)
    setDonationError('')
    fetch(`${API_BASE_URL}/donations/mine`, { headers: { Authorization: `Bearer ${token}` }, signal: controller.signal })
      .then(async (response) => {
        const body = await response.json().catch(() => null)
        if (!response.ok) throw new Error(safeApiErrorMessage(body, 'Could not load your donations.'))
        setDonations(body as Donation[])
      }).catch((reason) => {
        if (reason instanceof Error && reason.name === 'AbortError') return
        setDonations([])
        setDonationError(reason instanceof Error ? reason.message : 'Could not load your donations.')
      }).finally(() => { if (!controller.signal.aborted) setDonationsLoading(false) })
    return () => controller.abort()
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
      setShowAuth(false)
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
    setShowAuth(true)
    setView('list')
    setDonations([])
    setClinicTab('Overview')
    setAdminTab('Dashboard')
  }

  async function submitDonation(event: FormEvent<HTMLFormElement>, selectedPhotos: File[]) {
    event.preventDefault()
    if (!token) return false
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
      const failureMessages: string[] = []
      for (const [index, file] of files.entries()) {
        try {
          const finalPhoto = index === files.length - 1 && failed.length === 0
          await uploadDonationPhoto({ apiBaseUrl: API_BASE_URL, donationId: donation.id, token, file, finalize: finalPhoto })
          uploaded.push(file.name)
        } catch (reason) {
          if (pending && reason instanceof DonationUploadError && reason.status === 409) { uploaded.push(file.name); continue }
          failed.push(file.name)
          failureMessages.push(reason instanceof Error ? reason.message : `${file.name}: Photo upload failed. Try again.`)
        }
      }
      if (failed.length) {
        setDonations((current) => [donation, ...current.filter((item) => item.id !== donation.id)])
        sessionStorage.setItem('medshare_donation_retry', JSON.stringify({ donation, payload: pending?.payload ?? payload, uploaded: [...(pending?.uploaded ?? []), ...uploaded], failed }))
        setDonationError(
  failureMessages.some((message) =>
    message.toLowerCase().includes('does not appear to show medicine')
  )
    ? 'Not a medicine photo. Upload the medicine or its packaging.'
    : failureMessages.join(' ')
)
        setView('create')
        return false
      }
      const refresh = await fetch(`${API_BASE_URL}/donations/${donation.id}`, { headers: { Authorization: `Bearer ${token}` } })
      if (refresh.ok) Object.assign(donation, await refresh.json())
      sessionStorage.removeItem('medshare_donation_retry')
      setDonations((current) => [donation, ...current.filter((item) => item.id !== donation.id)])
      setView('submitted')
      setDonorFormRevision((revision) => revision + 1)
      return true
    } catch (reason) { setDonationError(reason instanceof Error ? reason.message : 'Could not submit donation.') }
    finally { setDonationBusy(false) }
    return false
  }

  if (authLoading && token && !user) return <main className="min-h-screen bg-[#f7f8f5]" aria-label="Checking your session" />
  const openRoleSelection = (nextMode: 'login' | 'signup') => {
    setMode(nextMode)
    setError('')
    setShowAuth(false)
    setShowRoleSelection(true)
  }
  if (!user && !token && showRoleSelection) return <RoleSelection mode={mode} onBack={() => { setShowRoleSelection(false); setShowAuth(false); setError('') }} onChoose={(selectedRole) => { setRole(selectedRole); setShowRoleSelection(false); setShowAuth(true) }} />
  if (!user && !token && !showAuth) return <LandingPage onGetStarted={() => openRoleSelection('signup')} onSignIn={() => openRoleSelection('login')} />
  if (user?.role === 'PATIENT' && token) return <main className="patient-app-shell"><PatientDiscovery token={token} userName={user.name} onLogout={logout} /></main>

  return <main className={user?.role === 'DONOR' ? 'donor-app-shell' : user?.role === 'PATIENT' ? 'patient-app-shell' : user?.role === 'CLINIC_PHARMACIST' ? 'clinic-app-shell' : user?.role === 'ADMIN' ? 'admin-app-shell' : user ? 'min-h-screen bg-[#f7f8f5] px-5 py-10 text-[#18372e] sm:py-16' : 'medshare-auth'}>
    <div className={user ? user.role === 'DONOR' ? 'donor-app-content' : user.role === 'PATIENT' ? 'patient-app-content' : user.role === 'CLINIC_PHARMACIST' ? 'clinic-app-content' : user.role === 'ADMIN' ? 'admin-app-content' : 'mx-auto w-full max-w-xl' : 'auth-shell'}>
      {!user && <button type="button" className="auth-home-button" onClick={() => { setShowAuth(false); setShowRoleSelection(false); setError('') }} aria-label="Return to MedShare AI home">
        <span className="auth-brand-mark"><HeartHandshake size={21} strokeWidth={1.6} /></span>
        <span>MedShare <i>AI</i></span>
      </button>}
      <section className={user ? user.role === 'DONOR' ? 'donor-app-panel' : user.role === 'PATIENT' ? 'patient-app-panel' : user.role === 'CLINIC_PHARMACIST' ? 'clinic-app-panel' : user.role === 'ADMIN' ? 'admin-app-panel' : 'rounded-[2rem] border border-[#e4e9e0] bg-white shadow-[0_24px_80px_-48px_rgba(27,63,49,.3)] p-4 sm:p-7' : 'auth-panel'}>
        {user && user.role !== 'DONOR' && user.role !== 'PATIENT' && user.role !== 'CLINIC_PHARMACIST' && user.role !== 'ADMIN' && <div className="mb-7 flex items-center gap-2 text-xs font-semibold uppercase tracking-[.12em] text-[#71886d]"><ShieldCheck size={16} /> Secure account access</div>}
        {user ? <div>
          {user.role === 'CLINIC_PHARMACIST' && token ? <>
            <div className="clinic-workspace">
              <aside className="clinic-sidebar">
                <a className="clinic-brand" href="#clinic-overview" aria-label="MedShare AI clinic dashboard"><span className="clinic-brand-mark"><HeartHandshake size={20} strokeWidth={1.5} /></span><span>MedShare<span> AI</span></span></a>
                <div className="clinic-account"><p className="clinic-eyebrow">Clinic / Pharmacist</p><p>{user.name}</p><span>{user.clinic_profile?.clinic_name || roleLabels[user.role]}</span></div>
                <div className={`clinic-verification clinic-verification-${(user.clinic_profile?.verification_status ?? 'PENDING').toLowerCase()}`}><span>Clinic verification</span><b>{user.clinic_profile?.verification_status ?? 'PENDING'}</b>{user.clinic_profile?.verification_status === 'PENDING' && <small>Profile waiting for platform review</small>}{user.clinic_profile?.verification_rejection_reason && <small>{user.clinic_profile.verification_rejection_reason}</small>}</div>
                <nav aria-label="Clinic operations" role="tablist" className="clinic-nav">
                  {clinicTabs.map((tab, index) => {
                    const icons = [<LayoutDashboard size={16} />, <Inbox size={16} />, <Boxes size={16} />, <Users size={16} />, <FileText size={16} />, <Recycle size={16} />]
                    return <button key={tab} id={`clinic-tab-${index}`} type="button" role="tab" aria-selected={clinicTab === tab} aria-controls={`clinic-panel-${index}`} tabIndex={clinicTab === tab ? 0 : -1} onClick={() => setClinicTab(tab)} onKeyDown={(event) => {
                      if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
                        event.preventDefault()
                        const direction = event.key === 'ArrowRight' ? 1 : -1
                        const nextIndex = (index + direction + clinicTabs.length) % clinicTabs.length
                        setClinicTab(clinicTabs[nextIndex])
                        document.getElementById(`clinic-tab-${nextIndex}`)?.focus()
                      }
                    }} className={`clinic-nav-link${clinicTab === tab ? ' active' : ''}`}>{icons[index]}<span>{tab}</span></button>
                  })}
                </nav>
                <div className="clinic-sidebar-foot"><div className="clinic-sidebar-art"><HelpingHands /></div><p className="clinic-handwritten">A little care. A lasting difference.</p><button type="button" onClick={logout} className="clinic-logout"><ArrowLeft size={14} /> Log out</button></div>
              </aside>
              <div className="clinic-main">
                <div className="clinic-topbar"><span className="clinic-preview-stamp">Clinic operations</span><span>Care connects us.</span></div>
                <header className="clinic-heading"><div className="clinic-heading-copy"><p className="clinic-eyebrow">Clinic / MedShare community</p><h1>{clinicTab}</h1><p>{user.clinic_profile?.clinic_name || user.name}</p></div><div className="clinic-heading-actions"><Notifications token={token} /><div className="clinic-user-chip"><span>{user.name.slice(0,1).toUpperCase()}</span><span className="clinic-chip-copy">{user.name}</span></div></div></header>
                <div className="clinic-verification-mobile"><b>Clinic verification: {user.clinic_profile?.verification_status ?? 'PENDING'}</b>{user.clinic_profile?.verification_rejection_reason && <span>{user.clinic_profile.verification_rejection_reason}</span>}</div>
                <div id="clinic-panel-0" role="tabpanel" aria-labelledby="clinic-tab-0" hidden={clinicTab !== 'Overview'}><PharmacistDashboard token={token} refreshKey={operationsRevision} onNavigate={setClinicTab} /></div>
                <div id="clinic-panel-1" role="tabpanel" aria-labelledby="clinic-tab-1" hidden={clinicTab !== 'Donations'}><PharmacistReview token={token} onReviewComplete={() => setOperationsRevision((revision) => revision + 1)} /></div>
                <div id="clinic-panel-2" role="tabpanel" aria-labelledby="clinic-tab-2" hidden={clinicTab !== 'Inventory'}><PharmacistInventory token={token} refreshKey={operationsRevision} onPricingUpdated={() => setOperationsRevision((revision) => revision + 1)} /></div>
                <div id="clinic-panel-3" role="tabpanel" aria-labelledby="clinic-tab-3" hidden={clinicTab !== 'Patient Requests'}><PharmacistRequests token={token} /><PharmacistDispensing token={token} /></div>
                <div id="clinic-panel-4" role="tabpanel" aria-labelledby="clinic-tab-4" hidden={clinicTab !== 'Prescriptions'}><PharmacistPrescriptions token={token} /></div>
                <div id="clinic-panel-5" role="tabpanel" aria-labelledby="clinic-tab-5" hidden={clinicTab !== 'Waste Management'}><PharmacistExpiryWaste token={token} /></div>
                <footer className="clinic-footer"><span>MedShare AI · Hands that help</span><span>Clinical decisions are recorded through your clinic tools.</span></footer>
              </div>
            </div>
          </>: user.role === 'ADMIN' && token ? <div className="admin-workspace">
            <aside className="admin-sidebar">
              <a className="admin-brand" href="#admin-dashboard" aria-label="MedShare AI admin dashboard"><span className="admin-brand-mark"><HeartHandshake size={20} strokeWidth={1.5} /></span><span>MedShare<span> AI</span></span></a>
              <div className="admin-account"><p className="admin-eyebrow">Platform administrator</p><p>{user.name}</p><span>MedShare AI</span></div>
              <nav className="admin-nav" aria-label="Admin sections">
                <button type="button" aria-current={adminTab === 'Dashboard' ? 'page' : undefined} onClick={() => setAdminTab('Dashboard')} className={`admin-nav-link${adminTab === 'Dashboard' ? ' active' : ''}`}><LayoutDashboard size={16} /><span>Dashboard</span></button>
                <button type="button" aria-current={adminTab === 'Clinic Verification' ? 'page' : undefined} onClick={() => setAdminTab('Clinic Verification')} className={`admin-nav-link${adminTab === 'Clinic Verification' ? ' active' : ''}`}><ShieldCheck size={16} /><span>Clinic Verification</span></button>
              </nav>
              <div className="admin-sidebar-foot"><div className="admin-sidebar-art"><HelpingHands /></div><p className="admin-handwritten">A little care. A lasting difference.</p><button type="button" onClick={logout} className="admin-logout"><ArrowLeft size={14} /> Log out</button></div>
            </aside>
            <div className="admin-main">
              <div className="admin-topbar"><span className="admin-preview-stamp">MedShare AI Â· Platform oversight</span><span>Care connects us.</span></div>
              <header className="admin-heading"><div className="admin-heading-copy"><p className="admin-eyebrow">Administrator workspace</p><h1>{adminTab}</h1><p>{adminTab === 'Dashboard' ? 'A clear view of the care moving through MedShare AI.' : 'Review clinic applications and record verification decisions.'}</p></div><div className="admin-heading-actions"><Notifications token={token} /><div className="clinic-user-chip"><span>{user.name.slice(0, 1).toUpperCase()}</span><span className="clinic-chip-copy">{user.name}</span></div></div></header>
              <div className="admin-content" key={adminTab}>{adminTab === 'Dashboard' ? <AdminDashboard token={token} /> : <AdminClinicVerification token={token} />}</div>
              <footer className="admin-footer"><span>MedShare AI · Hands that help</span><span>Platform activity reflects current records.</span></footer>
            </div>
          </div> : user.role === 'DONOR' ? <DonorDashboard key={donorFormRevision} donations={donations} donationsLoading={donationsLoading} userName={user.name} token={token} view={view} setView={setView} error={donationError} busy={donationBusy} onSubmit={submitDonation} onLogout={logout} /> : <><div className="text-center"><span className="mx-auto grid size-14 place-items-center rounded-2xl bg-[#e7efe2] text-[#63855b]"><Heart size={24} /></span><h1 className="mt-5 text-2xl font-semibold tracking-tight">{successText[user.role]}</h1><p className="mt-2 text-sm text-[#718078]">Signed in as {user.name} · {roleLabels[user.role]}</p></div>{token && <div className="mt-4 flex justify-end"><Notifications token={token} /></div>}{token ? <PatientDiscovery token={token} userName={user.name} onLogout={logout} /> : null}</>}
        </div> : <div className="auth-columns">
          <aside className="auth-story">
            <p className="auth-eyebrow">A community of care</p>
            <h1 className="auth-display">Hands that <em>help.</em></h1>
            <p className="auth-story-copy">The medicine you no longer need could be the relief someone is waiting for.</p>
            <div className="auth-illustration"><HelpingHands /></div>
            <p className="auth-handwritten">Good medicine. Even better together.</p>
            <div className="auth-trust"><ShieldCheck size={16} /><span>Given with kindness. Shared with care.</span></div>
          </aside>
          <div className="auth-form-wrap">
            <p className="auth-eyebrow">{mode === 'signup' ? 'Your care begins here' : 'Welcome back'}</p>
            <h2 className="auth-form-title">{mode === 'signup' ? 'Join the community.' : 'Pick up where care left off.'}</h2>
            <p className="auth-form-copy">{mode === 'signup' ? 'Create an account and find your way to help.' : 'Sign in to your MedShare AI account.'}</p>
            <div className="auth-selected-role"><span>{mode === 'signup' ? 'Selected signup role' : 'Role selected for context'}</span><strong>{roleLabels[role]}</strong>{mode === 'login' && <small>Your account role from the server determines your access.</small>}<button type="button" onClick={() => { setShowAuth(false); setShowRoleSelection(true); setError('') }}>Change role</button></div>
            <form className="auth-form" onSubmit={submit} aria-busy={busy}>
              {mode === 'signup' && <><label className="auth-field">Full name<input className="auth-input" name="name" autoComplete="name" required minLength={1} maxLength={120} /></label><label className="auth-field">I am a<select className="auth-input" value={role} onChange={(event) => setRole(event.target.value as SignupRole)}><option value="DONOR">Donor</option><option value="PATIENT">Patient</option><option value="CLINIC_PHARMACIST">Clinic / Pharmacist</option></select></label></>}
              <label className="auth-field">Email address<input className="auth-input" name="email" type="email" autoComplete="email" required maxLength={320} /></label>
              <label className="auth-field">Password<span className="auth-password"><input className="auth-input" name="password" type={showPassword ? 'text' : 'password'} autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} required minLength={mode === 'signup' ? 8 : 1} maxLength={72} /><button type="button" className="auth-password-toggle" onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword}>{showPassword ? <EyeOff size={18} /> : <Eye size={18} />}</button></span></label>
              {mode === 'signup' && <><div className="auth-field-grid"><label className="auth-field">Phone <span>(optional)</span><input className="auth-input" name="phone" type="tel" maxLength={40} /></label><label className="auth-field">City <span>(optional)</span><input className="auth-input" name="city" maxLength={120} /></label></div>{role === 'CLINIC_PHARMACIST' && <fieldset className="auth-clinic"><legend>Clinic details</legend><label className="auth-field">Clinic name<input className="auth-input" name="clinic_name" required maxLength={160} /></label><label className="auth-field">Address<input className="auth-input" name="address" required maxLength={500} /></label><div className="auth-field-grid"><label className="auth-field">Clinic city<input className="auth-input" name="clinic_city" required maxLength={120} /></label><label className="auth-field">License number <span>(optional)</span><input className="auth-input" name="license_number" maxLength={100} /></label></div><label className="auth-field">Contact number <span>(optional)</span><input className="auth-input" name="contact_number" maxLength={40} /></label></fieldset>}</>}
              {error && <p role="alert" className="auth-error"><ShieldCheck size={17} aria-hidden="true" />{error}</p>}
              <button type="submit" disabled={busy} className="auth-submit">{busy ? <><span className="auth-spinner" aria-hidden="true" />Please wait…</> : mode === 'signup' ? 'Create account' : 'Sign in'}</button>
            </form>
            <p className="auth-switch">{mode === 'signup' ? 'Already have an account?' : 'New to MedShare AI?'} <button type="button" onClick={() => { setMode(mode === 'signup' ? 'login' : 'signup'); setError('') }}>{mode === 'signup' ? 'Log in' : 'Create account'}</button></p>
            <p className="auth-footnote"><ShieldCheck size={14} /> Your information is kept secure.</p>
          </div>
        </div>}
      </section>
      {user ? <p className="mt-6 text-center text-xs text-[#87938a]">Carefully shared. Professionally reviewed.</p> : <p className="auth-footer">Carefully shared. Professionally reviewed.</p>}
    </div>
  </main>
}

function RoleSelection({ mode, onBack, onChoose }: { mode: 'login' | 'signup'; onBack: () => void; onChoose: (role: SignupRole) => void }) {
  return <main className="medshare-role-selection">
    <header className="role-selection-header">
      <button type="button" className="role-selection-logo" onClick={onBack} aria-label="Return to MedShare AI home"><span className="role-selection-mark"><HeartHandshake size={20} strokeWidth={1.5} /></span><span>MedShare<span> AI</span></span></button>
      <span className="role-selection-stamp">A community of care</span>
    </header>
    <div className="role-selection-content">
      <section className="role-selection-intro">
        <div className="role-selection-copy rise">
          <p className="role-selection-eyebrow">A community of care</p>
          <h1>MedShare AI<span>Hands that help.</span></h1>
          <p className="role-selection-subtitle">The medicine you no longer need could be the relief someone is waiting for.</p>
          <div className="role-selection-promise"><span><Heart size={16} strokeWidth={1.5} /></span><span>Given with kindness. Shared with care.</span></div>
        </div>
        <div className="role-selection-art rise"><HelpingHands /><div className="role-selection-journey"><span>Generous donors</span><span>Trusted clinics</span><span>Healthier lives</span></div><p>Good medicine. Even better together.</p></div>
      </section>
      <section className="role-selection-options" aria-labelledby="role-selection-title">
        <div className="role-selection-heading"><div className="role-selection-heading-main"><button type="button" className="role-selection-back" onClick={onBack}><ArrowLeft size={14} /> Back to Landing Page</button><h2 id="role-selection-title">Sign in — where does your care begin?</h2></div><span>Three roles. One shared purpose.</span></div>
        <div className="role-selection-grid">{publicRoles.map(({ value, name, description, action, number, icon: Icon }, index) => <button type="button" key={value} className="role-selection-card rise" style={{ animationDelay: `${index * 70}ms` }} onClick={() => onChoose(value)}>
          <span className="role-selection-card-top"><Icon size={28} strokeWidth={1.3} /><span>{number}</span></span>
          <span className="role-selection-card-title">{name}</span>
          <span className="role-selection-description">{description}</span>
          <span className="role-selection-card-action"><span>{mode === 'signup' ? action : `Continue as ${name}`}</span><ArrowUpRight size={16} /></span>
        </button>)}</div>
      </section>
      <footer className="role-selection-footer"><span>MedShare AI · People helping people.</span><span>{mode === 'login' ? 'Your account role is confirmed when you sign in.' : 'Carefully shared. Professionally reviewed.'}</span></footer>
    </div>
  </main>
}

function DonorDashboard({ donations, donationsLoading, userName, token, view, setView, error, busy, onSubmit, onLogout }: { donations: Donation[]; donationsLoading: boolean; userName: string; token: string | null; view: 'list' | 'create' | 'submitted'; setView: (view: 'list' | 'create' | 'submitted') => void; error: string; busy: boolean; onSubmit: (event: FormEvent<HTMLFormElement>, files: File[]) => Promise<boolean>; onLogout: () => void }) {
  type DonorTab = 'Overview' | 'Donate Medicine' | 'My Donations'
  const [activeTab, setActiveTab] = useState<DonorTab>('Overview')
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [qualityWarnings, setQualityWarnings] = useState<Record<string, string>>({})
  const [cameraError, setCameraError] = useState('')
  const [cameraActive, setCameraActive] = useState(false)
  const [retakeIndex, setRetakeIndex] = useState<number | null>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const galleryInputRef = useRef<HTMLInputElement>(null)
  const today = new Date().toISOString().slice(0, 10)
  const tabs = [
    { id: 'Overview' as const, icon: <LayoutDashboard size={16} /> },
    { id: 'Donate Medicine' as const, icon: <Upload size={16} /> },
    { id: 'My Donations' as const, icon: <ListChecks size={16} /> },
  ]

  useEffect(() => () => streamRef.current?.getTracks().forEach((track) => track.stop()), [])

  async function submitForm(event: FormEvent<HTMLFormElement>) {
    const form = event.currentTarget
    if (!await onSubmit(event, selectedFiles)) return
    setSelectedFiles([])
    setQualityWarnings({})
    setCameraError('')
    setRetakeIndex(null)
    stopCamera()
    form.reset()
    if (galleryInputRef.current) galleryInputRef.current.value = ''
  }

  async function inspectPhoto(file: File) {
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) return `${file.name}: use a JPEG, PNG, or WebP photo.`
    if (file.size === 0) return `${file.name}: the file is empty.`
    if (file.size > 5 * 1024 * 1024) return `${file.name}: each photo must be 5 MB or smaller. Retake or choose a smaller photo.`
    const header = new Uint8Array(await file.slice(0, 12).arrayBuffer())
    const jpeg = header[0] === 0xff && header[1] === 0xd8 && header[2] === 0xff
    const png = header.length >= 8 && [137, 80, 78, 71, 13, 10, 26, 10].every((byte, index) => header[index] === byte)
    const webp = header.length >= 12 && String.fromCharCode(...header.slice(0, 4)) === 'RIFF' && String.fromCharCode(...header.slice(8, 12)) === 'WEBP'
    if (!(file.type === 'image/jpeg' && jpeg || file.type === 'image/png' && png || file.type === 'image/webp' && webp)) return `${file.name}: contents do not match a supported JPEG, PNG, or WebP image.`
    try {
      const decoded = await createImageBitmap(file)
      if (!decoded.width || !decoded.height) { decoded.close(); return `${file.name}: the image is empty or corrupted.` }
      decoded.close()
    } catch { return `${file.name}: the image is corrupted or cannot be decoded.` }
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

  async function addPhotos(incoming: File[]) {
    setCameraError('')
    const accepted: File[] = []
    const rejected: string[] = []
    for (const file of incoming) {
      const warning = await inspectPhoto(file)
      if (warning) rejected.push(warning)
      else accepted.push(file)
    }
    if (rejected.length) setCameraError(rejected.join(' '))
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
      void addPhotos([photo]); stopCamera()
    }, 'image/jpeg', 0.92)
  }

  function navigate(tab: DonorTab) {
    setActiveTab(tab)
    setView(tab === 'Donate Medicine' ? 'create' : 'list')
  }

  const statusLabel = (status: DonationStatus) => ({ PENDING_REVIEW: 'Under clinic verification', APPROVED: 'Approved', REJECTED: 'Rejected', CANCELLED: 'Cancelled' })[status]
  const dateLabel = (date: string) => new Date(date).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
  const rows = (items: Donation[]) => items.map((donation) => [
    <span key="donation" className="donor-record-name">Donation <span>#{donation.id.slice(0, 8)}</span></span>,
    <span key="date">{dateLabel(donation.created_at)}</span>,
    <span key="status" className={`donor-status donor-status-${donation.status.toLowerCase()}`}><span />{statusLabel(donation.status)}</span>,
  ])

  return <div id="donor-overview" className="donor-workspace">
    <aside className="donor-sidebar">
      <a className="donor-logo" href="#donor-overview" aria-label="MedShare AI donor dashboard"><span className="donor-logo-mark"><HeartHandshake size={20} strokeWidth={1.5} /></span><span>MedShare<span> AI</span></span></a>
      <div className="donor-account"><p className="donor-eyebrow">Donor</p><p>{userName}</p></div>
      <nav className="donor-nav" aria-label="Donor sections" role="tablist">
        {tabs.map((tab, index) => <button key={tab.id} id={`donor-tab-${index}`} type="button" role="tab" aria-selected={activeTab === tab.id} aria-controls={`donor-panel-${index}`} tabIndex={activeTab === tab.id ? 0 : -1} onClick={() => navigate(tab.id)} onKeyDown={(event) => {
          if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
            event.preventDefault()
            const next = (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length
            navigate(tabs[next].id)
            document.getElementById(`donor-tab-${next}`)?.focus()
          }
        }} className={`donor-nav-link${activeTab === tab.id ? ' is-active' : ''}`}>{tab.icon}{tab.id}</button>)}
      </nav>
      <div className="donor-sidebar-foot"><div className="donor-sidebar-art"><HelpingHands /></div><p className="donor-handwritten">A little care. A lasting difference.</p><button type="button" onClick={onLogout} className="donor-change-role"><ArrowLeft size={14} /> Log out</button></div>
    </aside>

    <div className="donor-main">
      <div className="donor-topbar"><span className="donor-preview-stamp">Your donation activity</span><span>Care connects us.</span></div>
      <header className="donor-workspace-heading"><div><p className="donor-eyebrow">Donor / MedShare community</p><h1>{activeTab}</h1><p>{userName}</p></div><div className="clinic-heading-actions">{token && <Notifications token={token} />}<div className="clinic-user-chip"><span>{userName.slice(0, 1).toUpperCase()}</span><span className="clinic-chip-copy">{userName}</span></div></div></header>
      <div id={`donor-panel-${tabs.findIndex((tab) => tab.id === activeTab)}`} role="tabpanel" aria-labelledby={`donor-tab-${tabs.findIndex((tab) => tab.id === activeTab)}`} key={activeTab} className="donor-tab-content rise">
        {view === 'submitted' ? <section className="donor-success" aria-live="polite"><div className="donor-success-mark"><Heart size={25} /></div><div><p className="donor-eyebrow">A generous next step</p><h2>Thank you for donating</h2><p>Your photos and pickup information are submitted. Our clinic pharmacist will identify and verify the medicine. Follow the status in My Donations.</p><button type="button" onClick={() => navigate('My Donations')} className="donor-button donor-button-primary">View my donations <ArrowUpRight size={16} /></button></div></section> : view === 'create' ? <>
          <div className="donor-steps" aria-label="Donation steps"><span className="is-current">01 &middot; Photograph</span><span className={selectedFiles.length ? 'is-current' : ''}>02 &middot; Pickup details</span><span>03 &middot; Pharmacist review</span></div>
          <div className="donor-form-layout"><section className="donor-photo-section"><div className="donor-section-heading"><span className="donor-step">01</span><div><h2>Show us the medicine</h2><p>Clear packaging helps our pharmacist review it.</p></div></div>
            <div className="donor-photo-zone">
              {!selectedFiles.length && !cameraActive && <div className="donor-photo-empty"><span className="donor-photo-icon"><ImagePlus size={27} strokeWidth={1.5} /></span><h3>Every act of care starts here.</h3><p>Add a clear photo of the full strip or box, including printed details.</p></div>}
              <div className="donor-photo-actions"><button type="button" onClick={() => void startCamera()} className="donor-button donor-button-primary"><Camera size={16} /> Take a photo</button><label className="donor-button donor-button-outline"><Upload size={16} /> Upload from gallery<input ref={galleryInputRef} type="file" accept="image/jpeg,image/png,image/webp" multiple aria-label="Upload medicine photos from gallery" onChange={(event) => { void addPhotos(Array.from(event.target.files ?? [])); event.currentTarget.value = '' }} /></label></div>
              {cameraActive && <div className="donor-camera"><video ref={videoRef} autoPlay playsInline muted /><div className="donor-photo-actions"><button type="button" onClick={capturePhoto} className="donor-button donor-button-primary"><Camera size={16} /> Capture photo</button><button type="button" onClick={stopCamera} className="donor-button donor-button-outline">Cancel</button></div><p>Frame the full strip or box, then capture printed details clearly.</p></div>}
              {cameraError && <p role="alert" className="donor-inline-alert donor-inline-warn">{cameraError}</p>}
              {selectedFiles.length > 0 && <p className="donor-photo-count">{selectedFiles.length} of 8 photos added</p>}
              <div className="donor-photo-list">{selectedFiles.map((file, index) => <article key={`${file.name}-${index}`} className="donor-photo-item"><PhotoPreview file={file} alt={`Preview of ${file.name}`} /><div className="donor-photo-meta"><p className="donor-photo-name">Photo {index + 1}: {file.name}</p><p>Check that printed details and packaging are readable.</p>{qualityWarnings[file.name] && <p className="donor-quality-warning">{qualityWarnings[file.name]}</p>}</div><div className="donor-photo-controls"><button type="button" onClick={() => void startCamera(index)}>Retake</button><button type="button" onClick={() => setSelectedFiles((current) => current.filter((_, currentIndex) => currentIndex !== index))}>Remove</button></div></article>)}</div>
            </div>
            <aside className="donor-photo-note"><ShieldCheck size={17} /><p>Loose pills or cut blister fragments without traceable packaging may not be accepted. Photo checks flag possible readability issues; a pharmacist identifies and verifies the medicine.</p></aside>
          </section>
          <form onSubmit={(event) => void submitForm(event)} className="donor-details-form"><div className="donor-section-heading"><span className="donor-step donor-step-sage">02</span><div><h2>Pickup details</h2><p>You do not need to identify the medicine.</p></div></div>
            <div className="donor-workflow-note"><ShieldCheck size={16} /><p>The pharmacist records medicine name, batch, packaging, and quantity after physically verifying it. Donor entries for those details are not part of this workflow.</p></div>
            <label className="donor-field">Pickup address <span className="donor-required">Required</span><span className="donor-input-wrap"><MapPin size={16} /><input name="pickup_address" autoComplete="street-address" required maxLength={500} placeholder="Where can the clinic collect it?" /></span></label>
            <label className="donor-field">Expiry date <span className="donor-optional">If known</span><input className="donor-date" type="date" name="donor_expiry_date" min={today} /></label>
            {error && <p role="alert" className="donor-inline-alert donor-inline-error">{error}</p>}
            <button disabled={busy} className="donor-button donor-button-primary donor-submit">{busy ? <><span className="donor-spinner" aria-hidden="true" />Submitting donation…</> : <>Submit donation <Heart size={16} /></>}</button><p className="donor-privacy">Our clinic pharmacist will identify and verify the medicine from your photos.</p>
          </form></div>
        </> : activeTab === 'Overview' ? <>
           <div className="donor-stats" aria-label="Donation summary">{[
             ['Total donations', donations.length, 'Your submitted records'],
             ['Approved', donations.filter((item) => item.status === 'APPROVED').length, 'Checked by a pharmacist'],
             ['In review', donations.filter((item) => item.status === 'PENDING_REVIEW').length, 'Awaiting clinic verification'],
             ['Needs attention', donations.filter((item) => item.status === 'REJECTED' || item.status === 'CANCELLED').length, 'Rejected or cancelled records'],
           ].map(([label, value, hint], index) => <article key={label} className={`donor-stat donor-stat-${index}`}><p>{label}</p><strong>{donationsLoading || error ? '--' : value}</strong><span>{hint}</span></article>)}</div>
          <section className="donor-care-banner"><div><p className="donor-eyebrow">Small acts, meaningful change</p><h2>Your kindness has a next chapter.</h2><p>The unused medicine in your cupboard could make a real difference to someone's day.</p><button type="button" onClick={() => navigate('Donate Medicine')} className="donor-button donor-button-primary">Donate medicine <ArrowUpRight size={16} /></button></div><HelpingHands /></section>
           {error && <p role="alert" className="donor-inline-alert donor-inline-error">{error}</p>}
           <section className="donor-recent"><div className="donor-recent-heading"><h2>Your recent generosity</h2><button type="button" onClick={() => navigate('My Donations')} className="donor-view-all">View all <ArrowUpRight size={15} /></button></div><div className="donor-table-wrap"><table><thead><tr><th>Donation</th><th>Submitted</th><th>Status</th></tr></thead><tbody>{donationsLoading ? <tr><td colSpan={3} className="donor-table-empty" aria-live="polite">Loading your donations...</td></tr> : donations.length ? rows(donations.slice(0, 3)).map((row, index) => <tr key={donations[index].id}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>) : <tr><td colSpan={3} className="donor-table-empty">{error ? 'Your donation records could not be loaded.' : 'No donations yet. Your donations will appear here.'}</td></tr>}</tbody></table></div></section>
         </> : <section className="donor-donations-section">{error && <p role="alert" className="donor-inline-alert donor-inline-error">{error}</p>}<div className="donor-recent-heading"><div><h2>My Donations</h2><p>Each donation is a little more care in the world.</p></div><button type="button" onClick={() => navigate('Donate Medicine')} className="donor-button donor-button-primary"><Upload size={15} /> New donation</button></div><div className="donor-table-wrap"><table><thead><tr><th>Donation</th><th>Submitted</th><th>Status</th></tr></thead><tbody>{donationsLoading ? <tr><td colSpan={3} className="donor-table-empty" aria-live="polite">Loading your donation history...</td></tr> : donations.length ? rows(donations).map((row, index) => <tr key={donations[index].id}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>) : <tr><td colSpan={3} className="donor-table-empty">{error ? <p role="status">Your donation history is unavailable. Please try again later.</p> : <div className="donor-empty"><span className="donor-empty-icon"><HeartHandshake size={27} strokeWidth={1.2} /></span><h3>Your first act of care starts here.</h3><p>When you share unused medicine, your submissions will appear here for you to follow.</p><button type="button" onClick={() => navigate('Donate Medicine')} className="donor-text-button">Share a little care <ArrowUpRight size={15} /></button></div>}</td></tr>}</tbody></table></div></section>}
      </div>
      <footer className="donor-footer"><span>MedShare AI | Hands that help</span><span>Donation history and status reflect your records.</span></footer>
    </div>
  </div>
}

export default App
