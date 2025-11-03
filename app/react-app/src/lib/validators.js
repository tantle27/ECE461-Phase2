export function isValidId(id) {
  return /^[A-Za-z0-9-]+$/.test(id)
}

export function isValidUrl(url) {
  try {
    const u = new URL(url)
    return ['http:', 'https:'].includes(u.protocol)
  } catch (e) {
    return false
  }
}

export function required(value) {
  return value !== undefined && value !== null && String(value).trim() !== ''
}
