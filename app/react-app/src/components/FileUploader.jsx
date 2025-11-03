import React, { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import ArtifactCard from './ArtifactCard'

export default function FileUploader() {
  const [file, setFile] = useState(null)
  const [status, setStatus] = useState('')
  const [artifactType, setArtifactType] = useState('model')
  const [artifactId, setArtifactId] = useState('')
  const [artifactName, setArtifactName] = useState('')
  const [result, setResult] = useState(null)
  const { client } = useAuth()

  async function handleUpload(e) {
    e.preventDefault()
    if (!file) return setStatus('Please choose a file first')
    const fd = new FormData()
    fd.append('file', file)
    fd.append('artifact_type', artifactType)
    if (artifactId) fd.append('id', artifactId)
    if (artifactName) fd.append('name', artifactName)
    try {
      setStatus('uploading')
      const resp = await client.post('/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
      setResult(resp.data?.artifact)
      setStatus('done')
    } catch (err) {
      setStatus('error: ' + (err?.message || 'upload failed'))
      setResult(null)
    }
  }

  return (
    <div className="bg-white shadow rounded p-6">
      <form onSubmit={handleUpload} className="flex flex-col gap-4" aria-labelledby="upload-heading">
        <h3 id="upload-heading" className="sr-only">File upload</h3>

        <div className="grid md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">Artifact Type</label>
            <select value={artifactType} onChange={e => setArtifactType(e.target.value)} className="mt-1 p-2 border rounded w-full">
              <option value="model">Model</option>
              <option value="dataset">Dataset</option>
              <option value="code">Code</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Artifact ID (optional)</label>
            <input value={artifactId} onChange={e => setArtifactId(e.target.value)} className="mt-1 p-2 border rounded w-full" placeholder="leave empty to auto-generate" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Name (optional)</label>
            <input value={artifactName} onChange={e => setArtifactName(e.target.value)} className="mt-1 p-2 border rounded w-full" placeholder="display name" />
          </div>
        </div>

        <div>
          <label htmlFor="fileInput" className="block text-sm font-medium text-gray-700">Choose a file</label>
          <input
            id="fileInput"
            name="file"
            type="file"
            accept="*/*"
            onChange={e => setFile(e.target.files?.[0] ?? null)}
            className="mt-2"
            aria-describedby="file-desc"
          />
          <div id="file-desc" className="text-xs text-gray-600 mt-1">Maximum file size and accepted types are determined by the server.</div>
        </div>

        <div className="flex gap-2">
          <button className="px-4 py-2 bg-blue-700 text-white rounded focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500" type="submit">Upload</button>
          <button aria-label="Clear selected file" className="px-4 py-2 bg-gray-200 rounded focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500" type="button" onClick={() => setFile(null)}>Clear</button>
        </div>

        {file && (
          <p className="text-sm" aria-live="polite">Selected file: {file.name}</p>
        )}

        <div id="upload-status" role="status" aria-live="polite" aria-atomic="true" className="text-sm text-gray-700">
          {status}
        </div>

        {result && (
          <div className="mt-4">
            <h4 className="text-sm font-medium mb-2">Uploaded Artifact</h4>
            <ArtifactCard artifact={result} />
          </div>
        )}
      </form>
    </div>
  )
}
