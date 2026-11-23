const turn = Math.PI * 2

type Palette = { ink: string; surface: string }

const hull = new Path2D(
  'M -16 -4.3 C -6 -6.8 5 -7.4 13 -4.8 Q 19 -2.9 23 0 ' +
  'Q 19 2.9 13 4.8 C 5 7.4 -6 6.8 -16 4.3 Q -18 0 -16 -4.3 Z'
)
const noseSeam = new Path2D('M 12 -5 Q 14 0 12 5')
const nozzle = new Path2D('M -16 -3.4 L -20 -3.0 L -20 3.0 L -16 3.4')
const hullHatching = new Path2D(
  'M -14 4.2 l 2.4 -2.5 M -10.5 5 l 2.8 -2.9 M -6.5 5.7 l 3.1 -3.1 ' +
  'M -2.1 6 l 3 -2.8 M 3 6.2 l 2.7 -2.5 M 8 5.9 l 2.3 -2.2'
)
const hullPencilEdge = new Path2D('M -15 5.3 Q -4 8.2 8 7.1 M 15 4.9 Q 18.5 3.4 20.6 2')
const cloud = new Path2D(
  'M 12 23 C 5 23 3 20 4 17.5 C 4.5 14.5 8 13 12 13.5 ' +
  'C 13 8 20 5.5 26 8.2 C 29 2 39 1 44 7 ' +
  'C 49 5 56 8.3 57 13 C 64 11.5 70 14.5 70 18.5 Q 70 23 63 23 Z'
)
const cloudPencilEdge = new Path2D(
  'M 10 19.5 Q 15 22 22 20.8 M 29 21 Q 35 22.5 41 21.1 ' +
  'M 48 20.5 Q 52 21.8 58 21.1 M 59 17.5 Q 63 16.9 66 18.4'
)

const drawRocket = (
  context: CanvasRenderingContext2D,
  palette: Palette,
  x: number,
  y: number,
  heading: number,
  roll: number
) => {
  context.save()
  context.translate(x, y)
  context.rotate(heading)
  context.strokeStyle = palette.ink
  context.fillStyle = palette.surface

  context.globalAlpha = 0.55
  context.lineWidth = 1
  context.beginPath()
  context.moveTo(-24, 0)
  context.quadraticCurveTo(-34, -1.4, -46 - Math.sin(roll * 2) * 4, 0)
  context.moveTo(-25, -3.2)
  context.lineTo(-32, -3.2)
  context.moveTo(-26, 3.2)
  context.lineTo(-35, 3.2)
  context.stroke()
  context.globalAlpha = 1

  const fin = (angle: number, rear: boolean) => {
    const radial = Math.sin(angle)
    context.globalAlpha = rear ? 0.55 : 1
    context.beginPath()
    context.moveTo(-15.4, radial * 3.6)
    context.lineTo(-20, radial * 12.1)
    context.quadraticCurveTo(-13.6, radial * 10.2, -6, radial * 5.2)
    context.stroke()
    if (!rear && Math.abs(radial) > .35) {
      context.globalAlpha = .42
      context.lineWidth = .7
      context.beginPath()
      context.moveTo(-18.7, radial * 10.3)
      context.lineTo(-14.5, radial * 8.8)
      context.moveTo(-17.4, radial * 8.5)
      context.lineTo(-12.3, radial * 7.6)
      context.stroke()
      context.lineWidth = 1.35
    }
    context.globalAlpha = 1
  }

  const fins = [roll, roll + turn / 3, roll + turn * 2 / 3]
  context.lineWidth = 1.35
  for (const angle of fins) {
    if (Math.cos(angle) <= 0) fin(angle, true)
  }

  context.lineWidth = 1.4
  context.fill(hull)
  context.stroke(hull)
  context.stroke(nozzle)

  context.save()
  context.clip(hull)
  context.translate(0, Math.sin(roll) * 0.82)
  context.lineWidth = .72
  context.globalAlpha = .45
  context.stroke(hullHatching)
  context.restore()

  context.lineWidth = .68
  context.globalAlpha = .38
  context.stroke(hullPencilEdge)

  context.lineWidth = 1
  context.globalAlpha = 0.68
  context.stroke(noseSeam)
  context.globalAlpha = 1

  const facing = Math.cos(roll)
  if (facing > 0.04) {
    const windowY = Math.sin(roll) * 4.8
    context.lineWidth = 1.25
    context.beginPath()
    context.ellipse(3.3, windowY, 3.45, Math.max(0.18, 2.9 * facing), 0, 0, turn)
    context.stroke()
  }

  context.lineWidth = 1.35
  for (const angle of fins) {
    if (Math.cos(angle) > 0) fin(angle, false)
  }
  context.restore()
}

const distantClouds = [
  { position: 0.18, level: 0.41, span: 0.78, speed: 19, opacity: 0.33 },
  { position: 0.83, level: 0.23, span: 0.92, speed: 27, opacity: 0.39 }
]
const nearbyClouds = [
  { position: 0.34, level: 0.48, span: 0.94, speed: 34, opacity: 0.73 },
  { position: 0.94, level: 0.52, span: 0.86, speed: 40, opacity: 0.64 }
]
type Cloud = typeof distantClouds[number]

export const drawFlight = (
  context: CanvasRenderingContext2D,
  palette: Palette,
  width: number,
  height: number,
  time: number,
  progress: number
) => {
  context.clearRect(0, 0, width, height)
  context.lineCap = 'round'
  context.lineJoin = 'round'

  const drawCloud = (bank: Cloud, foreground: boolean) => {
    const span = width + 120
    const x = ((width * bank.position - time * bank.speed + 95) % span + span) % span - 95
    context.save()
    context.translate(x, bank.level * height)
    context.scale(bank.span, bank.span)
    if (foreground) {
      context.fillStyle = palette.surface
      context.fill(cloud)
    }
    context.strokeStyle = palette.ink
    context.globalAlpha = bank.opacity
    context.lineWidth = 1.1
    context.stroke(cloud)
    context.globalAlpha = bank.opacity * .58
    context.lineWidth = .72
    context.stroke(cloudPencilEdge)
    context.restore()
  }
  for (const bank of distantClouds) drawCloud(bank, false)

  const rocketX = -27 + progress * (width + 79)
  const rocketY = height * (0.62 - progress * 0.31) + Math.sin(progress * turn) * 1.5
  drawRocket(context, palette, rocketX, rocketY, -0.15 + Math.sin(progress * turn) * 0.075, time * turn * 1.16)

  for (const bank of nearbyClouds) drawCloud(bank, true)

  const trackLength = Math.max(0, width - 28)
  context.fillStyle = palette.ink
  context.globalAlpha = 0.19
  context.fillRect(14, height - 3, trackLength, 1)
  context.globalAlpha = 0.62
  context.fillRect(14, height - 3, Math.min(trackLength, Math.max(0, rocketX - 14)), 1)
  context.globalAlpha = 1
}
