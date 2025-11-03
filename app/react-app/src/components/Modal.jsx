import React from 'react'

export default function Modal({ title, children, onClose, actions }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black opacity-30" onClick={onClose} />
      <div className="bg-white rounded shadow-lg z-10 max-w-xl w-full p-6">
        {title && <h3 className="text-lg font-semibold mb-3">{title}</h3>}
        <div>{children}</div>
        {actions && <div className="mt-4 flex gap-2 justify-end">{actions}</div>}
      </div>
    </div>
  )
}
