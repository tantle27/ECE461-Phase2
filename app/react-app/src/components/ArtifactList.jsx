import React from 'react'
import ArtifactCard from './ArtifactCard'

export default function ArtifactList({ items }) {
  if (!items || items.length === 0) return <div className="text-sm text-gray-600">No artifacts found.</div>
  return (
    <div className="grid gap-4">
      {items.map(it => (
        <ArtifactCard key={it.id || it.name} artifact={it} />
      ))}
    </div>
  )
}
