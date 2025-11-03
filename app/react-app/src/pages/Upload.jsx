import React from 'react'
import FileUploader from '../components/FileUploader'

export default function Upload() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold text-gray-900">Upload Artifact</h2>
        <p className="text-gray-600 mt-1">Upload files to create artifacts with media attachments</p>
      </div>
      
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-blue-900 mb-2">Upload Guidelines</h3>
        <ul className="text-sm text-blue-800 space-y-1 list-disc list-inside">
          <li>Upload model packages (.zip containing model files and config.json)</li>
          <li>Upload dataset files (CSV, JSON, or compressed archives)</li>
          <li>Upload code artifacts (source files or repositories)</li>
          <li>Optionally specify an artifact ID or let the system auto-generate one</li>
          <li>Set a display name to make the artifact easier to identify</li>
        </ul>
      </div>
      
      <FileUploader />
    </div>
  )
}
