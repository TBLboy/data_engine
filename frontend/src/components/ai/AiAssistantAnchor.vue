<template>
  <button
    class="ai-anchor ai-grounded-socket"
    :class="{
      'is-active': active,
      'is-thinking': status === 'thinking',
      'is-error': status === 'error'
    }"
    :aria-expanded="active"
    aria-label="打开 AI 质检助手"
    @click="toggle"
  >
    <span class="ai-core-grounded" aria-hidden="true">
      <span class="core-bloom" />
      <span class="core-glass" />
      <span class="core-grid" />
      <span class="core-lens" />
      <span class="core-highlight" />
      <svg class="core-ring-svg" viewBox="0 0 74 74" aria-hidden="true">
        <defs>
          <linearGradient id="ringGradientV3AI" x1="9" y1="9" x2="65" y2="65" gradientUnits="userSpaceOnUse">
            <stop stop-color="#efffff" />
            <stop offset="0.42" stop-color="#25e8d4" />
            <stop offset="1" stop-color="#1f77ff" />
          </linearGradient>
        </defs>
        <circle class="ring-outer" cx="37" cy="37" r="34" />
        <circle class="ring-mid" cx="37" cy="37" r="29" stroke="url(#ringGradientV3AI)" />
        <circle class="ring-inner" cx="37" cy="37" r="19" />
        <g class="ticks">
          <path d="M37 2.3v6.2"/><path d="M37 65.5v6.2"/>
          <path d="M2.3 37h6.2"/><path d="M65.5 37h6.2"/>
          <path d="M12.5 12.5l4.1 4.1"/><path d="M57.4 57.4l4.1 4.1"/>
          <path d="M61.5 12.5l-4.1 4.1"/><path d="M16.6 57.4l-4.1 4.1"/>
        </g>
      </svg>
      <span class="core-orbit"><span class="core-particle" /></span>
      <span class="core-scan" />
    </span>
    <span class="socket-status"><span /></span>
  </button>
</template>

<script setup lang="ts">
const props = defineProps<{
  active?: boolean
  status?: 'idle' | 'thinking' | 'error'
}>()

const emit = defineEmits<{
  (e: 'open'): void
  (e: 'close'): void
}>()

function toggle() {
  if (props.active) {
    emit('close')
  } else {
    emit('open')
  }
}
</script>

<style scoped>
.ai-anchor {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  padding: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}
.ai-anchor:focus-visible { outline: 3px solid rgba(31,184,255,.34); outline-offset: 5px; border-radius: 999px; }

.ai-grounded-socket {
  width: 108px;
  height: 108px;
  border-radius: 999px;
  background:
    radial-gradient(circle at 50% 46%, rgba(255,255,255,.98) 0 44%, rgba(244,249,255,.92) 45% 61%, rgba(232,242,252,.82) 62% 100%),
    linear-gradient(145deg, #ffffff, #edf5fc);
  border: 1px solid rgba(204, 220, 235, .92);
  box-shadow:
    inset 0 2px 5px rgba(255,255,255,.98),
    inset 0 -10px 22px rgba(42, 83, 123, .075),
    inset 0 0 0 9px rgba(243, 248, 253, .74),
    0 8px 18px rgba(31, 63, 96, .075);
  transition: border-color .22s ease, box-shadow .22s ease, background .22s ease, transform .22s cubic-bezier(.2,.9,.22,1);
}

.ai-grounded-socket::before {
  content: "";
  position: absolute;
  inset: 9px;
  border-radius: 999px;
  background: linear-gradient(145deg, rgba(245, 251, 255, .98), rgba(230, 241, 250, .86));
  border: 1px solid rgba(202, 220, 237, .86);
  box-shadow:
    inset 0 4px 10px rgba(48, 82, 114, .11),
    inset 0 -1px 0 rgba(255,255,255,.96);
  pointer-events: none;
}

.ai-grounded-socket::after {
  content: "";
  position: absolute;
  left: 24px;
  right: 24px;
  bottom: 8px;
  height: 8px;
  border-radius: 999px;
  background: rgba(34, 73, 112, .13);
  filter: blur(8px);
  opacity: .48;
  pointer-events: none;
}

.ai-grounded-socket:hover,
.ai-grounded-socket.is-active {
  border-color: rgba(61, 176, 230, .50);
  box-shadow:
    inset 0 2px 5px rgba(255,255,255,.98),
    inset 0 -10px 22px rgba(42, 83, 123, .075),
    inset 0 0 0 9px rgba(243, 248, 253, .78),
    0 10px 20px rgba(31, 85, 130, .095),
    0 0 0 1px rgba(37, 232, 212, .08);
}
.ai-grounded-socket.is-thinking { border-color: rgba(117,102,255,.42); }
.ai-grounded-socket.is-error { border-color: rgba(216,102,114,.36); filter: saturate(.82); }

.ai-core-grounded {
  position: relative;
  width: 74px;
  height: 74px;
  flex: 0 0 74px;
  border-radius: 50%;
  z-index: 2;
  filter: drop-shadow(0 7px 10px rgba(24, 82, 122, .18));
  transition: transform .22s cubic-bezier(.2,.9,.22,1), filter .22s ease;
}
.ai-grounded-socket:hover .ai-core-grounded,
.ai-grounded-socket.is-active .ai-core-grounded {
  transform: scale(1.035);
  filter: drop-shadow(0 8px 12px rgba(31, 119, 255, .18));
}

.core-bloom, .core-glass, .core-lens, .core-ring-svg, .core-orbit, .core-particle, .core-scan, .core-grid, .core-highlight {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  pointer-events: none;
}

.core-bloom {
  inset: 2px;
  background: radial-gradient(circle, rgba(37,232,212,.20) 0 30%, rgba(31,184,255,.10) 45%, transparent 70%);
  opacity: .62;
  filter: blur(5px);
  animation: socketBreath 4.6s ease-in-out infinite;
}
.core-glass {
  inset: 9px;
  background:
    radial-gradient(circle at 30% 22%, rgba(255,255,255,.98) 0 9%, rgba(255,255,255,.32) 14%, transparent 34%),
    radial-gradient(circle at 46% 48%, #a9fff5 0 8%, #29ecd9 20%, #1fb8ff 41%, rgba(31, 58, 102, .94) 72%, rgba(12, 29, 54, .98) 100%);
  box-shadow:
    inset 0 1px 1px rgba(255,255,255,.88),
    inset 0 -12px 22px rgba(8, 29, 57, .56),
    0 0 0 1px rgba(255,255,255,.64),
    0 0 14px rgba(37,232,212,.22);
  animation: coreBreath 3.9s ease-in-out infinite;
}
.core-lens {
  inset: 15px;
  background:
    linear-gradient(145deg, rgba(255,255,255,.34), transparent 34%),
    radial-gradient(circle at 60% 58%, rgba(255,255,255,.25), transparent 30%);
  box-shadow: inset 0 0 0 1px rgba(255,255,255,.28);
}
.core-grid {
  inset: 16px;
  opacity: .28;
  background:
    linear-gradient(90deg, transparent 0 46%, rgba(235,255,255,.58) 47% 52%, transparent 53% 100%),
    linear-gradient(0deg, transparent 0 46%, rgba(235,255,255,.46) 47% 52%, transparent 53% 100%);
  mask: radial-gradient(circle, #000 0 62%, transparent 63%);
  mix-blend-mode: screen;
}
.core-highlight {
  inset: 8px;
  background: radial-gradient(circle at 28% 22%, rgba(255,255,255,.72), rgba(255,255,255,.16) 13%, transparent 28%);
  opacity: .84;
}
.core-ring-svg { overflow: visible; }
.core-ring-svg .ring-outer { stroke: rgba(155, 217, 238, .76); stroke-width: 1; fill: none; stroke-dasharray: 88 18 28 16; animation: coreDash 10s linear infinite; }
.core-ring-svg .ring-mid { stroke-width: 1.55; fill: none; stroke-dasharray: 20 140; stroke-linecap: round; animation: coreDashReverse 4.4s linear infinite; filter: drop-shadow(0 0 4px rgba(31,184,255,.62)); }
.core-ring-svg .ring-inner { stroke: rgba(37,232,212,.82); stroke-width: .75; fill: none; stroke-dasharray: 3 7; opacity: .86; }
.core-ring-svg .ticks { stroke: rgba(255,255,255,.70); stroke-width: .75; stroke-linecap: round; opacity: .58; }
.core-orbit {
  inset: 4px;
  animation: coreRotate 6.4s linear infinite;
}
.core-particle {
  position: absolute;
  width: 7px;
  height: 7px;
  right: 7px;
  top: 31px;
  border-radius: 999px;
  background: radial-gradient(circle, #fff, #bafdf6 36%, #25e8d4 66%, transparent 72%);
  box-shadow: 0 0 9px rgba(37,232,212,.78), 0 0 15px rgba(31,184,255,.38);
}
.core-orbit::after {
  content:"";
  position:absolute;
  width: 4px;
  height: 4px;
  left: 9px;
  top: 14px;
  border-radius: 999px;
  background: #8aa8ff;
  box-shadow: 0 0 8px rgba(117,102,255,.62);
  opacity: .58;
}
.core-scan {
  inset: 13px;
  background: conic-gradient(from 0deg, transparent 0 70%, rgba(255,255,255,.48) 77%, rgba(37,232,212,.28) 83%, transparent 92% 100%);
  mix-blend-mode: screen;
  opacity: .42;
  animation: coreScan 5.3s linear infinite;
}

.socket-status {
  position: absolute;
  z-index: 3;
  right: 6px;
  bottom: 6px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 20px;
  padding: 0 7px;
  border-radius: 999px;
  background: rgba(255,255,255,.92);
  border: 1px solid rgba(211, 226, 240, .92);
  color: #4d6a82;
  font-size: 10px;
  line-height: 1;
  box-shadow: 0 5px 10px rgba(31, 63, 96, .08);
}
.socket-status::before {
  content: "";
  width: 5px;
  height: 5px;
  border-radius: 999px;
  background: #25e8d4;
  box-shadow: 0 0 0 3px rgba(37,232,212,.12);
}
.ai-grounded-socket.is-thinking .socket-status { color: #625de2; }
.ai-grounded-socket.is-thinking .socket-status::before { background: #7566ff; box-shadow: 0 0 0 3px rgba(117,102,255,.12); }
.ai-grounded-socket.is-thinking .socket-status span::before { content: "Analyzing"; }
.socket-status span::before { content: "Ready"; }

.ai-grounded-socket.is-thinking .core-orbit { animation-duration: 1.1s; }
.ai-grounded-socket.is-thinking .core-scan { animation-duration: 1s; opacity: .86; }
.ai-grounded-socket.is-thinking .core-ring-svg .ring-mid { animation-duration: 1.1s; }
.ai-grounded-socket.is-error .core-glass { filter: grayscale(.25); }

.ai-tooltip {
  position: absolute;
  left: 50%;
  bottom: calc(100% + 10px);
  transform: translate(-50%, 6px);
  width: max-content;
  min-width: 172px;
  padding: 9px 11px;
  border-radius: 13px;
  background: rgba(22, 36, 54, .94);
  color: white;
  box-shadow: 0 12px 30px rgba(20, 36, 56, .20);
  opacity: 0;
  pointer-events: none;
  transition: opacity .18s ease, transform .18s ease;
  text-align: left;
}
.ai-tooltip::after {
  content:"";
  position:absolute;
  left:50%; bottom:-5px;
  width:10px; height:10px;
  transform: translateX(-50%) rotate(45deg);
  background: rgba(22, 36, 54, .94);
}
.ai-tooltip b { display:block; font-size: 12px; line-height: 1.3; }
.ai-tooltip span { display:block; margin-top:3px; font-size:11px; color: rgba(255,255,255,.72); }
.ai-anchor:hover .ai-tooltip { opacity: 1; transform: translate(-50%, 0); }

@keyframes socketBreath { 0%,100% { opacity:.50; transform: scale(.99); } 50% { opacity:.75; transform: scale(1.025); } }
@keyframes coreBreath { 0%,100% { transform: scale(.99); } 50% { transform: scale(1.016); } }
@keyframes coreRotate { to { transform: rotate(360deg); } }
@keyframes coreScan { to { transform: rotate(360deg); } }
@keyframes coreDash { to { stroke-dashoffset: -150; } }
@keyframes coreDashReverse { to { stroke-dashoffset: 160; } }

@media (prefers-reduced-motion: reduce) {
  .core-bloom, .core-glass, .core-orbit, .core-scan, .core-ring-svg .ring-outer, .core-ring-svg .ring-mid { animation: none !important; }
}
</style>
