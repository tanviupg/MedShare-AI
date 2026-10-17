const EXPIRED_MEDICINE_MESSAGE = 'This medicine has expired and cannot be approved. Please reject it and record it in Waste Management.'

function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function readableString(value) {
  return typeof value === 'string' && value.trim() && !value.includes('[object Object]') ? value.trim() : null
}

function findMessage(value, depth = 0) {
  if (depth > 4) return null
  const direct = readableString(value)
  if (direct) return direct
  if (Array.isArray(value)) {
    for (const item of value) {
      const message = findMessage(item, depth + 1)
      if (message) return message
    }
    return null
  }
  if (!isRecord(value)) return null
  for (const key of ['message', 'detail', 'error', 'errors']) {
    if (key in value) {
      const message = findMessage(value[key], depth + 1)
      if (message) return message
    }
  }
  return null
}

export function safeErrorMessage(value, fallback = 'Something went wrong. Please try again.') {
  const message = findMessage(value)
  if (!message) return fallback
  if (/expir(?:ed|y).{0,80}(?:cannot|can't|not allowed)|(?:cannot|can't).{0,80}expir/i.test(message)) {
    return EXPIRED_MEDICINE_MESSAGE
  }
  if (/traceback|stack trace|\bat [\w./\\-]+\.(?:py|js|ts):\d+|\[object Object\]|\b(?:exception|sqlalchemy|psycopg|errno|trace id|internal server error)\b/i.test(message)) return fallback
  return message
}

export async function apiErrorMessage(response, fallback) {
  let body
  try { body = await response.json() } catch { return fallback }
  return safeApiErrorMessage(body, fallback)
}

export function safeApiErrorMessage(body, fallback) {
  // FastAPI validation details are structured and can contain implementation details.
  if (Array.isArray(body?.detail) || (isRecord(body?.detail) && !readableString(body.detail))) {
    const joined = JSON.stringify(body.detail)
    if (/expir.{0,80}(?:cannot|can't|not allowed)|(?:cannot|can't).{0,80}expir/i.test(joined)) return EXPIRED_MEDICINE_MESSAGE
    return 'Please check the information and try again.'
  }
  return safeErrorMessage(body, fallback)
}
