/**
 * LightRays - Dynamic WebGL Volumetric Light Rays Background for Verity
 * Adapted from React Bits (https://reactbits.dev/backgrounds/light-rays)
 * Powered by OGL (Lightweight WebGL framework)
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

const { Renderer, Program, Triangle, Mesh } = OGL;

const DEFAULT_COLOR = '#afb3dd';

const hexToRgb = hex => {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return m ? [parseInt(m[1], 16) / 255, parseInt(m[2], 16) / 255, parseInt(m[3], 16) / 255] : [0.686, 0.702, 0.867];
};

const getAnchorAndDir = (origin, w, h) => {
  const outside = 0.2;
  switch (origin) {
    case 'top-left':
      return { anchor: [0, -outside * h], dir: [0, 1] };
    case 'top-right':
      return { anchor: [w, -outside * h], dir: [0, 1] };
    case 'left':
      return { anchor: [-outside * w, 0.5 * h], dir: [1, 0] };
    case 'right':
      return { anchor: [(1 + outside) * w, 0.5 * h], dir: [-1, 0] };
    case 'bottom-left':
      return { anchor: [0, (1 + outside) * h], dir: [0, -1] };
    case 'bottom-center':
      return { anchor: [0.5 * w, (1 + outside) * h], dir: [0, -1] };
    case 'bottom-right':
      return { anchor: [w, (1 + outside) * h], dir: [0, -1] };
    default: // "top-center"
      return { anchor: [0.5 * w, -outside * h], dir: [0, 1] };
  }
};

const vert = `
attribute vec2 position;
varying vec2 vUv;
void main() {
  vUv = position * 0.5 + 0.5;
  gl_Position = vec4(position, 0.0, 1.0);
}
`;

const frag = `precision highp float;

uniform float iTime;
uniform vec2  iResolution;

uniform vec2  rayPos;
uniform vec2  rayDir;
uniform vec3  raysColor;
uniform float raysSpeed;
uniform float lightSpread;
uniform float rayLength;
uniform float pulsating;
uniform float fadeDistance;
uniform float saturation;
uniform vec2  mousePos;
uniform float mouseInfluence;
uniform float noiseAmount;
uniform float distortion;
uniform float lightMode;

varying vec2 vUv;

float noise(vec2 st) {
  return fract(sin(dot(st.xy, vec2(12.9898,78.233))) * 43758.5453123);
}

float rayStrength(vec2 raySource, vec2 rayRefDirection, vec2 coord,
                  float seedA, float seedB, float speed) {
  vec2 sourceToCoord = coord - raySource;
  vec2 dirNorm = normalize(sourceToCoord);
  float cosAngle = dot(dirNorm, rayRefDirection);

  float distortedAngle = cosAngle + distortion * sin(iTime * 2.0 + length(sourceToCoord) * 0.01) * 0.2;
  
  float spreadFactor = pow(max(distortedAngle, 0.0), 1.0 / max(lightSpread, 0.001));

  float distance = length(sourceToCoord);
  float maxDistance = iResolution.x * rayLength;
  float lengthFalloff = clamp((maxDistance - distance) / maxDistance, 0.0, 1.0);
  
  float fadeFalloff = clamp((iResolution.x * fadeDistance - distance) / (iResolution.x * fadeDistance), 0.5, 1.0);
  float pulse = pulsating > 0.5 ? (0.8 + 0.2 * sin(iTime * speed * 3.0)) : 1.0;

  float baseStrength = clamp(
    (0.45 + 0.15 * sin(distortedAngle * seedA + iTime * speed)) +
    (0.3 + 0.2 * cos(-distortedAngle * seedB + iTime * speed)),
    0.0, 1.0
  );

  return baseStrength * lengthFalloff * fadeFalloff * spreadFactor * pulse;
}

void mainImage(out vec4 fragColor, in vec2 fragCoord) {
  vec2 coord = vec2(fragCoord.x, iResolution.y - fragCoord.y);
  
  vec2 finalRayDir = rayDir;
  if (mouseInfluence > 0.0) {
    vec2 mouseScreenPos = mousePos * iResolution.xy;
    vec2 mouseDirection = normalize(mouseScreenPos - rayPos);
    finalRayDir = normalize(mix(rayDir, mouseDirection, mouseInfluence));
  }

  vec4 rays1 = vec4(1.0) *
               rayStrength(rayPos, finalRayDir, coord, 36.2214, 21.11349,
                           1.5 * raysSpeed);
  vec4 rays2 = vec4(1.0) *
               rayStrength(rayPos, finalRayDir, coord, 22.3991, 18.0234,
                           1.1 * raysSpeed);

  fragColor = rays1 * 0.5 + rays2 * 0.4;

  if (noiseAmount > 0.0) {
    float n = noise(coord * 0.01 + iTime * 0.1);
    fragColor.rgb *= (1.0 - noiseAmount + noiseAmount * n);
  }

  float brightness = 1.0 - (coord.y / iResolution.y);
  fragColor.x *= 0.1 + brightness * 0.8;
  fragColor.y *= 0.3 + brightness * 0.6;
  fragColor.z *= 0.5 + brightness * 0.5;

  if (saturation != 1.0) {
    float gray = dot(fragColor.rgb, vec3(0.299, 0.587, 0.114));
    fragColor.rgb = mix(vec3(gray), fragColor.rgb, saturation);
  }

  fragColor.rgb *= raysColor;

  if (lightMode > 0.5) {
    vec3 mapped = vec3(1.0) - exp(-max(fragColor.rgb, vec3(0.0)) * 1.35);
    float energy = clamp(max(mapped.r, max(mapped.g, mapped.b)), 0.0, 1.0);
    vec3 hue = mapped / max(energy, 0.0001);
    vec3 ink = mix(hue * 0.25, hue * 0.72, energy);
    fragColor = vec4(mix(vec3(1.0), ink, energy), 1.0);
  }
}

void main() {
  vec4 color;
  mainImage(color, gl_FragCoord.xy);
  gl_FragColor  = color;
}
`;

export function initLightRays(container, customOptions = {}) {
  if (!container) return null;

  const options = {
    raysOrigin: 'top-center',
    raysColor: '#afb3dd',
    raysSpeed: 1.5,
    lightSpread: 0.8,
    rayLength: 1.2,
    pulsating: false,
    fadeDistance: 1.0,
    saturation: 1.0,
    followMouse: true,
    mouseInfluence: 0.1,
    noiseAmount: 0.1,
    distortion: 0.05,
    lightMode: false,
    ...customOptions
  };

  const renderer = new Renderer({
    dpr: Math.min(window.devicePixelRatio || 1, 2),
    alpha: true
  });

  const gl = renderer.gl;
  gl.canvas.style.width = '100%';
  gl.canvas.style.height = '100%';

  while (container.firstChild) {
    container.removeChild(container.firstChild);
  }
  container.appendChild(gl.canvas);

  const uniforms = {
    iTime: { value: 0 },
    iResolution: { value: [1, 1] },
    rayPos: { value: [0, 0] },
    rayDir: { value: [0, 1] },
    raysColor: { value: hexToRgb(options.raysColor) },
    raysSpeed: { value: options.raysSpeed },
    lightSpread: { value: options.lightSpread },
    rayLength: { value: options.rayLength },
    pulsating: { value: options.pulsating ? 1.0 : 0.0 },
    fadeDistance: { value: options.fadeDistance },
    saturation: { value: options.saturation },
    mousePos: { value: [0.5, 0.5] },
    mouseInfluence: { value: options.mouseInfluence },
    noiseAmount: { value: options.noiseAmount },
    distortion: { value: options.distortion },
    lightMode: { value: options.lightMode ? 1.0 : 0.0 }
  };

  const geometry = new Triangle(gl);
  const program = new Program(gl, {
    vertex: vert,
    fragment: frag,
    uniforms
  });
  const mesh = new Mesh(gl, { geometry, program });

  const mouse = { x: 0.5, y: 0.5 };
  const smoothMouse = { x: 0.5, y: 0.5 };
  let animationId = null;
  let isRunning = false;

  const updatePlacement = () => {
    if (!container || !renderer) return;

    renderer.dpr = Math.min(window.devicePixelRatio || 1, 2);
    const wCSS = container.clientWidth || window.innerWidth;
    const hCSS = container.clientHeight || window.innerHeight;
    renderer.setSize(wCSS, hCSS);

    const dpr = renderer.dpr;
    const w = wCSS * dpr;
    const h = hCSS * dpr;

    uniforms.iResolution.value = [w, h];
    const { anchor, dir } = getAnchorAndDir(options.raysOrigin, w, h);
    uniforms.rayPos.value = anchor;
    uniforms.rayDir.value = dir;
  };

  const loop = t => {
    if (!isRunning) return;

    uniforms.iTime.value = t * 0.001;

    if (options.followMouse && options.mouseInfluence > 0.0) {
      const smoothing = 0.92;
      smoothMouse.x = smoothMouse.x * smoothing + mouse.x * (1 - smoothing);
      smoothMouse.y = smoothMouse.y * smoothing + mouse.y * (1 - smoothing);
      uniforms.mousePos.value = [smoothMouse.x, smoothMouse.y];
    }

    try {
      renderer.render({ scene: mesh });
      animationId = requestAnimationFrame(loop);
    } catch (error) {
      console.warn('LightRays render error:', error);
    }
  };

  const handleMouseMove = e => {
    const rect = container.getBoundingClientRect();
    const x = (e.clientX - rect.left) / (rect.width || window.innerWidth);
    const y = (e.clientY - rect.top) / (rect.height || window.innerHeight);
    mouse.x = Math.max(0, Math.min(1, x));
    mouse.y = Math.max(0, Math.min(1, y));
  };

  if (options.followMouse) {
    window.addEventListener('mousemove', handleMouseMove, { passive: true });
  }

  const resizeObserver = new ResizeObserver(updatePlacement);
  resizeObserver.observe(container);
  window.addEventListener('resize', updatePlacement);

  updatePlacement();
  isRunning = true;
  animationId = requestAnimationFrame(loop);

  return {
    destroy() {
      isRunning = false;
      if (animationId) cancelAnimationFrame(animationId);
      window.removeEventListener('resize', updatePlacement);
      if (options.followMouse) window.removeEventListener('mousemove', handleMouseMove);
      resizeObserver.disconnect();
      try {
        const loseContextExt = gl.getExtension('WEBGL_lose_context');
        if (loseContextExt) loseContextExt.loseContext();
        if (gl.canvas && gl.canvas.parentNode) gl.canvas.parentNode.removeChild(gl.canvas);
      } catch (err) {}
    }
  };
}

// Auto-inject LightRays background across screens
function autoInitBackground() {
  if (typeof document === 'undefined') return;

  // Clean up any previous background (e.g. ghost-fibers)
  const oldGhost = document.getElementById('ghost-fibers-bg');
  if (oldGhost) oldGhost.remove();

  let bg = document.getElementById('light-rays-bg');
  if (!bg) {
    bg = document.createElement('div');
    bg.id = 'light-rays-bg';
    bg.className = 'custom-rays';
    bg.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      z-index: -10;
      pointer-events: none;
      overflow: hidden;
    `;
    document.body.prepend(bg);
  }

  // Ensure body, html, main, and sections let the rays shine through
  if (!document.getElementById('light-rays-style')) {
    const style = document.createElement('style');
    style.id = 'light-rays-style';
    style.textContent = `
      html, body {
        background-color: #07090e !important;
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
      #light-rays-bg {
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        z-index: -10;
        pointer-events: none;
        overflow: hidden;
      }
    `;
    document.head.appendChild(style);
  }

  initLightRays(bg, {
    raysOrigin: 'top-center',
    raysColor: '#afb3dd',
    raysSpeed: 1.5,
    lightSpread: 0.8,
    rayLength: 1.2,
    followMouse: true,
    mouseInfluence: 0.1,
    noiseAmount: 0.1,
    distortion: 0.05
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', autoInitBackground);
} else {
  autoInitBackground();
}
