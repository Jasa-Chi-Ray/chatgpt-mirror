#version 300 es
precision highp float;

const int WAVE_POINTS = 80;

uniform sampler2D uBefore;
uniform sampler2D uAfter;
uniform vec2 uViewport;
uniform vec2 uBuffer;
uniform vec2 uWave[WAVE_POINTS];
uniform float uTime;
uniform bool uToLight;
out vec4 outputColor;

vec2 waterline(float x) {
  float sampleIndex = clamp(x / uViewport.x, 0.0, 1.0) * float(WAVE_POINTS - 1);
  int left = min(int(sampleIndex), WAVE_POINTS - 2);
  return mix(uWave[left], uWave[left + 1], sampleIndex - float(left));
}

vec2 texturePoint(vec2 point) {
  return clamp(point / uViewport, 0.0, 1.0);
}

vec3 scene(vec2 point) {
  vec2 uv = texturePoint(point);
  float below = smoothstep(-3.5, 3.5, point.y - waterline(point.x).x);
  return mix(texture(uAfter, uv).rgb, texture(uBefore, uv).rgb, below);
}

vec3 waveRefraction(vec2 point, vec2 bend) {
  vec3 first = scene(point + bend * 1.033);
  vec3 center = scene(point + bend);
  vec3 last = scene(point + bend * 0.967);
  return vec3(first.r, center.g, last.b);
}

float reflectedLight(vec3 normal, vec3 direction, float gloss) {
  return pow(max(dot(normal, normalize(direction + vec3(0.0, 0.0, 1.0))), 0.0), gloss);
}

vec4 waveGlass(vec2 point) {
  vec2 surface = waterline(point.x);
  float delta = point.y - surface.x;
  if (delta < -surface.y * 1.6 || delta > surface.y * 1.6) return vec4(0.0);

  float slope = (waterline(point.x + 4.0).x - waterline(point.x - 4.0).x) * 0.125;
  vec2 normal = normalize(vec2(-slope, 1.0));
  float side = uToLight ? 1.0 : -1.0;
  float distance = delta * normal.y * side;
  float body = smoothstep(-6.0, 3.0, distance) * (1.0 - smoothstep(0.20, 1.0, distance / surface.y));
  float lip = exp(-pow((distance - 1.0) / 6.0, 2.0));
  float silhouette = max(body, lip * 0.90);
  if (silhouette < 0.008) return vec4(0.0);

  float along = point.x / uViewport.x;
  float swell = sin(along * 24.0 - uTime * 10.0) * 0.5 + 0.5;
  float ripple = sin(along * 47.0 + uTime * 16.0 + distance * 0.18);
  float rollingRidge = exp(-pow((distance - surface.y * (0.32 + 0.15 * swell)) / 9.0, 2.0));
  float lens = (22.0 * lip - 11.0 * rollingRidge + 5.0 * ripple * body) * (0.74 + swell * 0.54);
  vec2 tangent = vec2(normal.y, -normal.x);
  vec2 bend = normal * lens * side + tangent * (ripple * 3.8 + slope * 7.0) * silhouette;
  vec3 refracted = waveRefraction(point, bend);

  vec3 opticNormal = normalize(vec3(normal * side * (0.18 + 0.86 * lip + 0.27 * rollingRidge),
    0.86 - 0.64 * lip));
  float fresnel = 0.04 + 0.60 * pow(1.0 - opticNormal.z, 5.0);
  vec3 reflected = scene(point - normal * side * (12.0 + 9.0 * swell) + tangent * ripple * 7.0);
  vec3 transmitted = mix(refracted, reflected, fresnel);
  float specular = 0.21 * reflectedLight(opticNormal, vec3(-0.5, -0.7, 0.8), 31.0)
                 + 0.16 * reflectedLight(opticNormal, vec3(0.3, 0.8, 0.72), 61.0);
  float glint = exp(-pow((distance + 0.4) / 1.6, 2.0)) * (0.20 + 0.42 * pow(swell, 2.4));
  float secondary = rollingRidge * pow(max(0.0, ripple), 3.0) * 0.15;
  float shadow = exp(-pow((distance - 8.0) / 5.0, 2.0)) * (0.075 + 0.045 * swell);

  vec3 glass = transmitted * vec3(0.95, 1.00, 0.97) * (1.0 - shadow);
  glass += (specular + glint + secondary) * vec3(0.92, 1.0, 0.97) * (1.0 - glass * 0.48);
  return vec4(clamp(glass, 0.0, 1.0), clamp(silhouette, 0.0, 1.0));
}

void main() {
  vec2 normalized = vec2(gl_FragCoord.x / uBuffer.x, 1.0 - gl_FragCoord.y / uBuffer.y);
  outputColor = waveGlass(normalized * uViewport);
}
