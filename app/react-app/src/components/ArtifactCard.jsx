import React from 'react'

export default function ArtifactCard({ artifact }) {
  if (!artifact) return null
  const md = artifact.metadata || {}
  const id = md.id || artifact.id
  const name = md.name || artifact.name
  const type = md.type || artifact.type
  const version = md.version || artifact.version || '1.0.0'
  const data = artifact.data || {}
  const url = data.url || artifact.url
  
  return (
    <article className="p-4 bg-white rounded-lg shadow-sm border border-gray-200 hover:shadow-md transition-shadow">
      <header className="flex justify-between items-start mb-3">
        <div className="flex-1">
          <h4 className="text-lg font-semibold text-gray-900">{name || id}</h4>
          <div className="flex gap-2 mt-1">
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">
              {type}
            </span>
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">
              v{version}
            </span>
          </div>
        </div>
        <div className="text-xs text-gray-500">
          <span className="font-mono bg-gray-50 px-2 py-1 rounded">{id}</span>
        </div>
      </header>

      {/* Data details */}
      {Object.keys(data).length > 0 && (
        <section className="mt-3 space-y-2">
          {data.url && (
            <div className="text-sm">
              <span className="text-gray-600">URL: </span>
              <a className="text-blue-600 hover:underline break-all" href={data.url} target="_blank" rel="noreferrer">
                {data.url}
              </a>
            </div>
          )}
          {data.path && (
            <div className="text-sm">
              <span className="text-gray-600">Path: </span>
              <span className="font-mono text-xs bg-gray-50 px-1 py-0.5 rounded">{data.path}</span>
            </div>
          )}
          {data.s3_key && (
            <div className="text-sm">
              <span className="text-gray-600">S3: </span>
              <span className="font-mono text-xs bg-gray-50 px-1 py-0.5 rounded">
                {data.s3_bucket}/{data.s3_key}
              </span>
            </div>
          )}
          {data.size && (
            <div className="text-sm">
              <span className="text-gray-600">Size: </span>
              <span className="font-semibold">{(data.size / 1024 / 1024).toFixed(2)} MB</span>
            </div>
          )}
          {data.content_type && (
            <div className="text-sm">
              <span className="text-gray-600">Type: </span>
              <span className="text-gray-800">{data.content_type}</span>
            </div>
          )}
          {data.original_filename && (
            <div className="text-sm">
              <span className="text-gray-600">Original: </span>
              <span className="text-gray-800">{data.original_filename}</span>
            </div>
          )}
        </section>
      )}

      {/* Fallback URL display */}
      {!data.url && url && (
        <div className="mt-3">
          <a className="text-blue-600 hover:underline text-sm" href={url} target="_blank" rel="noreferrer">
            Open URL →
          </a>
        </div>
      )}
    </article>
  )
}
