import axios from 'axios'

// Use environment variable for API base URL
// Production (Amplify): /api prefix routes to backend via _redirects
// Development (local): empty string routes to localhost via vite proxy
const isDevelopment = import.meta.env.MODE === 'development'
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || (isDevelopment ? '' : '/api')

function mapError(err) {
  if (!err || !err.response) return { status: 0, message: err?.message || 'Unknown error' }
  const { status, data } = err.response
  let message = data?.message || data || err.message || 'Error'
  switch (status) {
    case 400: message = message || 'Bad request'; break
    case 403: message = message || 'Authentication failed'; break
    case 404: message = message || 'Not found'; break
    case 409: message = message || 'Conflict'; break
    case 413: message = message || 'Too many results'; break
    case 424: message = message || 'Disqualified rating'; break
    case 500: message = message || 'Server error'; break
    case 501: message = message || 'Not implemented'; break
    case 502: message = message || 'External service error'; break
  }
  return { status, message, data }
}

const baseClient = axios.create({ baseURL: API_BASE_URL, timeout: 20000 })

// request interceptor to add X-Authorization if token present
function attachToken(instance, token) {
  instance.interceptors.request.use(config => {
    if (config?.skipAuth) return config
    if (token) {
      config.headers = config.headers || {}
      config.headers['X-Authorization'] = token
    }
    return config
  }, e => Promise.reject(e))
}

// create a new axios instance bound to a token
function createInstance(token) {
  const inst = axios.create({ baseURL: API_BASE_URL, timeout: 20000 })
  attachToken(inst, token)
  return inst
}

// wrapper for base client; supports skipAuth in config
async function request(method, url, data, config = {}) {
  try {
    const resp = await baseClient.request({ method, url, data, ...config })
    return resp
  } catch (err) {
    throw mapError(err)
  }
}

export default {
  put: (url, data, config) => request('put', url, data, config),
  post: (url, data, config) => request('post', url, data, config),
  get: (url, config) => request('get', url, null, config),
  delete: (url, config) => request('delete', url, null, config),
  createInstance,
}
