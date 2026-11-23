import fragmentSource from './liquid-glass.frag?raw'

export const wavePointCount = 80

const vertexSource = `#version 300 es
void main() {
  vec2 point = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
  gl_Position = vec4(point * 2.0 - 1.0, 0.0, 1.0);
}
`

type Viewport = { width: number; height: number }

const compile = (gl: WebGL2RenderingContext, type: number, source: string) => {
  const shader = gl.createShader(type)
  if (!shader) throw new Error('Unable to allocate a glass shader.')
  gl.shaderSource(shader, source)
  gl.compileShader(shader)
  if (gl.getShaderParameter(shader, gl.COMPILE_STATUS)) return shader

  const details = gl.getShaderInfoLog(shader)
  gl.deleteShader(shader)
  throw new Error(details ?? 'Unable to compile the glass shader.')
}

export const createGlassRenderer = (canvas: HTMLCanvasElement, viewport: Viewport) => {
  const scale = Math.min(devicePixelRatio, 1.5, Math.sqrt(1_650_000 / (viewport.width * viewport.height)))
  canvas.width = Math.max(1, Math.round(viewport.width * scale))
  canvas.height = Math.max(1, Math.round(viewport.height * scale))
  const gl = canvas.getContext('webgl2', { alpha: true, premultipliedAlpha: false, antialias: false, depth: false })
  if (!gl) return null
  const program = gl.createProgram()
  if (!program) return null
  const textures: WebGLTexture[] = []
  const clear = () => {
    gl.clearColor(0, 0, 0, 0)
    gl.clear(gl.COLOR_BUFFER_BIT)
  }
  const dispose = () => {
    clear()
    for (const texture of textures) gl.deleteTexture(texture)
    gl.deleteProgram(program)
  }
  try {
    const vertex = compile(gl, gl.VERTEX_SHADER, vertexSource)
    try {
      const fragment = compile(gl, gl.FRAGMENT_SHADER, fragmentSource)
      gl.attachShader(program, vertex)
      gl.attachShader(program, fragment)
      gl.linkProgram(program)
      gl.deleteShader(fragment)
    } finally {
      gl.deleteShader(vertex)
    }
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(gl.getProgramInfoLog(program) ?? 'Unable to link the glass shader.')
    }

    const uniform = (name: string) => gl.getUniformLocation(program, name)
    const waveUniform = uniform('uWave[0]')
    const timeUniform = uniform('uTime')
    const directionUniform = uniform('uToLight')
    gl.viewport(0, 0, canvas.width, canvas.height)
    gl.useProgram(program)
    gl.uniform2f(uniform('uViewport'), viewport.width, viewport.height)
    gl.uniform2f(uniform('uBuffer'), canvas.width, canvas.height)
    gl.uniform1i(uniform('uBefore'), 0)
    gl.uniform1i(uniform('uAfter'), 1)
    clear()

    const setScenes = (before: HTMLCanvasElement, after: HTMLCanvasElement) => {
      for (const [unit, surface] of [before, after].entries()) {
        const texture = gl.createTexture()
        if (!texture) throw new Error('Unable to allocate a glass texture.')
        textures.push(texture)
        gl.activeTexture(gl.TEXTURE0 + unit)
        gl.bindTexture(gl.TEXTURE_2D, texture)
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, surface)
      }
      if (gl.getError() !== gl.NO_ERROR) throw new Error('Unable to upload the glass textures.')
    }

    const draw = (wave: Float32Array, time: number, toLight: boolean) => {
      gl.uniform2fv(waveUniform, wave)
      gl.uniform1f(timeUniform, time)
      gl.uniform1i(directionUniform, Number(toLight))
      gl.drawArrays(gl.TRIANGLES, 0, 3)
    }

    return { setScenes, draw, dispose, lost: () => gl.isContextLost() }
  } catch (error) {
    dispose()
    throw error
  }
}
