// Small call sounds generated with the Web Audio API (no audio files needed).
// Browsers only allow audio after a user click, so call these from click handlers.

let ctx;
let ringTimer = null;

function audio() {
  ctx ??= new (window.AudioContext || window.webkitAudioContext)();
  if (ctx.state === "suspended") ctx.resume();
  return ctx;
}

function tone(freq, start, duration, gain = 0.05) {
  const c = audio();
  const osc = c.createOscillator();
  const amp = c.createGain();
  const t0 = c.currentTime + start;
  osc.type = "sine";
  osc.frequency.value = freq;
  amp.gain.setValueAtTime(0, t0);
  amp.gain.linearRampToValueAtTime(gain, t0 + 0.02);
  amp.gain.linearRampToValueAtTime(0, t0 + duration);
  osc.connect(amp).connect(c.destination);
  osc.start(t0);
  osc.stop(t0 + duration + 0.05);
}

export function startRing() {
  stopRing();
  const ring = () => {
    for (const offset of [0, 0.5]) {
      tone(440, offset, 0.4);
      tone(480, offset, 0.4);
    }
  };
  ring();
  ringTimer = setInterval(ring, 2200);
}

export function stopRing() {
  if (ringTimer) clearInterval(ringTimer);
  ringTimer = null;
}

export function playPickup() {
  tone(660, 0, 0.09);
  tone(880, 0.1, 0.12);
}

export function playEnd() {
  tone(480, 0, 0.16);
  tone(360, 0.2, 0.28);
}
