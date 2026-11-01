import { useEffect, useRef } from 'react';
import './Radar.css';

const vertexSource = `#version 300 es
out vec2 vUv;
void main() {
  vec2 position = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
  vUv = position * 0.5;
  gl_Position = vec4(position * 2.0 - 1.0, 0.0, 1.0);
}`;

const fragmentSource = `#version 300 es
precision highp float;
in vec2 vUv;
out vec4 outColor;
uniform vec2 uResolution;
uniform vec2 uCenter;
uniform vec2 uMouse;
uniform vec3 uColor;
uniform float uTime;
uniform float uScale;
uniform float uTrail;
uniform float uGlow;
uniform float uBrightness;
uniform float uGridOpacity;
uniform float uLineWidth;
uniform float uOpacity;
uniform float uClutter;
uniform float uGrain;
uniform float uIntro;
uniform float uFade;
uniform int uRings;
uniform int uSpokes;
uniform int uTargets;
uniform int uTicks;
uniform int uMouseEnabled;
uniform int uPaused;
uniform int uLightMode;
float hash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}
float circle(float distance, float radius, float width) {
  return 1.0 - smoothstep(width, width * 2.0, abs(distance - radius));
}
void main() {
  vec2 uv = vUv;
  vec2 p = (uv - uCenter) * vec2(uResolution.x / uResolution.y, 1.0) * (2.0 / max(uScale, 0.1));
  float radius = length(p);
  float angle = mod(atan(p.y, p.x) + 6.2831853, 6.2831853);
  float ringStep = 0.92 / float(max(uRings, 1));
  float rings = 0.0;
  for (int i = 1; i <= 8; i++) {
    if (i <= uRings) rings = max(rings, circle(radius, ringStep * float(i), uLineWidth * 0.0016));
  }
  float spokes = 0.0;
  float sector = 6.2831853 / float(max(uSpokes, 1));
  float spokeDistance = abs(sin(angle / sector * 3.14159265));
  spokes = 1.0 - smoothstep(uLineWidth * 0.004, uLineWidth * 0.01, spokeDistance);
  float grid = (rings * 0.75 + spokes * 0.16) * uGridOpacity;
  float sweepAngle = mod(uTime * 0.8, 6.2831853);
  float sweepDistance = mod(sweepAngle - angle + 6.2831853, 6.2831853);
  float sweep = exp(-sweepDistance / max(uTrail, 0.04) * 1.5) * uGlow;
  float beam = exp(-abs(sweepDistance) / 0.045) * uGlow * 0.6;
  float target = 0.0;
  if (uTargets > 0) target = max(target, circle(length(uv - vec2(0.69, 0.62)), 0.0, 0.012));
  if (uTargets > 1) target = max(target, circle(length(uv - vec2(0.34, 0.32)), 0.0, 0.01));
  if (uTargets > 2) target = max(target, circle(length(uv - vec2(0.73, 0.35)), 0.0, 0.009));
  if (uTargets > 3) target = max(target, circle(length(uv - vec2(0.26, 0.69)), 0.0, 0.008));
  if (uTargets > 4) target = max(target, circle(length(uv - vec2(0.56, 0.24)), 0.0, 0.008));
  if (uTargets > 5) target = max(target, circle(length(uv - vec2(0.43, 0.77)), 0.0, 0.007));
  float mouse = 0.0;
  if (uMouseEnabled == 1) mouse = circle(length(uv - uMouse), 0.04, 0.002) * 0.18;
  float tickMarks = 0.0;
  if (uTicks == 1) tickMarks = pow(max(0.0, cos(angle * 24.0)), 42.0) * step(0.72, radius) * step(radius, 0.76);
  float grain = (hash(floor(uv * uResolution) + floor(uTime * 12.0)) - 0.5) * uGrain;
  float clutter = step(1.0 - uClutter * 0.025, hash(floor(uv * 28.0))) * 0.14;
  float alpha = (grid * 0.28 + sweep * 0.12 + beam + target * 0.38 + mouse + tickMarks * 0.16 + clutter + grain) * uOpacity * uBrightness;
  float edgeFade = 1.0 - smoothstep(0.58, 0.98, radius);
  float introFade = mix(1.0, smoothstep(0.0, max(uFade, 0.01), uIntro), step(0.5, uFade));
  alpha *= edgeFade * introFade;
  if (uLightMode == 0) alpha *= 1.25;
  outColor = vec4(uColor, clamp(alpha, 0.0, uOpacity));
}`;

function resolveColor(value) {
  const resolved = value.startsWith('var(')
    ? getComputedStyle(document.documentElement).getPropertyValue(value.slice(4, -1)).trim()
    : value;
  const hex = resolved.match(/^#([0-9a-f]{6})$/i);
  if (!hex) return [0.12, 0.42, 0.27];
  const number = Number.parseInt(hex[1], 16);
  return [(number >> 16 & 255) / 255, (number >> 8 & 255) / 255, (number & 255) / 255];
}

function compileShader(gl, type, source) {
  const shader = gl.createShader(type);
  if (!shader) throw new Error('Unable to allocate a Radar shader.');
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const message = gl.getShaderInfoLog(shader) || 'Radar shader compilation failed.';
    gl.deleteShader(shader);
    throw new Error(message);
  }
  return shader;
}

export default function Radar({
  mode = 'sweep',
  speed = 0.8,
  trail = 0.35,
  scale = 0.95,
  ringCount = 6,
  spokeCount = 12,
  ticks = true,
  targets = 6,
  clutter = 0.25,
  glow = 0.6,
  brightness = 1,
  gridOpacity = 0.9,
  lineWidth = 1,
  tilt = 0,
  mouseInteraction = true,
  intro = true,
  grain = 0.03,
  fade = 0.35,
  opacity = 0.85,
  dpr = 2,
  centerX = 0.5,
  centerY = 0.5,
  lightMode = true,
  backgroundColor = 'transparent',
  color = 'var(--leaf)',
  paused = false,
  className = '',
  style,
  onUnavailable,
  onError,
}) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const gl = canvas.getContext('webgl2', { alpha: true, antialias: true, premultipliedAlpha: false });
    if (!gl) {
      onUnavailable?.();
      return undefined;
    }

    let program;
    let animationFrame = 0;
    let loopRunning = false;
    let draw;
    let resizeObserver;
    let visible = true;
    let pageVisible = document.visibilityState === 'visible';
    let pointer = [0.5, 0.5];
    let failed = false;
    const startTime = performance.now();
    const observerTarget = canvas.closest('.home-hero') || canvas;
    const requestFrame = () => {
      if (loopRunning || paused || !visible || !pageVisible || mode === 'static' || !draw) return;
      loopRunning = true;
      animationFrame = window.requestAnimationFrame((now) => {
        loopRunning = false;
        draw(now);
      });
    };
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      requestFrame();
    }, { threshold: 0.01 });
    observer.observe(observerTarget);

    const updateVisibility = () => {
      pageVisible = document.visibilityState === 'visible';
      if (pageVisible) {
        requestFrame();
      } else {
        window.cancelAnimationFrame(animationFrame);
        animationFrame = 0;
        loopRunning = false;
      }
    };
    const updatePointer = (event) => {
      const rect = canvas.getBoundingClientRect();
      pointer = [
        Math.max(0, Math.min(1, (event.clientX - rect.left) / Math.max(rect.width, 1))),
        1 - Math.max(0, Math.min(1, (event.clientY - rect.top) / Math.max(rect.height, 1))),
      ];
    };
    document.addEventListener('visibilitychange', updateVisibility);
    if (mouseInteraction) window.addEventListener('pointermove', updatePointer, { passive: true });

    try {
      const vertex = compileShader(gl, gl.VERTEX_SHADER, vertexSource);
      const fragment = compileShader(gl, gl.FRAGMENT_SHADER, fragmentSource);
      program = gl.createProgram();
      if (!program) throw new Error('Unable to allocate the Radar program.');
      gl.attachShader(program, vertex);
      gl.attachShader(program, fragment);
      gl.linkProgram(program);
      gl.deleteShader(vertex);
      gl.deleteShader(fragment);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        throw new Error(gl.getProgramInfoLog(program) || 'Radar program linking failed.');
      }

      const uniforms = [
        'uResolution', 'uCenter', 'uMouse', 'uColor', 'uTime', 'uScale', 'uTrail', 'uGlow',
        'uBrightness', 'uGridOpacity', 'uLineWidth', 'uOpacity', 'uClutter', 'uGrain', 'uIntro',
        'uFade', 'uRings', 'uSpokes', 'uTargets', 'uTicks', 'uMouseEnabled', 'uPaused', 'uLightMode',
      ];
      const locations = Object.fromEntries(uniforms.map((name) => [name, gl.getUniformLocation(program, name)]));
      const colorValue = resolveColor(color);
      gl.useProgram(program);
      gl.bindVertexArray(gl.createVertexArray());
      gl.clearColor(0, 0, 0, backgroundColor === 'transparent' ? 0 : 1);

      draw = (now) => {
        if (failed) return;
        const ratio = Math.min(window.devicePixelRatio || 1, dpr);
        const width = Math.max(1, Math.floor(canvas.clientWidth * ratio));
        const height = Math.max(1, Math.floor(canvas.clientHeight * ratio));
        if (canvas.width !== width || canvas.height !== height) {
          canvas.width = width;
          canvas.height = height;
        }
        gl.viewport(0, 0, width, height);
        gl.clear(gl.COLOR_BUFFER_BIT);
        gl.useProgram(program);
        gl.uniform2f(locations.uResolution, width, height);
        gl.uniform2f(locations.uCenter, centerX, centerY);
        gl.uniform2f(locations.uMouse, pointer[0], pointer[1]);
        gl.uniform3f(locations.uColor, ...colorValue);
        gl.uniform1f(locations.uTime, mode === 'static' ? 0 : (now - startTime) * 0.001 * speed);
        gl.uniform1f(locations.uScale, scale);
        gl.uniform1f(locations.uTrail, trail);
        gl.uniform1f(locations.uGlow, glow);
        gl.uniform1f(locations.uBrightness, brightness);
        gl.uniform1f(locations.uGridOpacity, gridOpacity);
        gl.uniform1f(locations.uLineWidth, lineWidth);
        gl.uniform1f(locations.uOpacity, opacity);
        gl.uniform1f(locations.uClutter, clutter);
        gl.uniform1f(locations.uGrain, grain);
        gl.uniform1f(locations.uIntro, intro && !paused ? (now - startTime) * 0.001 : 1);
        gl.uniform1f(locations.uFade, fade);
        gl.uniform1i(locations.uRings, ringCount);
        gl.uniform1i(locations.uSpokes, spokeCount);
        gl.uniform1i(locations.uTargets, targets);
        gl.uniform1i(locations.uTicks, ticks ? 1 : 0);
        gl.uniform1i(locations.uMouseEnabled, mouseInteraction ? 1 : 0);
        gl.uniform1i(locations.uPaused, paused ? 1 : 0);
        gl.uniform1i(locations.uLightMode, lightMode ? 1 : 0);
        gl.drawArrays(gl.TRIANGLES, 0, 3);

        requestFrame();
      };

      draw(startTime);
      requestFrame();
      resizeObserver = new ResizeObserver(() => draw?.(performance.now()));
      resizeObserver.observe(canvas);
    } catch {
      failed = true;
      onError?.();
    }

    return () => {
      failed = true;
      window.cancelAnimationFrame(animationFrame);
      observer.disconnect();
      resizeObserver?.disconnect();
      document.removeEventListener('visibilitychange', updateVisibility);
      window.removeEventListener('pointermove', updatePointer);
      if (program) gl.deleteProgram(program);
    };
  }, [
    backgroundColor, brightness, centerX, centerY, color, clutter, dpr, fade, glow, gridOpacity,
    grain, intro, lightMode, lineWidth, mode, mouseInteraction, onError, onUnavailable, opacity,
    paused, ringCount, scale, speed, spokeCount, targets, ticks, trail,
  ]);

  return (
    <canvas
      ref={canvasRef}
      className={`radar-canvas ${className}`}
      style={{ backgroundColor, rotate: `${tilt}deg`, ...style }}
      aria-hidden="true"
    />
  );
}
