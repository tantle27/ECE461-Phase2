import React from 'react'

export default function AuditTrail({ entries = [] }) {
  if (!entries || entries.length === 0) return <div className="text-sm text-gray-600">No audit entries available.</div>
  return (
    <ol className="border-l-2 border-gray-200">
      {entries.map((e, idx) => (
        <li key={idx} className="mb-4 ml-4">
          <div className="text-sm text-gray-800 font-medium">{e.action}</div>
          <div className="text-xs text-gray-500">
            By: {e?.user?.name || 'system'} • {e?.date ? new Date(e.date).toLocaleString() : (e?.timestamp ? new Date(e.timestamp).toLocaleString() : '')}
          </div>
          {e.artifact && (
            <div className="mt-1 text-xs text-gray-600">{e.artifact.type}:{e.artifact.id} — {e.artifact.name}</div>
          )}
          {e.detail && <div className="mt-1 text-sm text-gray-700">{e.detail}</div>}
        </li>
      ))}
    </ol>
  )
}
