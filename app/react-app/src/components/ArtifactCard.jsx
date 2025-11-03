import React from 'react'

export default function ArtifactCard({ artifact }) {
  if (!artifact) return null
  const md = artifact.metadata || {}
  const id = md.id || artifact.id
  const name = md.name || artifact.name
  const type = md.type || artifact.type
  const url = (artifact.data && artifact.data.url) || artifact.url
  const metadata = artifact.metadata
  return (
    <article className="p-4 bg-white rounded shadow">
      <header className="flex justify-between items-start">
        <div>
          <h4 className="text-lg font-semibold">{name || id}</h4>
          <div className="text-xs text-gray-500">{type}</div>
        </div>
        <div className="text-sm text-gray-600">ID: <span className="font-mono">{id}</span></div>
      </header>

      {metadata && (
        <section className="mt-3 text-sm text-gray-700">
          <pre className="text-xs bg-gray-50 p-2 rounded overflow-auto">{JSON.stringify(metadata, null, 2)}</pre>
        </section>
      )}

      {url && (
        <div className="mt-3">
          <a className="text-blue-600 underline" href={url} target="_blank" rel="noreferrer">Open data URL</a>
        </div>
      )}
    </article>
  )
}
