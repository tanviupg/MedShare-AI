import { useEffect, useState } from 'react'
import { AlertTriangle, ArrowRight, Bell, ClipboardCheck, Package, Pill, ShieldAlert, Trash2 } from 'lucide-react'
import { API_BASE_URL } from './config'

type DashboardData = {
  summary: { pending_donations: number; pending_requests: number; pending_prescriptions: number; ready_for_dispensing: number; expiring_soon: number; expired: number; waste_pending: number; unread_notifications: number }
  inventory: { available: number; reserved: number; expiring_soon: number; expired: number; depleted: number; pricing_configured: number; pricing_missing: number }
  recent_donations: { medicine_name: string | null; created_at: string; extraction_status: string; details_confirmed: boolean; review_status: string }[]
  pending_requests: { medicine_name: string; strength: string | null; quantity: number; unit: string; created_at: string; prescription_status: string | null; status: string; payment_status: string | null }[]
  prescription_queue: { medicine_name: string; strength: string | null; created_at: string; verification_status: string }[]
  dispensing_queue: { medicine_name: string; strength: string | null; quantity: number; unit: string; created_at: string; payment_status: string; pickup_readiness: string }[]
  expiry_alerts: { medicine_name: string; strength: string | null; quantity: number; unit: string; expiry_date: string; status: string }[]
  waste_summary: { disposal_pending: number; collected: number; disposed: number; pending_items: { medicine_name: string | null; quantity: number; status: string; created_at: string }[] }
}

const dateLabel = (value: string) => new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
const button = 'inline-flex items-center gap-1.5 rounded-full border border-[#dce4d9] px-3 py-1.5 text-xs font-semibold text-[#174e3f] hover:bg-[#f5f8f3]'
const card = 'rounded-2xl border border-[#e4e9e0] bg-white p-4 sm:p-5'

type DashboardTab = 'Donations' | 'Patient Requests' | 'Prescriptions' | 'Inventory' | 'Waste Management' | 'Notifications'

export default function PharmacistDashboard({ token, refreshKey, onNavigate }: { token: string; refreshKey: number; onNavigate: (tab: DashboardTab) => void }) {
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    const url = `${API_BASE_URL}/pharmacist/dashboard`
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => {
        if (response.status === 401) throw new Error('Your session has expired. Please log in again.')
        if (response.status === 403) throw new Error('You are not authorized to view this dashboard.')
        if (!response.ok) throw new Error('Unable to load dashboard data.')
        return response.json() as Promise<DashboardData>
      })
      .then((result) => { if (active) setData(result) })
      .catch((reason) => {
        if (active) setError(reason instanceof Error && reason.message !== 'Failed to fetch' ? reason.message : 'Unable to connect to the dashboard service.')
      })
    return () => { active = false }
  }, [token, refreshKey])

  if (error) return <div className="mt-5 rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800" role="alert">{error}</div>
  if (!data) return <div className="mt-5 rounded-2xl border border-[#e4e9e0] bg-white p-8 text-sm text-[#718078]" role="status">Loading operations dashboard...</div>

  const s = data.summary
  const cards = [
    ['Pending Donations', s.pending_donations, 'donation-queue', 'Review'],
    ['Pending Requests', s.pending_requests, 'request-queue', 'Review'],
    ['Prescriptions to Verify', s.pending_prescriptions, 'prescription-queue', 'Verify'],
    ['Ready for Dispensing', s.ready_for_dispensing, 'dispensing-queue', 'Open queue'],
    ['Expiring Soon', s.expiring_soon, 'expiry-alerts', 'View stock'],
    ['Expired', s.expired, 'expiry-alerts', 'View stock'],
    ['Waste Pending', s.waste_pending, 'waste-overview', 'Manage waste'],
  ] as const
  const actions = [
    ...(s.expired ? [{ text: `${s.expired} inventory items are expired`, href: '#expiry-alerts', label: 'View expired stock', urgent: true }] : []),
    ...(s.pending_prescriptions ? [{ text: `${s.pending_prescriptions} prescriptions await verification`, href: '#prescription-queue', label: 'Verify prescriptions', urgent: true }] : []),
    ...(s.pending_donations ? [{ text: `${s.pending_donations} donations await review`, href: '#donation-queue', label: 'Review donations', urgent: true }] : []),
    ...(s.pending_requests ? [{ text: `${s.pending_requests} requests need a decision`, href: '#request-queue', label: 'Review requests', urgent: true }] : []),
    ...(s.waste_pending ? [{ text: `${s.waste_pending} waste records require disposal follow-up`, href: '#waste-overview', label: 'Manage waste', urgent: true }] : []),
    ...(s.ready_for_dispensing ? [{ text: `${s.ready_for_dispensing} approved requests are ready for dispensing`, href: '#dispensing-queue', label: 'Open dispensing', urgent: false }] : []),
    ...(s.expiring_soon ? [{ text: `${s.expiring_soon} inventory items expire within the warning window`, href: '#expiry-alerts', label: 'View inventory', urgent: false }] : []),
    ...(data.inventory.pricing_missing ? [{ text: `${data.inventory.pricing_missing} active items have no pricing configured`, href: '#inventory-overview', label: 'Review pricing', urgent: false }] : []),
  ]
  const stat = (title: string, value: number) => <div key={title} className="rounded-xl bg-[#f7f8f5] p-3"><dt className="text-xs text-[#718078]">{title}</dt><dd className="mt-1 text-lg font-semibold tabular-nums">{value}</dd></div>

  return <div className="mt-6 space-y-6 text-left">
    <header className="flex flex-wrap items-end justify-between gap-3 border-b border-[#edf0ea] pb-4"><div><p className="text-xs font-semibold uppercase tracking-[.12em] text-[#71886d]">Clinic operations</p><h2 className="mt-1 text-2xl font-semibold tracking-tight">Operations Dashboard</h2><p className="mt-1 text-sm text-[#718078]">Your clinic's current queues and stock status.</p></div><a className={button} href="#notifications"><Bell size={14} /> {s.unread_notifications} unread notifications</a></header>

    <section aria-label="Operations summary" className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
      {cards.map(([label, value, target, action]) => <article key={label} className={card}><p className="text-xs font-medium text-[#718078]">{label}</p><p className={`mt-2 text-3xl font-semibold tabular-nums ${(['Expired', 'Waste Pending'].includes(label) && value > 0) ? 'text-red-700' : 'text-[#18372e]'}`}>{value}</p><a href={`#${target}`} className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-[#174e3f]">{action}<ArrowRight size={13} /></a></article>)}
    </section>

    <section className={card} aria-label="Action required"><div className="flex items-center gap-2"><ShieldAlert size={18} className="text-[#a34e35]"/><h3 className="font-semibold">Action Required</h3></div>
      {actions.length ? <ul className="mt-3 divide-y divide-[#edf0ea]">{actions.map((item) => <li key={item.text} className="flex flex-wrap items-center justify-between gap-3 py-3"><span className={`flex items-center gap-2 text-sm ${item.urgent ? 'text-[#71382d]' : 'text-[#40584d]'}`}>{item.urgent && <AlertTriangle size={15} className="shrink-0 text-[#a34e35]"/>}{item.text}</span><a href={item.href} className={button}>{item.label}<ArrowRight size={13}/></a></li>)}</ul> : <p className="mt-3 rounded-xl bg-[#f5f9f2] p-4 text-sm text-[#55704f]">No operational actions are pending.</p>}
    </section>

    <section id="inventory-overview" className={card}><div className="flex items-center gap-2"><Package size={18} className="text-[#55704f]"/><h3 className="font-semibold">Inventory Overview</h3><button type="button" onClick={() => onNavigate('Inventory')} className={`${button} ml-auto`}>Manage inventory</button></div>
      <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">{stat('Available', data.inventory.available)}{stat('Reserved', data.inventory.reserved)}{stat('Expiring soon', data.inventory.expiring_soon)}{stat('Expired', data.inventory.expired)}{stat('Depleted', data.inventory.depleted)}</dl>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 rounded-xl bg-[#f7f8f5] p-3 text-sm"><span>Pricing configured: <b>{data.inventory.pricing_configured}</b></span><button type="button" onClick={() => onNavigate('Inventory')} className="text-left text-[#174e3f]">Pricing missing: <b>{data.inventory.pricing_missing}</b> · manage</button></div>
    </section>

    <div className="grid gap-6 xl:grid-cols-2">
      <section id="donation-queue" className={card}><h3 className="font-semibold">Donations Awaiting Review</h3>{data.recent_donations.length ? <ul className="mt-3 divide-y divide-[#edf0ea]">{data.recent_donations.map((d, i) => <li key={`${d.created_at}-${i}`} className="flex items-center justify-between gap-3 py-3"><div className="min-w-0"><p className="truncate text-sm font-medium">{d.medicine_name || 'Medicine details pending confirmation'}</p><p className="mt-1 text-xs text-[#718078]">Submitted {dateLabel(d.created_at)} · Extraction {d.extraction_status.replaceAll('_', ' ').toLowerCase()} · {d.details_confirmed ? 'Confirmed' : 'Unconfirmed'}</p></div>      <button type="button" onClick={() => onNavigate('Donations')} className={button}>Review</button></li>)}</ul> : <p className="mt-3 text-sm text-[#718078]">No donations awaiting review.</p>}</section>

      <section id="request-queue" className={card}><h3 className="font-semibold">Requests Requiring Attention</h3>{data.pending_requests.length ? <ul className="mt-3 divide-y divide-[#edf0ea]">{data.pending_requests.map((r, i) => <li key={`${r.created_at}-${i}`} className="flex items-center justify-between gap-3 py-3"><div><p className="text-sm font-medium">{r.medicine_name} {r.strength || ''} · {r.quantity} {r.unit}</p><p className="mt-1 text-xs text-[#718078]">{dateLabel(r.created_at)} · Prescription {r.prescription_status || 'not applicable'} · Payment {r.payment_status || 'not required'}</p></div>      <button type="button" onClick={() => onNavigate('Patient Requests')} className={button}>Review request</button></li>)}</ul> : <p className="mt-3 text-sm text-[#718078]">No requests require action.</p>}</section>

      <section id="prescription-queue" className={card}><div className="flex items-center gap-2"><ClipboardCheck size={17} className="text-[#55704f]"/><h3 className="font-semibold">Prescription Verification</h3></div>{data.prescription_queue.length ? <ul className="mt-3 divide-y divide-[#edf0ea]">{data.prescription_queue.map((r, i) => <li key={`${r.created_at}-${i}`} className="flex items-center justify-between gap-3 py-3"><div><p className="text-sm font-medium">{r.medicine_name} {r.strength || ''}</p><p className="mt-1 text-xs text-[#718078]">Request {dateLabel(r.created_at)} · {r.verification_status.replaceAll('_', ' ').toLowerCase()}</p></div>      <button type="button" onClick={() => onNavigate('Prescriptions')} className={button}>Verify</button></li>)}</ul> : <p className="mt-3 text-sm text-[#718078]">No prescriptions awaiting verification.</p>}</section>

      <section id="dispensing-queue" className={card}><h3 className="font-semibold">Ready for Dispensing</h3>{data.dispensing_queue.length ? <ul className="mt-3 divide-y divide-[#edf0ea]">{data.dispensing_queue.map((r, i) => <li key={`${r.created_at}-${i}`} className="flex items-center justify-between gap-3 py-3"><div><p className="text-sm font-medium">{r.medicine_name} {r.strength || ''} · {r.quantity} {r.unit}</p><p className="mt-1 text-xs text-[#718078]">{dateLabel(r.created_at)} · {r.payment_status.replaceAll('_', ' ').toLowerCase()} · {r.pickup_readiness.replaceAll('_', ' ').toLowerCase()}</p></div>      <button type="button" onClick={() => onNavigate('Patient Requests')} className={button}>Open queue</button></li>)}</ul> : <p className="mt-3 text-sm text-[#718078]">No requests are ready for dispensing.</p>}</section>

      <section id="expiry-alerts" className={card}><div className="flex items-center gap-2"><Pill size={17} className="text-[#55704f]"/><h3 className="font-semibold">Urgent Inventory</h3>      <button type="button" onClick={() => onNavigate('Inventory')} className={`${button} ml-auto`}>View inventory</button></div>{data.expiry_alerts.length ? <div className="mt-3 overflow-x-auto"><table className="w-full min-w-[460px] text-left text-xs"><thead className="text-[#718078]"><tr><th className="py-2 pr-3 font-medium">Medicine</th><th className="py-2 pr-3 font-medium">Quantity</th><th className="py-2 pr-3 font-medium">Expiry</th><th className="py-2 font-medium">Status</th></tr></thead><tbody className="divide-y divide-[#edf0ea]">{data.expiry_alerts.map((r, i) => <tr key={`${r.medicine_name}-${i}`}><td className="py-2 pr-3 font-medium">{r.medicine_name} {r.strength || ''}</td><td className="py-2 pr-3">{r.quantity} {r.unit}</td><td className="py-2 pr-3">{dateLabel(r.expiry_date)}</td><td className={`py-2 font-semibold ${r.status === 'Expired' ? 'text-red-700' : 'text-amber-800'}`}>{r.status}</td></tr>)}</tbody></table></div> : <p className="mt-3 text-sm text-[#718078]">No medicines are expiring soon.</p>}</section>

      <section id="waste-overview" className={card}><div className="flex items-center gap-2"><Trash2 size={17} className="text-[#55704f]"/><h3 className="font-semibold">Waste Summary</h3>      <button type="button" onClick={() => onNavigate('Waste Management')} className={`${button} ml-auto`}>Manage waste</button></div><dl className="mt-4 grid grid-cols-3 gap-2">{stat('Disposal pending', data.waste_summary.disposal_pending)}{stat('Collected', data.waste_summary.collected)}{stat('Disposed', data.waste_summary.disposed)}</dl>{data.waste_summary.pending_items.length ? <ul className="mt-3 divide-y divide-[#edf0ea]">{data.waste_summary.pending_items.map((w, i) => <li key={`${w.created_at}-${i}`} className="py-2 text-sm">{w.medicine_name || 'Waste record'} · {w.quantity} units · disposal pending</li>)}</ul> : <p className="mt-3 text-sm text-[#718078]">No waste actions are pending.</p>}</section>
    </div>
    <section id="notifications" className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[#e4e9e0] bg-[#f7f8f5] p-4"><p className="text-sm"><Bell size={15} className="mr-2 inline"/>Unread notifications: <b>{s.unread_notifications}</b></p>    <button type="button" onClick={() => onNavigate('Notifications')} className={button}>View notifications</button></section>
  </div>
}
