import React, { useState } from 'react'
import { isValidUrl, isValidId, required } from '../lib/validators'

export default function ArtifactForm({ onSubmit }) {
  const [type, setType] = useState('model')
  const [url, setUrl] = useState('')
  const [id, setId] = useState('')
  const [error, setError] = useState(null)

  function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    if (!required(id) || !isValidId(id)) return setError('ID is required and must be alphanumeric or hyphens')
    if (!required(url) || !isValidUrl(url)) return setError('Valid URL is required')
    onSubmit({ type, id, url })
  }

  return (
    <form onSubmit={handleSubmit} className="bg-white p-4 rounded shadow flex flex-col gap-3" aria-label="Create artifact">
      {error && <div className="text-sm text-red-700">{error}</div>}
      <div>
        <label className="block text-sm font-medium text-gray-700">Artifact Type</label>
        <select value={type} onChange={e => setType(e.target.value)} className="mt-1 p-2 border rounded">
          <option value="model">Model</option>
          <option value="dataset">Dataset</option>
          <option value="code">Code</option>
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700">Artifact ID</label>
        <input value={id} onChange={e => setId(e.target.value)} className="mt-1 p-2 border rounded w-full" placeholder="artifact-123" />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700">Artifact URL</label>
        <input value={url} onChange={e => setUrl(e.target.value)} className="mt-1 p-2 border rounded w-full" placeholder="https://..." />
      </div>

      <div className="flex gap-2">
        <button className="px-3 py-2 bg-blue-700 text-white rounded" type="submit">Create</button>
      </div>
    </form>
  )
}
