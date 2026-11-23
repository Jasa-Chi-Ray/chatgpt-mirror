import assert from 'node:assert/strict'
import { test } from 'node:test'
import { detectBrowserIp } from '../src/api/browser-ip.ts'

test('detects IPv4 and IPv6 without cookies, credentials, or referrer', async t => {
  for (const ip of ['203.0.113.9', '2001:db8::9']) {
    const fetch = t.mock.method(globalThis, 'fetch', async (url, options) => {
      assert.equal(url, 'https://api64.ipify.org?format=json')
      assert.equal(options.credentials, 'omit')
      assert.equal(options.referrerPolicy, 'no-referrer')
      assert.equal(options.cache, 'no-store')
      assert.equal(options.headers, undefined)
      assert.equal(options.body, undefined)
      return Response.json({ ip })
    })
    assert.equal(await detectBrowserIp(), ip)
    fetch.mock.restore()
  }
})

test('failed, blocked, and malformed lookups do not reject', async t => {
  for (const response of [
    new Response('', { status: 503 }),
    new Response('<html>blocked</html>'),
    Response.json({ ip: 'not-an-ip' }),
    Response.json({ ip: 'a'.repeat(46) }),
    Response.json({ ip: ['203.0.113.9'] }),
    Response.json(null),
  ]) {
    const fetch = t.mock.method(globalThis, 'fetch', async () => response)
    assert.equal(await detectBrowserIp(), null)
    fetch.mock.restore()
  }
  t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('Network blocked') })
  assert.equal(await detectBrowserIp(), null)
})

test('timeout returns within the deadline even when fetch never settles', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  let signal
  t.mock.method(globalThis, 'fetch', (_url, options) => {
    signal = options.signal
    return new Promise(() => {})
  })
  const pending = detectBrowserIp()
  t.mock.timers.tick(1500)
  assert.equal(await pending, null)
  assert.equal(signal.aborted, true)
})

test('each operation detects afresh instead of reusing an old network address', async t => {
  const addresses = ['203.0.113.9', '2001:db8::9']
  t.mock.method(globalThis, 'fetch', async () => Response.json({ ip: addresses.shift() }))
  assert.equal(await detectBrowserIp(), '203.0.113.9')
  assert.equal(await detectBrowserIp(), '2001:db8::9')
})
