import React, { useState } from 'react'
import { useAuth } from '../context/AuthContext'

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
      // Clear form
      setFile(null)
      setArtifactId('')
      setArtifactName('')
    } catch (err) {
      setStatus('error: ' + (err?.response?.data?.message || err?.message || 'upload failed'))
      setResult(null)
    }
  }

  return (
    <div className="bg-white shadow rounded-lg p-6">
      <form onSubmit={handleUpload} className="flex flex-col gap-4" aria-labelledby="upload-heading">
        <h3 id="upload-heading" className="text-lg font-semibold text-gray-900">Upload File</h3>

        <div className="grid md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Artifact Type *</label>
            <select value={artifactType} onChange={e => setArtifactType(e.target.value)} className="w-full p-2 border rounded focus:ring-2 focus:ring-blue-500">
              <option value="model">Model</option>
              <option value="dataset">Dataset</option>
              <option value="code">Code</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Artifact ID</label>
            <input 
              value={artifactId} 
              onChange={e => setArtifactId(e.target.value)} 
              className="w-full p-2 border rounded focus:ring-2 focus:ring-blue-500" 
              placeholder="Auto-generated if empty" 
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Display Name</label>
            <input 
              value={artifactName} 
              onChange={e => setArtifactName(e.target.value)} 
              className="w-full p-2 border rounded focus:ring-2 focus:ring-blue-500" 
              placeholder="Defaults to filename" 
            />
          </div>
        </div>

        <div>
          <label htmlFor="fileInput" className="block text-sm font-medium text-gray-700 mb-2">Choose File *</label>
          <input
            id="fileInput"
            name="file"
            type="file"
            accept="*/*"
            onChange={e => setFile(e.target.files?.[0] ?? null)}
            className="block w-full text-sm text-gray-500
              file:mr-4 file:py-2 file:px-4
              file:rounded file:border-0
              file:text-sm file:font-semibold
              file:bg-blue-50 file:text-blue-700
              hover:file:bg-blue-100"
            aria-describedby="file-desc"
          />
          <div id="file-desc" className="text-xs text-gray-600 mt-1">
            Supported: .zip packages for models, data files for datasets, source code for code artifacts
          </div>
        </div>

        {file && (
          <div className="bg-gray-50 p-3 rounded border border-gray-200">
            <div className="text-sm">
              <span className="font-medium">Selected: </span>
              <span className="text-gray-700">{file.name}</span>
              <span className="text-gray-500 ml-2">({(file.size / 1024).toFixed(2)} KB)</span>
            </div>
          </div>
        )}

        <div className="flex gap-3">
          <button 
            className="px-4 py-2 bg-blue-700 text-white rounded hover:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:bg-gray-400 disabled:cursor-not-allowed" 
            type="submit"
            disabled={!file || status === 'uploading'}
          >
            {status === 'uploading' ? 'Uploading...' : 'Upload'}
          </button>
          <button 
            aria-label="Clear selected file" 
            className="px-4 py-2 bg-gray-200 text-gray-700 rounded hover:bg-gray-300 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500" 
            type="button" 
            onClick={() => { setFile(null); setStatus(''); setResult(null) }}
          >
            Clear
          </button>
        </div>

        {status && status !== 'uploading' && status !== 'done' && (
          <div id="upload-status" role="alert" aria-live="assertive" className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
            {status}
          </div>
        )}

        {status === 'done' && result && (
          <div className="mt-4 p-4 bg-green-50 border border-green-200 rounded">
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-green-400" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3">
                <h4 className="text-sm font-medium text-green-800 mb-2">Upload Successful!</h4>
                <div className="text-sm text-green-700 space-y-1">
                  <div><span className="font-semibold">ID:</span> {result.metadata?.id}</div>
                  <div><span className="font-semibold">Name:</span> {result.metadata?.name}</div>
                  <div><span className="font-semibold">Type:</span> {result.metadata?.type}</div>
                  {result.data?.s3_key && <div><span className="font-semibold">Storage:</span> S3 ({result.data.s3_bucket})</div>}
                  {result.data?.path && <div><span className="font-semibold">Storage:</span> Local ({result.data.path})</div>}
                  {result.data?.size && <div><span className="font-semibold">Size:</span> {(result.data.size / 1024 / 1024).toFixed(2)} MB</div>}
                  {result.data?.original_filename && <div><span className="font-semibold">Original:</span> {result.data.original_filename}</div>}
                </div>
              </div>
            </div>
          </div>
        )}
      </form>
    </div>
  )
}
