import test from 'node:test'
import assert from 'node:assert/strict'
import { uploadDonationPhoto } from '../src/donationUpload.mjs'

const file = new Blob(['image bytes'], { type: 'image/jpeg' })
file.name = 'dog.jpg'
const request = { apiBaseUrl: '/api', donationId: 'donation-123', token: 'token', file, finalize: true }

test('valid photo sends the expected multipart request and accepts a successful response', async () => {
  let captured
  const response = new Response('[]', { status: 201 })
  const result = await uploadDonationPhoto({ ...request, fetchImpl: async (...args) => { captured = args; return response } })
  assert.equal(result, response)
  assert.equal(captured[0], '/api/donations/donation-123/images?finalize=true')
  assert.equal(captured[1].method, 'POST')
  assert.equal(captured[1].headers.Authorization, 'Bearer token')
  assert.equal(captured[1].headers['Content-Type'], undefined)
  assert.equal(captured[1].body.getAll('files').length, 1)
})

test('medicine-content rejection shows the concise message with its filename', async () => {
  await assert.rejects(
    uploadDonationPhoto({ ...request, fetchImpl: async () => Response.json({ detail: 'This photo does not appear to show medicine or medicine packaging. Please upload a clear photo of the medicine.' }, { status: 415 }) }),
    /dog\.jpg: Not a medicine photo\. Upload a photo of the medicine or its packaging\./,
  )
})

test('server/API and network failures remain distinct and actionable', async () => {
  await assert.rejects(
    uploadDonationPhoto({ ...request, fetchImpl: async () => new Response('oops', { status: 503 }) }),
    /upload service is temporarily unavailable/,
  )
  await assert.rejects(
    uploadDonationPhoto({ ...request, fetchImpl: async () => { throw new TypeError('offline') } }),
    /Check your connection and retry/,
  )
})
