/**
 * GhostFibers - Ambient WebGL2 Cyberpunk Background for Verity
 * Adapted from React Bits (https://reactbits.dev/backgrounds/ghost-fibers)
 * Powered by OGL (Lightweight WebGL2 framework)
 */

let OGL;
try {
  OGL = await import('/static/ogl.mjs');
} catch (e1) {
  try {
    OGL = await import('./ogl.mjs');
  } catch (e2) {
    OGL = await import('https://esm.sh/ogl@1.0.11');
  }
}

const { Renderer, Program, Mesh, Triangle } = OGL;

const hexToRgb = hex => {
  const value = hex.trim().replace(/^#/, '');
  const normalized = value.length === 3 ? value.replace(/./g, channel => channel + channel) : value;
  const match = /^([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(normalized);
  if (!match) return [1, 1, 1];
  return [parseInt(match[1], 16) / 255, parseInt(match[2], 16) / 255, parseInt(match[3], 16) / 255];
};

const vertex = `#version 300 es
in vec2 position;

void main() {
  gl_Position = vec4(position, 0.0, 1.0);
}
`;

const fragment = `#version 300 es
precision highp float;

uniform vec2 uResolution;
uniform float uTime;
uniform float uSpeed;
uniform float uScale;
uniform float uRotation;
uniform float uLayers;
uniform float uWaveAmplitude;
uniform float uWaveFrequency;
uniform float uWaveSpeed;
uniform float uLayerSpeed;
uniform float uTwist;
uniform float uTwistFrequency;
uniform float uTwistSpeed;
uniform float uLineFrequency;
uniform float uLineSpacing;
uniform float uLineSharpness;
uniform float uGlowFalloff;
uniform float uGlowIntensity;
uniform float uBrightness;
uniform float uBlueBoost;
uniform float uVignette;
uniform float uGrain;
uniform float uRotationSpeed;
uniform float uLightMode;
uniform vec3 uLineColor;
uniform vec3 uGlowColor;

out vec4 fragColor;

#define MAX_LAYERS 10

mat2 rotate2d(float angle) {
  float sine = sin(angle);
  float cosine = cos(angle);
  return mat2(cosine, -sine, sine, cosine);
}

float grainHash(vec2 point) {
  point = floor(point);
  float hash = 52.9829189 * fract(dot(point, vec2(0.065, 0.005)));
  return fract(hash);
}

float layeredGrain(vec2 fragmentPixel) {
  vec2 point = mod(fragmentPixel + vec2(uTime * 30.0, -uTime * 21.0), 1024.0);
  vec2 rotated = mat2(0.8, -0.5, 0.5, 0.8) * point;
  float grain = 0.0;
  grain += 0.40 * grainHash(rotated);
  grain += 0.25 * grainHash(rotated * 2.0 + 17.0);
  grain += 0.20 * grainHash(rotated * 4.0 + 47.0);
  grain += 0.10 * grainHash(rotated * 8.0 + 113.0);
  grain += 0.05 * grainHash(rotated * 16.0 + 191.0);
  return grain;
}

void main() {
  vec2 resolution = max(uResolution, vec2(1.0));
  vec2 uv = (2.0 * gl_FragCoord.xy - resolution) / resolution.y;
  float time = uTime * uSpeed;
  vec3 backdrop = mix(vec3(0.04, 0.055, 0.09), vec3(1.0), step(0.5, uLightMode));
  vec3 centerTone = max(uLineColor * 0.85567 - uGlowColor * 0.06186, vec3(0.0));
  vec3 cloudTone = uLineColor * 0.19588 + uGlowColor * 0.2268;
  vec2 p = uv;
  p /= max(uScale, 0.05);
  p = rotate2d(radians(uRotation) + time * uRotationSpeed) * p;
  vec3 color = vec3(0.0);
  float fiberField = 0.0;

  for (int index = 0; index < MAX_LAYERS; index++) {
    float fi = float(index) + 1.0;
    if (fi > uLayers) break;

    p += uWaveAmplitude * sin(p.yx * fi * uWaveFrequency + time * (uWaveSpeed + fi * uLayerSpeed));

    float radius = length(p);
    float polarAngle = atan(p.y, p.x);
    polarAngle += sin(radius * uTwistFrequency - time * uTwistSpeed + fi) * uTwist;
    p = vec2(cos(polarAngle), sin(polarAngle)) * radius;

    float lines = abs(sin(p.x * (uLineFrequency + fi * uLineSpacing) + sin(p.y * 3.0 + time)));
    lines = pow(max(0.0, 1.0 - lines), uLineSharpness);
    fiberField += lines / fi;
    color += uLineColor * lines / fi;

    float glow = exp(-uGlowFalloff * abs(sin(p.x * 3.0 + time + fi)));
    color += uGlowColor * glow * uGlowIntensity / (fi * 2.0);
  }

  float center = exp(-2.2 * dot(uv, uv));
  color += centerTone * center;

  float cloud = exp(-1.5 * length(uv + vec2(sin(time * 0.3) * 0.25, cos(time * 0.25) * 0.18)));
  color += cloudTone * cloud;

  float vignette = 1.0 - smoothstep(0.35, 1.45, length(uv));
  color *= mix(1.0 - uVignette, 1.0, vignette);
  color = 1.0 - exp(-color * uBrightness);
  color.b *= uBlueBoost;

  vec3 outputColor;
  if (uLightMode > 0.5) {
    float edgeFade = mix(1.0 - uVignette, 1.0, vignette);
    float fibers = pow(smoothstep(0.12, 1.05, fiberField) * edgeFade, 1.5);
    float atmosphere = (center * 0.025 + cloud * 0.015) * edgeFade;
    vec3 fiberInk = mix(backdrop, uLineColor, 0.52);
    vec3 airColor = mix(backdrop, uGlowColor, 0.16);

    outputColor = mix(backdrop, airColor, atmosphere);
    outputColor = mix(outputColor, fiberInk, fibers * 0.3);
  } else {
    outputColor = backdrop + color;
  }

  float noise = (layeredGrain(gl_FragCoord.xy) - 0.5) * uGrain;
  outputColor = clamp(outputColor + noise, 0.0, 1.0);
  fragColor = vec4(outputColor, 1.0);
}
`;

export function initGhostFibers(container, customOptions = {}) {
  if (!container) return null;

  const options = {
    lineColor: '#03010d',
    glowColor: '#3437A0',
    speed: 0.2,
    scale: 2,
    rotation: 0,
    rotationSpeed: -0.06,
    layers: 4,
    waveAmplitude: 0.015,
    waveFrequency: 3,
    waveSpeed: 0.15,
    layerSpeed: 0.08,
    twist: 0.1,
    twistFrequency: 5,
    twistSpeed: 1.2,
    lineFrequency: 5,
    lineSpacing: 2,
    lineSharpness: 16,
    glowFalloff: 10,
    glowIntensity: 1.6,
    brightness: 2,
    blueBoost: 1.25,
    vignette: 0.8,
    grain: 0.05,
    lightMode: false,
    dpr: Math.min(window.devicePixelRatio || 1, 1.5),
    fps: 60,
    paused: false,
    ...customOptions
  };

  const renderer = new Renderer({
    webgl: 2,
    alpha: false,
    antialias: false,
    dpr: Math.min(Math.max(options.dpr, 0.5), 2)
  });

  const gl = renderer.gl;
  const canvas = gl.canvas;
  canvas.style.width = '100%';
  canvas.style.height = '100%';
  canvas.style.display = 'block';
  canvas.setAttribute('aria-hidden', 'true');
  container.appendChild(canvas);

  const geometry = new Triangle(gl);
  const program = new Program(gl, {
    vertex,
    fragment,
    uniforms: {
      uResolution: { value: new Float32Array([1, 1]) },
      uTime: { value: 0 },
      uSpeed: { value: options.speed },
      uScale: { value: options.scale },
      uRotation: { value: options.rotation },
      uRotationSpeed: { value: options.rotationSpeed },
      uLayers: { value: options.layers },
      uWaveAmplitude: { value: options.waveAmplitude },
      uWaveFrequency: { value: options.waveFrequency },
      uWaveSpeed: { value: options.waveSpeed },
      uLayerSpeed: { value: options.layerSpeed },
      uTwist: { value: options.twist },
      uTwistFrequency: { value: options.twistFrequency },
      uTwistSpeed: { value: options.twistSpeed },
      uLineFrequency: { value: options.lineFrequency },
      uLineSpacing: { value: options.lineSpacing },
      uLineSharpness: { value: options.lineSharpness },
      uGlowFalloff: { value: options.glowFalloff },
      uGlowIntensity: { value: options.glowIntensity },
      uBrightness: { value: options.brightness },
      uBlueBoost: { value: options.blueBoost },
      uVignette: { value: options.vignette },
      uGrain: { value: options.grain },
      uLightMode: { value: options.lightMode ? 1 : 0 },
      uLineColor: { value: new Float32Array(hexToRgb(options.lineColor)) },
      uGlowColor: { value: new Float32Array(hexToRgb(options.glowColor)) }
    }
  });

  const mesh = new Mesh(gl, { geometry, program });

  let frameId = 0;
  let elapsed = 0;
  let previousTime = performance.now();
  let lastRenderTime = 0;
  let frameRate = options.fps;
  let isPaused = options.paused;
  let isVisible = true;
  let isPageVisible = !document.hidden;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  const render = () => renderer.render({ scene: mesh });
  const stop = () => {
    if (frameId !== 0) cancelAnimationFrame(frameId);
    frameId = 0;
  };
  const canAnimate = () => isVisible && isPageVisible && !isPaused && !reducedMotion.matches;

  const loop = now => {
    frameId = 0;
    if (!canAnimate()) return;

    const delta = Math.min((now - previousTime) / 1000, 0.1);
    previousTime = now;
    elapsed += delta;

    if (now - lastRenderTime >= 1000 / frameRate - 0.5) {
      program.uniforms.uTime.value = elapsed;
      render();
      lastRenderTime = now;
    }

    frameId = requestAnimationFrame(loop);
  };

  const start = () => {
    if (!canAnimate() || frameId !== 0) return;
    previousTime = performance.now();
    frameId = requestAnimationFrame(loop);
  };

  const setSize = () => {
    const rect = container.getBoundingClientRect();
    const w = Math.max(1, Math.floor(rect.width || window.innerWidth));
    const h = Math.max(1, Math.floor(rect.height || window.innerHeight));
    renderer.setSize(w, h);
    program.uniforms.uResolution.value[0] = gl.drawingBufferWidth;
    program.uniforms.uResolution.value[1] = gl.drawingBufferHeight;
    render();
  };

  const handleVisibility = () => {
    isPageVisible = !document.hidden;
    if (canAnimate()) start();
    else stop();
  };

  const handleReducedMotion = () => {
    if (canAnimate()) start();
    else {
      stop();
      render();
    }
  };

  const resizeObserver = new ResizeObserver(setSize);
  resizeObserver.observe(container);
  window.addEventListener('resize', setSize);

  const intersectionObserver = new IntersectionObserver(
    ([entry]) => {
      isVisible = entry.isIntersecting;
      if (canAnimate()) start();
      else stop();
    },
    { threshold: 0 }
  );
  intersectionObserver.observe(container);

  document.addEventListener('visibilitychange', handleVisibility);
  reducedMotion.addEventListener('change', handleReducedMotion);

  setSize();
  start();

  return {
    destroy() {
      stop();
      resizeObserver.disconnect();
      intersectionObserver.disconnect();
      window.removeEventListener('resize', setSize);
      document.removeEventListener('visibilitychange', handleVisibility);
      reducedMotion.removeEventListener('change', handleReducedMotion);
      if (canvas.parentNode === container) container.removeChild(canvas);
      gl.getExtension('WEBGL_lose_context')?.loseContext();
    }
  };
}

// Auto-inject GhostFibers background across screens if document is present
function autoInitBackground() {
  if (typeof document === 'undefined') return;

  // Check if background element already exists
  let bg = document.getElementById('ghost-fibers-bg');
  if (!bg) {
    bg = document.createElement('div');
    bg.id = 'ghost-fibers-bg';
    bg.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      z-index: -10;
      pointer-events: none;
      overflow: hidden;
      opacity: 0.95;
    `;
    document.body.prepend(bg);
  }

  // Ensure body, html, main, and hero sections let the background shine through
  const style = document.createElement('style');
  style.id = 'ghost-fibers-style';
  style.textContent = `
    html, body {
      background-color: transparent !important;
      background: transparent !important;
    }
    body {
      min-height: 100vh;
      position: relative;
    }
    main, 
    main.bg-background,
    body.bg-background,
    section.bg-surface-container-lowest,
    section.bg-background,
    .page-main-viewport {
      background-color: transparent !important;
      background: transparent !important;
    }
    #ghost-fibers-bg {
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      z-index: -10;
      pointer-events: none;
      overflow: hidden;
      opacity: 1;
    }
  `;
  document.head.appendChild(style);

  // Initialize shader with rich luminous cyber-glow parameters
  initGhostFibers(bg, {
    lineColor: '#0a0d2c',
    glowColor: '#3d44c9',
    speed: 0.22,
    scale: 2,
    rotation: 0,
    rotationSpeed: -0.06,
    layers: 5,
    waveAmplitude: 0.02,
    waveFrequency: 3,
    waveSpeed: 0.18,
    layerSpeed: 0.09,
    twist: 0.12,
    twistFrequency: 5,
    twistSpeed: 1.2,
    lineFrequency: 5,
    lineSpacing: 2,
    lineSharpness: 14,
    glowFalloff: 7.5,
    glowIntensity: 2.4,
    brightness: 2.6,
    blueBoost: 1.4,
    vignette: 0.7,
    grain: 0.04,
    dpr: Math.min(window.devicePixelRatio || 1, 1.5)
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', autoInitBackground);
} else {
  autoInitBackground();
}
