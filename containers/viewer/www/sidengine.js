// Lab64 viewer: the sound engine of SID Studio (15/11). Copyright (c) 2026 - Simone Caporale
//
// jsSID (vendor/jssid/jsSID.js, patched at image build time by containers/viewer/jssid_patch.py) computes the sound in a
// ScriptProcessorNode: on the main thread, together with all the drawing of the page, which makes it crackle under load.
// The same patched core is also built as an AudioWorklet module (vendor/jssid/jssid-worklet.js). This file chooses the engine
// and, for the worklet, is the main-thread side: WorkletPlayer has the SAME public API as jsSID (loadinit / loadstart / start /
// playcont / pause / stop, setmodel, setvolume, setmute, setfilter, setoverride, setvideo, getscope, getmem, getenv, getcpu,
// geteff, getvideo, getplaytime, gettitle / getauthor / getinfo / getsubtunes / getprefmodel, the three callbacks, getctx,
// setoutput, ...): commands go to the processor with port.postMessage, the state comes back about 60 times a second:
//   registers $D400-$D41F (getmem() is a 64 KB array where only that range is kept), envelopes, effective filter registers,
//   play routine cycles, play time, and the scope buffers: the samples written since the last message, copied by the page into
//   its own ring buffers, or (only when the page is crossOriginIsolated) rings in a SharedArrayBuffer written by the processor.
// Commands given before the module is loaded are kept and sent in order. SIDEngine.create() returns the worklet player when the
// page has a secure context (https or localhost) and AudioWorklet, otherwise (or with engine 'script', e.g. ?engine=script in
// sid.html) a plain jsSID, ScriptProcessor, as before. player.engine is 'worklet' or 'script'.
// SIDEngine.Analyzer (1.9): the silent jsSID that follows the WAV of the reSID source (see the class below).
// SIDEngine.renderOffline() renders a tune faster than real time with an OfflineAudioContext and the same worklet module (the
// settings and the file travel in the processor options: no race with the first block); it needs the worklet (offlineOk()).
(function (g) {
  'use strict';
  const MODULE = 'vendor/jssid/jssid-worklet.js', SCN = 8192;
  const AC = g.AudioContext || g.webkitAudioContext;
  const text = t => String(t || '').replace(/\0+$/, '').trim();       // jsSID returns its fixed 32 character fields with NULs

  function workletOk() { return !!(g.isSecureContext && AC && 'audioWorklet' in AC.prototype && typeof g.AudioWorkletNode !== 'undefined'); }

  class WorkletPlayer {
    constructor(opts) {
      opts = opts || {};
      this.engine = 'worklet';
      this.author = 'Hermit'; this.sourcecode = 'http://hermit.sidrip.com'; this.version = '0.9.1'; this.year = '2016';
      this.ctx = new AC();
      this.bgnoi = opts.bgnoi === undefined ? 0.0005 : opts.bgnoi;
      this.dest = this.ctx.destination;                            // where the engine is connected while it plays (setoutput)
      this.node = null; this.queue = []; this.playing = false; this.tok = 0; this.error = null; this.onfail = null;
      this.cb = { load: null, start: null, end: null };
      this.model = 8580.0;
      this.info = { title: '', author: '', info: '', subtunes: 1, prefmodel: 8580 };
      this.t = { regs: new Uint8Array(32), env: new Uint8Array(9), st: new Uint8Array(9), eff: [0, 0, 0, 0], cpu: 0, pt: 0, out: 0,
        vid: { sel: 'auto', std: 'pal', hdr: 'unknown', clk: 985248, fr: 985248 / 19656, frc: 19656 } };
      this.mem = new Uint8Array(65536);
      this.sc = { v: [0, 1, 2].map(() => new Float32Array(SCN)), m: new Float32Array(SCN), pos: 0, size: SCN };
      this.sab = null; this.posv = null;
      if (g.crossOriginIsolated && typeof SharedArrayBuffer !== 'undefined' && opts.sab !== false) {
        this.sab = new SharedArrayBuffer(SCN * 16 + 4);                // 3 voices + mix, floats, then the ring position
        this.sc.v = [0, 1, 2].map(k => new Float32Array(this.sab, SCN * 4 * k, SCN)); this.sc.m = new Float32Array(this.sab, SCN * 12, SCN);
        this.posv = new Int32Array(this.sab, SCN * 16, 1);
      }
      this.ready = this._start();
    }

    async _start() {
      try {
        await this.ctx.audioWorklet.addModule(MODULE);
        const n = this.node = new g.AudioWorkletNode(this.ctx, 'jssid', { numberOfInputs: 0, numberOfOutputs: 1, outputChannelCount: [1],
          processorOptions: { bgnoi: this.bgnoi, offline: false, sab: this.sab } });
        n.port.onmessage = e => this._msg(e.data);
        n.onprocessorerror = () => this._fail(new Error('the AudioWorklet processor stopped'));
        for (const [m, tr] of this.queue) n.port.postMessage(m, tr);
        this.queue = [];
        if (this.playing) n.connect(this.dest);
      } catch (e) { this._fail(e); }
    }
    _fail(e) { this.error = e; if (this.onfail) this.onfail(e); }
    _post(m, tr) { if (this.node) this.node.port.postMessage(m, tr || []); else this.queue.push([m, tr || []]); }

    _msg(m) {
      if (m.t === 'tm') {
        const t = this.t; t.regs = m.regs; t.env = m.env; t.st = m.st; t.eff = m.eff; t.cpu = m.cpu; t.pt = m.pt; t.out = m.out; t.vid = m.vid;
        this.mem.set(m.regs, 0xD400);
        if (m.sc && m.sc.n) this._push(m.sc);
      } else if (m.t === 'info') {
        this.info = { title: text(m.title), author: text(m.author), info: text(m.info), subtunes: m.subtunes, prefmodel: m.prefmodel };
        if (this.cb.load) this.cb.load();
      } else if (m.t === 'end') { if (this.cb.end) this.cb.end(); }
    }
    _push(sc) {                                                     // the samples written since the last message into the rings
      const n = Math.min(sc.n, SCN), off = sc.n - n, S = SCN, dst = [this.sc.v[0], this.sc.v[1], this.sc.v[2], this.sc.m], src = [sc.v[0], sc.v[1], sc.v[2], sc.m];
      let p = this.sc.pos;
      for (let c = 0; c < 4; c++) { p = this.sc.pos; for (let i = 0; i < n; i++) { dst[c][p] = src[c][off + i]; if (++p === S) p = 0; } }
      this.sc.pos = p;
    }

    _connect() { this.playing = true; if (this.ctx.state === 'suspended') this.ctx.resume().catch(() => {}); if (this.node) this.node.connect(this.dest); }
    _disconnect() { this.playing = false; if (this.node) try { this.node.disconnect(); } catch (e) { /* not connected */ } }
    _load(url, subt, play) {                                        // the page fetches the file, the processor parses it
      const tok = ++this.tok;
      this._disconnect(); this._post({ n: 'pause' });
      fetch(url).then(r => { if (!r.ok) throw new Error(url + ': HTTP ' + r.status); return r.arrayBuffer(); })
        .then(buf => { if (tok === this.tok) this._post({ n: 'loadinit', a: [buf, subt], play: !!play }, [buf]); })
        .catch(e => this._fail(e));
    }

    // ---- the API of jsSID
    loadstart(url, subt) { this._load(url, subt, true); if (this.cb.start) this.cb.start(); this._connect(); }
    loadinit(url, subt) { this._load(url, subt, false); }
    start(subt) { this._post({ n: 'start', a: [subt] }); if (this.cb.start) this.cb.start(); this._connect(); }
    playcont() { this._post({ n: 'playcont' }); this._connect(); }
    pause() { this._post({ n: 'pause' }); this._disconnect(); }
    stop() { this._disconnect(); this._post({ n: 'stop' }); this.t.pt = 0; }
    setmodel(m) { this.model = m; this._post({ n: 'setmodel', a: [m] }); }
    setvolume(v) { this._post({ n: 'setvolume', a: [v] }); }
    setmute(ch, on) { this._post({ n: 'setmute', a: [ch, on] }); }
    setfilter(on) { this._post({ n: 'setfilter', a: [on] }); }
    setoverride(o) { this._post({ n: 'setoverride', a: [o || {}] }); }
    setvideo(m) { this._post({ n: 'setvideo', a: [m] }); this.t.vid = Object.assign({}, this.t.vid, { sel: m }); }
    setloadcallback(f) { this.cb.load = f; }
    setstartcallback(f) { this.cb.start = f; }
    setendcallback(f, seconds) { this.cb.end = f; this._post({ n: 'setendcallback', a: [f !== null && f !== undefined, seconds] }); }
    setoutput(n) { const was = this.playing; if (was) this._disconnect(); this.dest = n; if (was) this._connect(); }
    getctx() { return this.ctx; }
    getscope() { if (this.posv) this.sc.pos = Atomics.load(this.posv, 0); return this.sc; }
    getmem() { return this.mem; }
    getenv() { return { env: this.t.env, st: this.t.st }; }
    getcpu() { return this.t.cpu; }
    geteff() { return this.t.eff; }
    getvideo() { return this.t.vid; }
    getplaytime() { return this.t.pt; }
    getoutput() { return this.t.out; }
    gettitle() { return this.info.title; }
    getauthor() { return this.info.author; }
    getinfo() { return this.info.info; }
    getsubtunes() { return this.info.subtunes; }
    getprefmodel() { return this.info.prefmodel; }
    getmodel() { return this.model; }
  }


  // ---- the analyzer (1.9). With the reSID source the page plays a WAV that sidplayfp rendered; this runs a SECOND jsSID next to it, silently,
  // locked to the same AudioContext clock, so that the panels that need registers, envelopes, voice outputs and play routine cycles can
  // be fed. Pieces: the worklet processor 'jssida' (jssid_worklet_tail.js: it is told at which context frame its sample 0 is, restores a state,
  // fast-forwards in slices of at most 0.05 s of emulation per 128-sample block until it has caught up with the clock, then renders the blocks
  // as they come), a Web Worker (sidck.js) that builds a checkpoint (the complete emulation state) every 10 s of the tune, and this class.
  // Time: analyzer sample 0 = the first play call of the tune; the WAV of sidplayfp has it tp1 seconds after its own first sample (init time
  // and sidplayfp's first play delay, computed by the processor from the init cycles), and the analyzer's clock is scaled to the WAV's.
  // play(startT, off): the WAV starts at context time startT from offset off. Seek = play() again (or hold() while paused).
  // Output: node -> gain (0) -> dest. The gain is what the A/B button opens (crossfade): a worklet connected to nothing would not run.
  // Telemetry arrives about the output latency before the sound: pump() hands the panels the messages whose frame has been output by now.
  const CK_STEP = 10, AN_PRE = 0.03;
  class Analyzer {
    constructor(ctx, ready, dest) {
      this.ctx = ctx; this.sr = ctx.sampleRate; this.gain = ctx.createGain(); this.gain.gain.value = 0; this.gain.connect(dest);
      this.node = null; this.worker = null; this.gen = 0; this.error = null; this.onfail = null; this.onapply = null;
      this.queue = []; this.cks = new Map(); this.maxk = 0; this.want = null; this.paused = null; this.map = null; this.holdTo = null;
      this.loaded = false; this.locked = false; this.status = 'idle'; this.tp1 = 0; this.info = null; this.opts = null; this.bytes = null;
      this.relocks = 0; this.maxGap = 0; this.maxProc = 0; this.workerOk = true;
      this.t = { regs: new Uint8Array(32), env: new Uint8Array(9), st: new Uint8Array(9), eff: [0, 0, 0, 0], cpu: 0, out: 0, done: 0,
        vid: { sel: 'auto', std: 'pal', hdr: 'unknown', clk: 985248, fr: 985248 / 19656, frc: 19656 }, model: 8580 };
      this.mem = new Uint8Array(65536);
      this.sc = { v: [0, 1, 2].map(() => new Float32Array(SCN)), m: new Float32Array(SCN), pos: 0, size: SCN };
      const self = this;
      this.view = { getmem: () => self.mem, getenv: () => ({ env: self.t.env, st: self.t.st }), getscope: () => self.sc, getcpu: () => self.t.cpu,
        geteff: () => self.t.eff, getvideo: () => self.t.vid, getplaytime: () => self.t.done / self.sr };
      this.ready = Promise.resolve(ready).then(() => this._start()).catch(e => this._fail(e));
    }
    async _start() {
      const n = this.node = new g.AudioWorkletNode(this.ctx, 'jssida', { numberOfInputs: 0, numberOfOutputs: 1, outputChannelCount: [1] });
      n.port.onmessage = e => this._msg(e.data);
      n.onprocessorerror = () => this._fail(new Error('the analyzer processor stopped'));
      n.connect(this.gain);
    }
    _fail(e) { this.error = e; this.status = 'failed'; if (this.onfail) this.onfail(e); }
    _post(m) { if (this.node) this.node.port.postMessage(m); }
    _killWorker() { if (this.worker) { this.worker.terminate(); this.worker = null; } }
    _reset() {
      this._killWorker(); this.queue.length = 0; this.cks.clear(); this.maxk = 0; this.want = null; this.paused = null; this.map = null; this.holdTo = null;
      this.loaded = false; this.locked = false; this.status = 'loading';
    }
    // buf: ArrayBuffer of the .sid; o: {sub (0 based), model: 6581 | 8580 | 'auto', video: 'auto' | 'pal' | 'ntsc', length: seconds of the WAV}
    load(buf, o) {
      const gen = ++this.gen; this._reset(); this.opts = o; this.bytes = buf;
      this.ready.then(() => { if (gen === this.gen && this.node) this._post({ n: 'load', gen, buf: buf.slice(0), sub: o.sub, model: o.model, video: o.video }); });
    }
    _msg(m) {
      if (m.t === 'loaded') {
        if (m.gen !== this.gen) return;
        this.loaded = true; this.tp1 = m.tp1; this.info = m; this.t.vid = m.vid; this.t.model = m.model; this.status = 'loaded';
        const o = this.opts;
        try {                                                     // checkpoints: every CK_STEP seconds of the tune, in a Web Worker
          this.worker = new g.Worker('sidck.js');
          this.worker.onmessage = e => this._wmsg(e.data);
          this.worker.onerror = () => { this.workerOk = false; this._killWorker(); };
          this.worker.postMessage({ n: 'build', gen: this.gen, buf: this.bytes.slice(0), sub: o.sub, model: m.model, video: o.video, sr: this.sr, step: CK_STEP, max: o.length || 180 });
        } catch (e) { this.workerOk = false; }
        if (this.holdTo !== null) { const p = this.holdTo; this.holdTo = null; this.hold(p); }
        else if (this.want) this._send();
      } else if (m.t === 'paused') { if (m.gen === this.gen) this.paused = { done: m.done }; }
      else if (m.t === 'tm') { if (m.gen === this.gen) { this.queue.push(m); if (this.queue.length > 900) this.queue.splice(0, this.queue.length - 600); } }
    }
    _wmsg(m) {
      if (m.gen !== this.gen) return;
      if (m.t === 'ck') { this.cks.set(m.k, m.st); if (m.k === this.maxk + 1) { this.maxk = m.k; while (this.cks.has(this.maxk + 1)) this.maxk++; } }
    }
    // the state to restore for a start at analyzer time a (s): a checkpoint at or before it, the state after init, or null (go on from where
    // the analyzer is: it was paused near enough)
    _restoreFor(a) {
      const sr = this.sr;
      if (this.paused && Math.abs(this.paused.done / sr - a) <= 0.1) { this.paused = null; return null; }
      this.paused = null;
      if (a <= 0) return { done: 0 };
      // a checkpoint up to 0.1 s AFTER the point is fine too: the analyzer waits for the clock (a seek to 30.0 s needs the checkpoint of 30 s, not a
      // 10 s fast-forward from 20 s)
      const k = Math.min(Math.floor((a + 0.1) / CK_STEP), this.maxk);
      return k > 0 ? { done: k * CK_STEP * sr, st: this.cks.get(k) } : { done: 0 };
    }
    // the WAV starts at context time startT from offset off (s); the analyzer is brought to the same point and follows the clock
    play(startT, off) {
      this.want = { startT, off }; this.holdTo = null;
      if (this.loaded) this._send();
    }
    _send() {
      const w = this.want, sr = this.sr, startF = Math.round(w.startT * sr), armF = startF - Math.round(w.off * sr) + Math.round(this.tp1 * sr);
      this.map = { armF, startF }; this.locked = false; this.status = 'locking'; this.queue.length = 0;
      this._post({ n: 'arm', armF, startF, restore: this._restoreFor(w.off - this.tp1) });
    }
    // while paused: bring the analyzer to WAV position pos (s) and wait there (the registers shown are those of that moment)
    hold(pos) {
      this.want = null; this.queue.length = 0;
      if (!this.loaded) { this.holdTo = pos; return; }
      const a = pos - this.tp1, sr = this.sr, restore = this._restoreFor(a);
      this.locked = false; this.status = 'locking';
      this._post({ n: 'goto', restore, to: Math.round(Math.max(0, a) * sr) });
    }
    pause() { this.want = null; this.holdTo = null; this._post({ n: 'pause' }); this.queue.length = 0; this.status = 'paused'; }
    stop() { this.pause(); this.paused = null; }
    call(m, ...a) { this._post({ n: 'call', m, a }); }
    // A/B: the analyzer audible (target = the volume) or silent, a 10 ms crossfade
    setAudible(on, vol) { fade(this.ctx, this.gain.gain, on ? vol : 0); }
    // the output latency: the time of the context frame being output now
    audibleNow() {
      const c = this.ctx, ts = c.getOutputTimestamp ? c.getOutputTimestamp() : null;
      if (ts && ts.contextTime > 0 && ts.performanceTime > 0) return ts.contextTime + (performance.now() - ts.performanceTime) / 1000;
      return c.currentTime - (c.outputLatency || 0) - (c.baseLatency || 0);
    }
    // hands the panels the telemetry whose sound is being output by now (scope samples too), and checks the lock
    pump() {
      const aud = this.audibleNow(), sr = this.sr;
      while (this.queue.length && this.queue[0].f / sr <= aud) this._apply(this.queue.shift());
    }
    _apply(m) {
      if (m.mwg > this.maxGap) this.maxGap = m.mwg;
      if (m.mpr > this.maxProc) this.maxProc = m.mpr;
      this.locked = !!m.lock;
      if (m.lock) {
        const t = this.t; t.regs = m.regs; t.env = m.env; t.st = m.st; t.eff = m.eff; t.cpu = m.cpu; t.out = m.out; t.vid = m.vid; t.model = m.model; t.done = m.done;
        this.mem.set(m.regs, 0xD400); this.status = m.on ? 'locked' : 'held';
        if (m.sc && m.sc.n) this._push(m.sc);
        if (!m.on) this.paused = { done: m.done };
      }
      if (this.onapply) this.onapply(m);
      // re-lock: the analyzer's play time against the WAV position, both from the context clock; more than 20 ms apart: seek again
      if (m.lock && m.on && this.want && this.map && m.f > this.map.startF) {
        const w = this.want, exp = m.f / this.sr - (w.startT - w.off) - this.tp1;
        if (Math.abs(m.done / this.sr - exp) > 0.020) this.relock();
      }
    }
    relock() {
      if (!this.want) return;
      this.relocks++;
      const base = this.want.startT - this.want.off, T = this.ctx.currentTime + AN_PRE;
      this.play(T, T - base);
    }
    _push(sc) {                                                   // scope samples (as the worklet player does)
      const n = Math.min(sc.n, SCN), off = sc.n - n, S = SCN, dst = [this.sc.v[0], this.sc.v[1], this.sc.v[2], this.sc.m], src = [sc.v[0], sc.v[1], sc.v[2], sc.m];
      let p = this.sc.pos;
      for (let c = 0; c < 4; c++) { p = this.sc.pos; for (let i = 0; i < n; i++) { dst[c][p] = src[c][off + i]; if (++p === S) p = 0; } }
      this.sc.pos = p;
    }
    statusText() {
      const k = this.maxk, tot = this.opts ? Math.floor((this.opts.length || 180) / CK_STEP) : 0;
      return 'analyzer: ' + ({ loading: 'loading…', loaded: 'ready', locking: 'locking…', locked: 'locked', held: 'held', paused: 'paused', idle: 'idle', failed: 'failed' }[this.status] || this.status) +
        (this.loaded ? ' · checkpoints ' + k + '/' + tot : '') + (this.relocks ? ' · ' + this.relocks + ' re-lock' + (this.relocks > 1 ? 's' : '') : '');
    }
  }
  function fade(ctx, param, v) {                                  // 10 ms linear ramp to v, from the value now
    const t = ctx.currentTime; param.cancelScheduledValues(t); param.setValueAtTime(param.value, t); param.linearRampToValueAtTime(v, t + 0.010);
  }

  // opts: {engine: 'auto' | 'script' (force the ScriptProcessor engine), bgnoi}
  function create(opts) {
    opts = opts || {};
    if (opts.engine !== 'script' && workletOk()) return new WorkletPlayer(opts);
    const p = new g.jsSID(16384, opts.bgnoi === undefined ? 0.0005 : opts.bgnoi);
    p.engine = 'script';
    return p;
  }
  function offlineOk() { return workletOk() && typeof g.OfflineAudioContext !== 'undefined'; }

  // o: {buf: ArrayBuffer of the .sid, sub: subtune (0 based), seconds, sr: sample rate, cmds: [{n, a}] jsSID calls (setmodel, setvolume,
  // setfilter, setmute, setoverride, setvideo), bgnoi, build(ctx, node): connects the node (default: to the destination),
  // onprogress(fraction)}. Returns {samples: Float32Array (mono), sr, took: seconds of real time}
  async function renderOffline(o) {
    const sr = o.sr, frames = Math.max(128, Math.round(o.seconds * sr));
    const ctx = new g.OfflineAudioContext(1, frames, sr);
    await ctx.audioWorklet.addModule(MODULE);
    const cmds = (o.cmds || []).concat([{ n: 'loadinit', a: [o.buf, o.sub], play: true }]);
    const node = new g.AudioWorkletNode(ctx, 'jssid', { numberOfInputs: 0, numberOfOutputs: 1, outputChannelCount: [1],
      processorOptions: { bgnoi: o.bgnoi === undefined ? 0.0005 : o.bgnoi, offline: true, cmds } });
    if (o.build) o.build(ctx, node); else node.connect(ctx.destination);
    if (o.onprogress) {                                            // suspend / resume at about 5% steps: the progress, no cost worth measuring
      let last = 0;
      for (let k = 1; k < 20; k++) {
        const q = Math.floor(frames * k / 20 / 128) * 128; if (q <= last || q >= frames) continue; last = q;
        ctx.suspend(q / sr).then(() => { o.onprogress(q / frames); ctx.resume(); });
      }
    }
    const t0 = performance.now(), buffer = await ctx.startRendering();
    return { samples: buffer.getChannelData(0), sr, took: (performance.now() - t0) / 1000 };
  }
  g.SIDEngine = { create, workletOk, offlineOk, renderOffline, WorkletPlayer, Analyzer, fade, analyzerOk: workletOk, MODULE, SCN };
})(window);
