import { safeApiErrorMessage } from './apiErrors.mjs'

export class DonationUploadError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'DonationUploadError'
    this.status = status
  }
}

function responseMessage(response, body) {
  if (response.status === 401) return 'Your session has expired. Sign in again, then retry the photo.'
  if (response.status === 403) return 'Your account is not authorized to upload this photo. Sign in with a donor account.'
  if (response.status === 413) return safeApiErrorMessage(body, 'This photo exceeds the 5 MB limit. Choose a smaller photo.')
  if (response.status >= 500) return 'The upload service is temporarily unavailable. Try again shortly; your donation is saved.'
  const message = safeApiErrorMessage(body, `Photo upload failed (HTTP ${response.status}).`)
  if (message === 'This photo does not appear to show medicine or medicine packaging. Please upload a clear photo of the medicine.') {
    return 'Not a medicine photo. Upload a photo of the medicine or its packaging.'
  }
  return message
}

export async function uploadDonationPhoto({ fetchImpl = fetch, apiBaseUrl, donationId, token, file, finalize }) {
  const form = new FormData()
  form.append('files', file)
  let response
  try {
    response = await fetchImpl(`${apiBaseUrl}/donations/${donationId}/images?finalize=${finalize}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    })
  } catch {
    throw new Error(`${file.name}: Could not reach the upload service. Check your connection and retry; your donation is saved.`)
  }
  if (response.ok) return response

  let body
  try { body = await response.json() } catch { body = null }
  throw new DonationUploadError(`${file.name}: ${responseMessage(response, body)}`, response.status)
}
