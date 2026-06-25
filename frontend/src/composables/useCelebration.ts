import confetti from 'canvas-confetti'

export function triggerCelebration(onDone: () => void) {
  const ctx = new AudioContext()
  const notes = [523.25, 659.25, 783.99]
  notes.forEach((freq, i) => {
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'sine'
    osc.frequency.value = freq
    gain.gain.setValueAtTime(0, ctx.currentTime + i * 0.15)
    gain.gain.linearRampToValueAtTime(0.3, ctx.currentTime + i * 0.15 + 0.05)
    gain.gain.linearRampToValueAtTime(0, ctx.currentTime + i * 0.15 + 0.4)
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.start(ctx.currentTime + i * 0.15)
    osc.stop(ctx.currentTime + i * 0.15 + 0.4)
  })

  const duration = 3000
  const end = Date.now() + duration
  const colors = ['#2563eb', '#f59e0b', '#16a34a', '#7c3aed', '#ef4444']

  function frame() {
    confetti({
      particleCount: 3,
      angle: 60,
      spread: 55,
      origin: { x: 0, y: 0.6 },
      colors,
    })
    confetti({
      particleCount: 3,
      angle: 120,
      spread: 55,
      origin: { x: 1, y: 0.6 },
      colors,
    })
    if (Date.now() < end) requestAnimationFrame(frame)
  }
  frame()

  setTimeout(() => {
    confetti({
      particleCount: 150,
      spread: 100,
      origin: { x: 0.5, y: 0.4 },
      colors,
    })
  }, 1500)

  setTimeout(onDone, duration + 500)
}
