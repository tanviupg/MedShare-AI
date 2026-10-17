import assert from 'node:assert/strict'
import { apiErrorMessage, safeErrorMessage } from '../src/apiErrors.mjs'

assert.equal(safeErrorMessage({ error: { message: 'Medicine is unavailable.' } }), 'Medicine is unavailable.')
assert.equal(await apiErrorMessage(new Response(JSON.stringify({ detail: [{ loc: ['body', 'quantity'], msg: 'Input should be greater than 0', type: 'greater_than' }] }), { status: 422 }), 'Could not update.'), 'Please check the information and try again.')
assert.equal(await apiErrorMessage(new Response(JSON.stringify({ detail: [{ loc: ['body'], msg: 'Expired medicine cannot be approved', type: 'value_error' }] }), { status: 422 }), 'Could not save review.'), 'This medicine has expired and cannot be approved. Please reject it and record it in Waste Management.')
assert.equal(safeErrorMessage({ detail: '[object Object]' }, 'Could not save.'), 'Could not save.')
assert.equal(safeErrorMessage('Traceback (most recent call last): secret'), 'Something went wrong. Please try again.')
console.log('5 frontend API error handling assertions passed')
