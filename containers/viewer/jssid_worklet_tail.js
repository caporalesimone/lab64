// ---- Lab64 (15/11): the AudioWorkletProcessor around the jsSID core above. Copyright (c) 2026 - Simone Caporale
// Appended to the patched core by containers/viewer/jssid_patch.py into jssid-worklet.js. Page side: www/sidengine.js.
//   options.processorOptions: {bgnoi, offline, sab, cmds}
//     offline: no telemetry (OfflineAudioContext); cmds: [{n, a, play}] applied in order when the processor is created (the
//     settings and the tune of an offline rendering: no race with the first process() call); sab: SharedArrayBuffer for the
//     scope rings (only a page with crossOriginIsolated can make one)
//   port messages from the page: {n: name of a jsSID method, a: arguments}; loadinit / loadstart carry the ArrayBuffer of the
//     .sid file ({n:'loadinit', a:[buffer, subtune], play:true} = load and play); setendcallback gets [on, seconds]
//   port messages to the page, about 60 times a second (and after every command): {t:'tm', regs: $D400-$D41F, env, st, eff, cpu,
//     pt (play time, s), out, vid (getvideo), model, sc: the scope samples written since the last message (not with a SAB)},
//     {t:'info', title, author, info, subtunes, prefmodel} after a load, {t:'end'} at the end of the length
// The same file also holds the silent ANALYZER ('jssida', 1.9, see the end) and is imported by the checkpoint Web Worker (www/sidck.js).
const SCN_ = 8192;
const CMDS_ = new Set(['setmodel', 'setvolume', 'setmute', 'setfilter', 'setoverride', 'setvideo', 'start', 'playcont', 'pause', 'stop']);

class JsSIDProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const o = (options && options.processorOptions) || {};
    this.s = new jsSID(0, o.bgnoi === undefined ? 0.0005 : o.bgnoi);
    this.offline = !!o.offline;
    this.every = Math.max(128, Math.round(sampleRate / 60));       // frames between two telemetry messages
    this.acc = 0;
    this.lp = 0;                                                   // ring position at the last message
    this.posv = null;
    if (o.sab) { this.s.scshare(o.sab); this.posv = new Int32Array(o.sab, SCN_ * 16, 1); }
    this.port.onmessage = e => this.cmd(e.data, false);
    for (const m of (o.cmds || [])) this.cmd(m, true);
  }

  cmd(m, quiet) {
    const s = this.s, a = m.a || [];
    if (m.n === 'loadinit' || m.n === 'loadstart') {
      s.loadinit(a[0], a[1]);
      if (m.play || m.n === 'loadstart') s.playcont();
      if (!this.offline) this.port.postMessage({ t: 'info', title: s.gettitle(), author: s.getauthor(), info: s.getinfo(), subtunes: s.getsubtunes(), prefmodel: s.getprefmodel() });
    } else if (m.n === 'setendcallback') {
      s.setendcallback(a[0] ? () => this.port.postMessage({ t: 'end' }) : null, a[1]);
    } else if (CMDS_.has(m.n)) {
      s[m.n].apply(s, a);
    }
    if (!quiet && !this.offline) this.tick();
  }

  tick() {
    const s = this.s, M = s.getmem(), E = s.getenv(), sc = s.getscope(), S = sc.size;
    const m = { t: 'tm', regs: M.slice(0xD400, 0xD420), env: Uint8Array.from(E.env), st: Uint8Array.from(E.st), eff: Array.from(s.geteff()),
      cpu: s.getcpu(), pt: s.getplaytime(), out: s.getoutput(), vid: s.getvideo(), model: s.getmodel() };
    const tr = [m.regs.buffer, m.env.buffer, m.st.buffer];
    if (this.posv) Atomics.store(this.posv, 0, sc.pos);
    else {                                                         // the samples written since the last message, newest last
      const n = ((sc.pos - this.lp) % S + S) % S, cut = a => { const r = new Float32Array(n); for (let i = 0; i < n; i++) r[i] = a[(sc.pos - n + i + S) % S]; return r; };
      this.lp = sc.pos;
      m.sc = { n, v: [cut(sc.v[0]), cut(sc.v[1]), cut(sc.v[2])], m: cut(sc.m) };
      tr.push(m.sc.v[0].buffer, m.sc.v[1].buffer, m.sc.v[2].buffer, m.sc.m.buffer);
    }
    this.port.postMessage(m, tr);
  }

  process(inputs, outputs) {
    const o = outputs[0][0];
    this.s.render(o, o.length);                                    // nothing written (silence) while paused
    if (!this.offline && (this.acc += o.length) >= this.every) { this.acc = 0; this.tick(); }
    return true;
  }
}
registerProcessor('jssid', JsSIDProcessor);

// ---- Lab64 (1.9): the SID Studio analyzer. Copyright (c) 2026 - Simone Caporale
// With the reSID source the page plays a WAV rendered by sidplayfp; a second jsSID (this processor, 'jssida') runs silently next to it, locked
// to the same audio clock, to feed the panels that need the registers (scopes, envelopes, CPU, piano roll, automation). It is never a
// second sound unless the page asks (A/B): its output goes through a GainNode that the page opens.
//
// KS: sidplayfp's WAVs are time-stretched against the emulated cycles: the effective clock of the file is the C64's times 0.999796 (PAL) /
// 0.999604 (NTSC). Measured with sidplayfp 3.2.3 at 44.1 kHz (the cause is unknown, so the constants are only valid for that version and
// rate); the page's re-lock (analyzer play time against the WAV position, more than 20 ms apart: seek again) covers a different value.
const KS_PAL = 0.999796, KS_NTSC = 0.999604;
// First play call of sidplayfp 3.2.3 with --delay=0 (what containers/tools/py/sidrender.py always uses), in cycles of ITS clock, measured with --cpu-debug on
// test tunes: init starts at 'init'; a VBI tune's first play is at 'vbi', a CIA tune's at 'cia' (these depend on the timer: test tunes with
// latch 19705 PAL / 17045 NTSC, so for another latch it is an approximation). A long init pushes it later: end of init + about 95 cycles of
// the PSID driver. The first sample of the WAV is OFF0 cycles before the init (fit of the WAV edges against the register-write cycles).
const SPF = { pal: { init: 167991, vbi: 177035, cia: 184451 }, ntsc: { init: 156015, vbi: 171086, cia: 173097 } };
// SPF_TRIM: seconds, calibrated on synthetic tunes (a gate toggling every 16 frames, 180 s, PAL / NTSC, VBI / CIA): with the model above the
// analyzer's edges came 1.05 ms after those of the WAV (median over 280-340 edges, drift under 0.04 ms per minute; PAL CIA: a step of 1.8 ms
// half way, which is in sidplayfp's own CIA timing); the trim brings the median to 0. The cause of the 1.05 ms is not known.
const SPF_OFF0 = 2140, SPF_DRIVER = 95, SPF_TRIM = -0.00105;

// a jsSID configured like the analyzer: bgnoi 0 (no dither), clock scale, video standard, model ('auto' = the header's), loaded and initialized
function lab64Make(buf, sub, model, video) {
  const s = new jsSID(0, 0);
  s.setks(KS_PAL, KS_NTSC); s.setvideo(video || 'auto');
  s.loadinit(buf, sub || 0);
  s.setmodel(!model || model === 'auto' ? s.getprefmodel() : +model);
  return s;
}
// seconds from the first sample of the sidplayfp WAV to its first play call, from the init cycles counted by the patch (getinit)
function lab64FirstPlay(s) {
  const v = s.getvideo(), i = s.getinit(), k = SPF[v.std], ks = v.std === 'ntsc' ? KS_NTSC : KS_PAL;
  const first = Math.max(i.cia ? k.cia : k.vbi, k.init + i.cyc + SPF_DRIVER);
  return (first - (k.init - SPF_OFF0)) / (v.clk * ks) + SPF_TRIM;
}

// Messages from the page: {n:'load', gen, buf, sub, model, video}; {n:'arm', armF, startF, restore}: analyzer sample 0 is at context frame
// armF, the WAV is audible from frame startF; restore = {done, st} (a checkpoint: state taken after 'done' samples; no st = the state
// after init) or null (continue); {n:'goto', restore, to}: only emulate up to sample 'to' and wait there (a seek while paused);
// {n:'pause'}; {n:'call', m, a}: setmute / setfilter / setvolume.
// Every block it knows how many samples it is missing (the context clock is the truth): behind -> fast-forward at most 0.05 s of emulation
// (about 1 ms) before the block's own samples, ahead -> wait. Locked = no fast-forward in this block and nothing missing.
// To the page: {t:'loaded', gen, tp1 (first play, s), init, vid, model}, {t:'paused', gen, done}, and about 60 times a second {t:'tm', gen, f (frame at
// the end of the block), done, lock, on, regs, env, st, eff, cpu, out, vid, model, sc (scope samples since the last message), mwg (longest wall
// time between two blocks, ms), mpr (longest block, ms)}.
class JsSIDAnalyzer extends AudioWorkletProcessor {
  constructor() {
    super();
    this.s = null; this.init = null; this.on = false; this.hold = null; this.held = true; this.done = 0; this.armF = 0; this.startF = 0; this.gen = 0;
    this.every = Math.max(128, Math.round(sampleRate / 60)); this.acc = 0; this.lp = 0;
    this.ffMax = Math.round(0.05 * sampleRate);
    this.mwg = 0; this.mpr = 0; this.lastW = 0;
    this.port.onmessage = e => this.cmd(e.data);
  }
  restore(r) {
    if (!r) return;
    this.s.setstate(r.st || this.init); this.done = r.done; this.lp = this.s.getscope().pos;
  }
  cmd(m) {
    if (m.n === 'load') {
      this.on = false; this.hold = null; this.gen = m.gen;
      const s = this.s = lab64Make(m.buf, m.sub, m.model, m.video);
      this.init = s.getstate(); this.done = 0; this.lp = s.getscope().pos; s.playcont();
      this.port.postMessage({ t: 'loaded', gen: m.gen, tp1: lab64FirstPlay(s), init: s.getinit(), vid: s.getvideo(), model: s.getmodel(), prefmodel: s.getprefmodel() });
    } else if (!this.s) return;
    else if (m.n === 'arm') { this.restore(m.restore); this.armF = m.armF; this.startF = m.startF; this.hold = null; this.on = true; }
    else if (m.n === 'goto') { this.restore(m.restore); this.hold = m.to; this.held = false; this.on = false; }
    else if (m.n === 'pause') { this.on = false; this.hold = null; this.port.postMessage({ t: 'paused', gen: this.gen, done: this.done }); }
    else if (m.n === 'call') this.s[m.m].apply(this.s, m.a);
  }
  tick(E, lock) {
    const s = this.s, sc = s.getscope(), S = sc.size, M = s.getmem(), En = s.getenv();
    const m = { t: 'tm', gen: this.gen, f: E, done: this.done, lock, on: this.on, mwg: this.mwg, mpr: this.mpr };
    this.mwg = 0; this.mpr = 0;
    const tr = [];
    if (lock) {
      m.regs = M.slice(0xD400, 0xD420); m.env = Uint8Array.from(En.env); m.st = Uint8Array.from(En.st); m.eff = Array.from(s.geteff());
      m.cpu = s.getcpu(); m.out = s.getoutput(); m.vid = s.getvideo(); m.model = s.getmodel();
      const n = ((sc.pos - this.lp) % S + S) % S, cut = a => { const r = new Float32Array(n); for (let i = 0; i < n; i++) r[i] = a[(sc.pos - n + i + S) % S]; return r; };
      m.sc = { n, v: [cut(sc.v[0]), cut(sc.v[1]), cut(sc.v[2])], m: cut(sc.m) };
      tr.push(m.regs.buffer, m.env.buffer, m.st.buffer, m.sc.v[0].buffer, m.sc.v[1].buffer, m.sc.v[2].buffer, m.sc.m.buffer);
    }
    this.lp = sc.pos;
    this.port.postMessage(m, tr);
  }
  process(inputs, outputs) {
    const w0 = Date.now(); if (this.lastW && w0 - this.lastW > this.mwg) this.mwg = w0 - this.lastW; this.lastW = w0;
    const o = outputs[0][0], n = o.length, s = this.s, E = currentFrame + n;
    let ff = 0, lock = false, active = false;
    if (s && this.on) {
      active = true;
      const pre = E <= this.startF, tgt = (pre ? this.startF : E) - this.armF, keep = pre ? 0 : n;   // before the start point: fast-forward only
      let need = tgt - this.done;
      if (need > keep) { ff = Math.min(need - keep, this.ffMax); s.ff(ff); this.done += ff; need -= ff; this.lp = s.getscope().pos; }
      if (!pre && need > 0) { const k = Math.min(need, n); s.render(o.subarray(n - k), k); this.done += k; need -= k; }
      lock = !ff && need === 0;                                                  // ahead (need < 0: a checkpoint up to 0.1 s past the point) = wait for the clock, not locked yet
    } else if (s && this.hold !== null) {
      active = true;
      if (this.done < this.hold) { ff = Math.min(this.hold - this.done, this.ffMax); s.ff(ff); this.done += ff; }
      lock = this.done >= this.hold;
      if (lock && !this.held) { this.held = true; this.tick(E, true); }
    }
    if (active && this.on && (this.acc += n) >= this.every) { this.acc = 0; this.tick(E, lock); }
    const dt = Date.now() - w0; if (dt > this.mpr) this.mpr = dt;
    return true;
  }
}
registerProcessor('jssida', JsSIDAnalyzer);
