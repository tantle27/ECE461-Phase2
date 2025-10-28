import React, { useState } from 'react'
import axios from 'axios'

export default function FileUploader({ uploadUrl }) {
  const [file, setFile] = useState(null)
  const [status, setStatus] = useState('')

  async function handleUpload(e) {
    e.preventDefault()
    if (!file) return setStatus('Please choose a file first')
    const fd = new FormData()
    fd.append('file', file)
    try {
      setStatus('uploading')
      const resp = await axios.post(uploadUrl || import.meta.env.VITE_API_URL + '/upload', fd, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      setStatus('done: ' + (resp.data?.message || 'ok'))
    } catch (err) {
      setStatus('error: ' + (err?.message || 'upload failed'))
    }
  }

  return (
    <div className="bg-white shadow rounded p-6">
      <form onSubmit={handleUpload} className="flex flex-col gap-4" aria-labelledby="upload-heading">
        <h3 id="upload-heading" className="sr-only">File upload</h3>

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
      </form>
    </div>
  )
}
