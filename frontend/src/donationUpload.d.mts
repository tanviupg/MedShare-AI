export class DonationUploadError extends Error {
  status: number
  constructor(message: string, status: number)
}

export function uploadDonationPhoto(options: {
  fetchImpl?: typeof fetch
  apiBaseUrl: string
  donationId: string
  token: string
  file: File
  finalize: boolean
}): Promise<Response>
