import { useEffect, useState } from 'react'
import { API_BASE_URL } from './config'
import { safeApiErrorMessage } from './apiErrors.mjs'

type StatusCounts = { total: number; by_status: Record<string, number> }
type PlatformDashboard = {
  clinics: { total: number; pending: number; verified: number; rejected: number }
  users: { total: number; by_role: Record<string, number> }
  donations: StatusCounts
  inventory: { available: number; reserved: number }
  requests: StatusCounts
  waste: StatusCounts
}

const cardClass = 'rounded-2xl border border-[#e4e9e0] bg-white p-5'
const labelize = (value: string) => value.toLowerCase().replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())

export default function AdminDashboard({ token }: { token: string }) {
  const [data, setData] = useState<PlatformDashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    fetch(`${API_BASE_URL}/admin/dashboard`, { headers: { Authorization: `Bearer ${token}` }, signal: controller.signal })
      .then(async (response) => {
        const body = await response.json() as PlatformDashboard & { detail?: string }
        if (!response.ok) throw new Error(safeApiErrorMessage(body, 'Could not load platform dashboard.'))
        setData(body)
      }).catch((cause: unknown) => {
        if (cause instanceof Error && cause.name !== 'AbortError') setError(cause.message || 'Could not load platform dashboard.')
      }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [token, refreshKey])

  if (loading && !data) return <div className="mt-6 rounded-2xl border border-[#e4e9e0] bg-white p-8 text-sm text-[#718078]" role="status">Loading platform totals...</div>
  if (error && !data) return <div className="mt-6 rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800" role="alert"><p>{error}</p><button type="button" onClick={() => setRefreshKey((key) => key + 1)} className="mt-3 rounded-full border border-red-300 px-4 py-2 font-semibold">Retry</button></div>
  if (!data) return null

  const allZero = data.clinics.total + data.donations.total + data.inventory.available + data.inventory.reserved + data.requests.total + data.waste.total === 0
  const statusCard = (title: string, counts: StatusCounts) => <section className={cardClass} key={title}>
    <div className="flex items-baseline justify-between gap-3"><h3 className="font-semibold">{title}</h3><span className="text-2xl font-semibold">{counts.total}</span></div>
    <dl className="mt-4 space-y-2">{Object.entries(counts.by_status).map(([status, count]) => <div key={status} className="flex justify-between gap-3 text-sm"><dt className="text-[#718078]">{labelize(status)}</dt><dd className="font-medium">{count}</dd></div>)}</dl>
  </section>

  return <section className="mt-6" aria-label="Admin platform dashboard">
    <header className="mb-4 flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-[.12em] text-[#71886d]">Platform oversight</p><h1 className="mt-1 text-2xl font-semibold tracking-tight">Admin Dashboard</h1><p className="mt-1 text-sm text-[#718078]">Read-only aggregate totals across MedShare AI.</p></div><button type="button" onClick={() => setRefreshKey((key) => key + 1)} disabled={loading} className="rounded-full border border-[#dce4d9] px-4 py-2.5 text-sm font-semibold text-[#55704f] disabled:opacity-50">Refresh totals</button></header>
    {error && <p role="alert" className="mb-4 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900">Refresh failed: {error}. Showing the last loaded totals.</p>}
    {allZero && <p className="mb-4 rounded-xl border border-dashed border-[#dce4d9] px-4 py-3 text-sm text-[#718078]">No platform records yet. All aggregate counts are zero.</p>}
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label="Platform totals">
      <article className={cardClass}><div className="flex items-baseline justify-between"><h3 className="font-semibold">Clinics</h3><span className="text-2xl font-semibold">{data.clinics.total}</span></div><dl className="mt-4 grid grid-cols-3 gap-2 text-center text-sm"><div><dt className="text-[#718078]">Pending</dt><dd className="mt-1 font-semibold">{data.clinics.pending}</dd></div><div><dt className="text-[#718078]">Approved</dt><dd className="mt-1 font-semibold">{data.clinics.verified}</dd></div><div><dt className="text-[#718078]">Rejected</dt><dd className="mt-1 font-semibold">{data.clinics.rejected}</dd></div></dl></article>
      <article className={cardClass}><div className="flex items-baseline justify-between"><h3 className="font-semibold">Registered users</h3><span className="text-2xl font-semibold">{data.users.total}</span></div><dl className="mt-4 space-y-2">{Object.entries(data.users.by_role).map(([role, count]) => <div key={role} className="flex justify-between gap-3 text-sm"><dt className="text-[#718078]">{labelize(role)}</dt><dd className="font-medium">{count}</dd></div>)}</dl></article>
      {statusCard('Donations', data.donations)}
      <article className={cardClass}><h3 className="font-semibold">Inventory quantities</h3><dl className="mt-4 space-y-2 text-sm"><div className="flex justify-between"><dt className="text-[#718078]">Available units</dt><dd className="font-semibold">{data.inventory.available}</dd></div><div className="flex justify-between"><dt className="text-[#718078]">Reserved units</dt><dd className="font-semibold">{data.inventory.reserved}</dd></div></dl></article>
      {statusCard('Patient requests', data.requests)}
      {statusCard('Waste and disposal', data.waste)}
    </section>
  </section>
}
