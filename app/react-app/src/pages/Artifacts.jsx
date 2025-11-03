import React, { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import ArtifactForm from '../components/ArtifactForm'
import ArtifactList from '../components/ArtifactList'
import ErrorBanner from '../components/ErrorBanner'
import Loading from '../components/Loading'
import LineageGraph from '../components/LineageGraph'
import AuditTrail from '../components/AuditTrail'

export default function ArtifactsPage() {
  const { client } = useAuth()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [items, setItems] = useState([])
  const [selected, setSelected] = useState(null)
  const [audit, setAudit] = useState([])
  const [lineage, setLineage] = useState({ nodes: [], links: [] })

  async function handleCreate({ type, id, url }) {
    setError(null)
    setLoading(true)
    try {
      await client.post(`/artifact/${type}`, { id, url })
      // show created artifact
      setItems(prev => [{ id, name: id, type, url }, ...prev])
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }

  async function fetchById(artifactType, artifactId) {
    setError(null)
    setLoading(true)
    try {
      const resp = await client.get(`/artifact/${artifactType}/${artifactId}`)
      setSelected(resp.data)
      // fetch audit and lineage for admin sections
      try { const a = await client.get(`/artifact/${artifactType}/${artifactId}/audit`); setAudit(a.data) } catch (e) { /* ignore */ }
      try { const l = await client.get(`/artifact/${artifactType}/${artifactId}/lineage`); setLineage(l.data || { nodes: [], links: [] }) } catch (e) { /* ignore */ }
    } catch (err) {
      setError(err)
      setSelected(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-semibold">Artifacts</h2>

      <div className="grid md:grid-cols-2 gap-6">
        <div>
          <h3 className="text-lg font-medium mb-2">Create Artifact</h3>
          <ArtifactForm onSubmit={handleCreate} />
        </div>

        <div>
          <h3 className="text-lg font-medium mb-2">Get Artifact by ID</h3>
          <GetByIdForm onFetch={fetchById} />
        </div>
      </div>

      <ErrorBanner error={error} />
      {loading && <Loading />}

      <section>
        <h3 className="text-lg font-medium mb-2">Selected Artifact</h3>
        {selected ? <ArtifactList items={[selected]} /> : <div className="text-sm text-gray-600">No artifact selected.</div>}
      </section>

      <section>
        <h3 className="text-lg font-medium mb-2">Rate / Metrics</h3>
        {/* placeholder for metrics display; could use recharts */}
        {selected?.metrics ? <pre className="bg-gray-50 p-3 rounded">{JSON.stringify(selected.metrics, null, 2)}</pre> : <div className="text-sm text-gray-600">No metrics available</div>}
      </section>

      <section>
        <h3 className="text-lg font-medium mb-2">Cost</h3>
        <div className="text-sm text-gray-700">Standalone: {selected?.cost?.standalone ?? '—'} • Total: {selected?.cost?.total ?? '—'}</div>
      </section>

      <section>
        <h3 className="text-lg font-medium mb-2">Lineage</h3>
        <LineageGraph nodes={lineage.nodes} links={lineage.links} />
      </section>

      <section>
        <h3 className="text-lg font-medium mb-2">Audit Trail</h3>
        <AuditTrail entries={audit} />
      </section>
    </div>
  )
}

function GetByIdForm({ onFetch }) {
  const [type, setType] = useState('model')
  const [id, setId] = useState('')
  const [err, setErr] = useState(null)

  function submit(e) {
    e.preventDefault()
    setErr(null)
    if (!id) return setErr('ID required')
    onFetch(type, id)
  }

  return (
    <form onSubmit={submit} className="bg-white p-4 rounded shadow flex gap-2 items-end">
      <div>
        <label className="block text-sm text-gray-700">Type</label>
        <select value={type} onChange={e => setType(e.target.value)} className="mt-1 p-2 border rounded">
          <option value="model">Model</option>
          <option value="dataset">Dataset</option>
          <option value="code">Code</option>
        </select>
      </div>
      <div className="flex-1">
        <label className="block text-sm text-gray-700">ID</label>
        <input value={id} onChange={e => setId(e.target.value)} className="mt-1 p-2 border rounded w-full" />
      </div>
      <div>
        <button className="px-3 py-2 bg-blue-700 text-white rounded">Fetch</button>
      </div>
      {err && <div className="text-sm text-red-700">{err}</div>}
    </form>
  )
}
