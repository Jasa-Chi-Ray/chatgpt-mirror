export type LoginFingerprint = Record<string, string>
let fingerprintPromise: Promise<LoginFingerprint> | undefined

// HTTP deployments do not expose SubtleCrypto. Keep the same SHA-256 rendering
// hashes there without sending raw canvas pixels or font metrics to the server.
const sha256Fallback = (bytes: Uint8Array): string => {
  const constants = new Uint32Array([
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
  ])
  const state = new Uint32Array([0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19])
  const padded = new Uint8Array(Math.ceil((bytes.length + 9) / 64) * 64)
  padded.set(bytes); padded[bytes.length] = 0x80
  const view = new DataView(padded.buffer)
  view.setUint32(padded.length - 8, Math.floor(bytes.length / 0x20000000))
  view.setUint32(padded.length - 4, (bytes.length * 8) >>> 0)
  const words = new Uint32Array(64)
  const rotate = (value: number, bits: number) => (value >>> bits) | (value << (32 - bits))
  for (let offset = 0; offset < padded.length; offset += 64) {
    for (let i = 0; i < 16; i++) words[i] = view.getUint32(offset + i * 4)
    for (let i = 16; i < 64; i++) {
      const x = words[i - 15]; const y = words[i - 2]
      const s0 = rotate(x, 7) ^ rotate(x, 18) ^ (x >>> 3)
      const s1 = rotate(y, 17) ^ rotate(y, 19) ^ (y >>> 10)
      words[i] = (words[i - 16] + s0 + words[i - 7] + s1) >>> 0
    }
    let [a,b,c,d,e,f,g,h] = state
    for (let i = 0; i < 64; i++) {
      const s1 = rotate(e, 6) ^ rotate(e, 11) ^ rotate(e, 25)
      const choice = (e & f) ^ (~e & g)
      const t1 = (h + s1 + choice + constants[i] + words[i]) >>> 0
      const s0 = rotate(a, 2) ^ rotate(a, 13) ^ rotate(a, 22)
      const majority = (a & b) ^ (a & c) ^ (b & c)
      const t2 = (s0 + majority) >>> 0
      h=g; g=f; f=e; e=(d+t1)>>>0; d=c; c=b; b=a; a=(t1+t2)>>>0
    }
    const block = [a,b,c,d,e,f,g,h]
    for (let i = 0; i < 8; i++) state[i] = (state[i] + block[i]) >>> 0
  }
  return Array.from(state, word => word.toString(16).padStart(8, '0')).join('')
}

const digest = async (value: string) => {
  const input = new TextEncoder().encode(value)
  if (!globalThis.crypto?.subtle) return sha256Fallback(input)
  try {
    const bytes = await crypto.subtle.digest('SHA-256', input)
    return Array.from(new Uint8Array(bytes), byte => byte.toString(16).padStart(2, '0')).join('')
  } catch { return sha256Fallback(input) }
}

export const collectLoginFingerprint = (): Promise<LoginFingerprint> => {
  if (fingerprintPromise) return fingerprintPromise
  fingerprintPromise = (async (): Promise<LoginFingerprint> => {
    try {
      const canvas = document.createElement('canvas')
      canvas.width = 240; canvas.height = 80
      const ctx = canvas.getContext('2d')
      if (!ctx) return {}
      const gradient = ctx.createLinearGradient(0, 0, 240, 80)
      gradient.addColorStop(0, '#17384d'); gradient.addColorStop(1, '#d29848')
      ctx.fillStyle = gradient; ctx.fillRect(0, 0, 240, 80)
      ctx.font = '19px Georgia'; ctx.fillStyle = '#e8e3d5'
      ctx.fillText('Mirror Aa 中 0123 Ω', 7.5, 28.3)
      ctx.globalCompositeOperation = 'multiply'
      ctx.beginPath(); ctx.arc(121.3, 46.8, 24.4, 0, Math.PI * 2); ctx.fill()
      const image = await digest(canvas.toDataURL())
      const small = document.createElement('canvas'); small.width = 9; small.height = 8
      const smallCtx = small.getContext('2d')
      if (!smallCtx) return {}
      smallCtx.drawImage(canvas, 0, 0, 9, 8)
      const pixels = smallCtx.getImageData(0, 0, 9, 8).data
      let bits = ''
      const grey = (index: number) => pixels[index] * .299 + pixels[index + 1] * .587 + pixels[index + 2] * .114
      for (let y = 0; y < 8; y++) for (let x = 0; x < 8; x++) bits += grey((y * 9 + x) * 4) > grey((y * 9 + x + 1) * 4) ? '1' : '0'
      let shape = ''
      for (let i = 0; i < 64; i += 4) shape += parseInt(bits.slice(i, i + 4), 2).toString(16)
      const metrics = ['serif', 'sans-serif', 'monospace', 'Georgia', 'Arial', 'Times New Roman', 'Courier New', 'system-ui'].map(font => {
        ctx.font = `17px ${font}`
        const metric = ctx.measureText('Aa中Ω0123mmmmWWii')
        return [metric.width, metric.actualBoundingBoxAscent, metric.actualBoundingBoxDescent].join(',')
      }).join('|')
      const node = document.createElement('div')
      node.style.cssText = 'position:fixed;left:-10000px;width:217.3px;font:17px Georgia;letter-spacing:.37px;line-height:1.27;visibility:hidden'
      node.textContent = 'Mirror Aa中Ω 0123 wrap rendering sample'
      document.body.appendChild(node)
      const rect = node.getBoundingClientRect()
      const layout = `${rect.width}|${rect.height}|${getComputedStyle(node).lineHeight}`
      node.remove()
      const gpuCanvas = document.createElement('canvas'); gpuCanvas.width = 32; gpuCanvas.height = 32
      const gl = gpuCanvas.getContext('webgl', { preserveDrawingBuffer: true })
      let gpu = 'webgl:unavailable'
      if (gl) {
        const shader = (kind: number, source: string) => {
          const value = gl.createShader(kind)!
          gl.shaderSource(value, source); gl.compileShader(value)
          return value
        }
        const vertex = shader(gl.VERTEX_SHADER, 'attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}')
        const fragment = shader(gl.FRAGMENT_SHADER, 'precision mediump float;void main(){gl_FragColor=vec4(gl_FragCoord.xy/32.,.37,1.);}')
        const program = gl.createProgram()!; gl.attachShader(program, vertex); gl.attachShader(program, fragment); gl.linkProgram(program); gl.useProgram(program)
        const buffer = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-.93,-.91,.87,-.42,-.31,.97]), gl.STATIC_DRAW)
        const location = gl.getAttribLocation(program, 'p'); gl.enableVertexAttribArray(location); gl.vertexAttribPointer(location, 2, gl.FLOAT, false, 0, 0)
        gl.drawArrays(gl.TRIANGLES, 0, 3)
        const gpuPixels = new Uint8Array(32 * 32 * 4); gl.readPixels(0, 0, 32, 32, gl.RGBA, gl.UNSIGNED_BYTE, gpuPixels)
        gpu = Array.from(gpuPixels).join(',') + '|' + String(gl.getParameter(gl.SHADING_LANGUAGE_VERSION))
        gl.deleteBuffer(buffer); gl.deleteProgram(program); gl.deleteShader(vertex); gl.deleteShader(fragment)
        gl.getExtension('WEBGL_lose_context')?.loseContext()
      }
      return { canvas: image, shape, webgl: await digest(gpu), fonts: await digest(metrics), layout: await digest(layout) }
    } catch { return {} }
  })()
  return fingerprintPromise.then(fp => {
    // Retry after the user enables rendering, without requiring a full page reload.
    if (Object.keys(fp).length !== 5) fingerprintPromise = undefined
    return fp
  })
}

export class LoginCoolingError extends Error {
  constructor(public remainingSeconds: number) { super(`请在 ${remainingSeconds} 秒后重试登录`) }
}

export class LoginVerificationError extends Error {}

export const getLoginCooldown = async (): Promise<number> => {
  const response = await fetch('/0x/user/login-status', {
    method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fingerprint: await collectLoginFingerprint() })
  })
  const data = await response.json()
  if (!response.ok) {
    const message = typeof data.message === 'string' ? data.message : '暂时无法读取登录状态，请稍后重试'
    if (data.code === 'fingerprint_required') throw new LoginVerificationError(message)
    throw new Error(message)
  }
  return Math.max(0, Math.min(120, Number(data.remaining_seconds) || 0))
}
