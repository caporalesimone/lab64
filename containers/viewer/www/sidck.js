// Lab64 viewer: checkpoint builder of the SID Studio analyzer, a Web Worker (1.9). Copyright (c) 2026 - Simone Caporale
//
// It runs the SAME patched jsSID core as the analyzer (vendor/jssid/jssid-worklet.js, imported with stubs for the AudioWorklet
// globals; lab64Make() configures it exactly like the analyzer: clock scale, video standard, model) and fast-forwards through the tune,
// posting a state (getstate: the 64 KB memory + about 1.2 KB of chip and CPU state) every `step` seconds of emulation. A seek then
// restores the nearest earlier state and fast-forwards a few seconds at most, in slices, instead of emulating from the start; the
// fast-forward costs about 16-22 ms per emulated second, so it must not run in the audio thread.
// Messages in: {n:'build', gen, buf, sub, model, video, sr, step, max}  ({n:'stop'} abandons the job; the page also just terminates the worker)
// Messages out: {t:'ck', gen, k, st} (state after k * step seconds), {t:'done', gen}
'use strict';
self.AudioWorkletProcessor = class { constructor() { this.port = {}; } };
self.registerProcessor = () => {};
self.sampleRate = 44100;
importScripts('vendor/jssid/jssid-worklet.js');
let job = 0;
onmessage = async e => {
  const m = e.data;
  if (m.n === 'stop') { job++; return; }
  if (m.n !== 'build') return;
  const my = ++job;
  self.sampleRate = m.sr;                                       // read by the core when the player is created
  const s = lab64Make(m.buf, m.sub, m.model, m.video), step = Math.round(m.step * m.sr);
  for (let k = 1; k * m.step <= m.max; k++) {
    for (let left = step; left > 0;) {                          // one second of emulation at a time, so that a new job is noticed
      const q = Math.min(left, m.sr); s.ff(q); left -= q;
      await new Promise(r => setTimeout(r, 0));
      if (job !== my) return;
    }
    postMessage({ t: 'ck', gen: m.gen, k, st: s.getstate() });
  }
  postMessage({ t: 'done', gen: m.gen });
};
