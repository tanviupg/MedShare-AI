import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const app = await readFile(new URL('../src/App.tsx', import.meta.url), 'utf8')

test('only a completed donation submission triggers a fresh donor form instance', () => {
  const failedUpload = app.indexOf('if (failed.length) {')
  const successfulSubmission = app.indexOf("setView('submitted')", failedUpload)
  assert.ok(failedUpload >= 0)
  assert.ok(successfulSubmission > failedUpload)
  assert.match(app.slice(failedUpload, successfulSubmission), /return false/)
  assert.match(app.slice(successfulSubmission, successfulSubmission + 180), /setDonorFormRevision/)
  assert.match(app, /<DonorDashboard key=\{donorFormRevision\}/)
})

test('successful completion clears files, previews metadata, camera state, form fields, and native input', () => {
  const resetStart = app.indexOf('async function submitForm')
  const resetEnd = app.indexOf('\n  async function inspectPhoto', resetStart)
  const reset = app.slice(resetStart, resetEnd)
  assert.match(reset, /if \(!await onSubmit\(event, selectedFiles\)\) return/)
  assert.match(reset, /setSelectedFiles\(\[\]\)/)
  assert.match(reset, /setQualityWarnings\(\{\}\)/)
  assert.match(reset, /setCameraError\(''\)/)
  assert.match(reset, /setRetakeIndex\(null\)/)
  assert.match(reset, /stopCamera\(\)/)
  assert.match(reset, /form\.reset\(\)/)
  assert.match(reset, /galleryInputRef\.current\.value = ''/)
})

test('failed uploads keep the draft retry record and leave the form intact', () => {
  const failedUpload = app.indexOf('if (failed.length) {')
  const completed = app.indexOf("setView('submitted')", failedUpload)
  const failurePath = app.slice(failedUpload, completed)
  assert.match(failurePath, /sessionStorage\.setItem\('medshare_donation_retry'/)
  assert.match(failurePath, /setView\('create'\)/)
  assert.match(failurePath, /return false/)
  const resetStart = app.indexOf('async function submitForm')
  const resetEnd = app.indexOf('\n  async function inspectPhoto', resetStart)
  assert.match(app.slice(resetStart, resetEnd), /if \(!await onSubmit\(event, selectedFiles\)\) return/)
})
