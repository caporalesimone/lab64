// lab64-viewer server (13/11). Copyright (c) 2026 - Simone Caporale
// ONE port (6080, published on localhost only):
//   /            index page (www/index.html), /live.html live screen with audio, /config.js proposed disk, project name, player
//   /vnc/        KasmVNC web client (files of the official package)
//   /websockify  WebSocket to Xvnc (127.0.0.1:6901, not published): bytes passed through as they are
//   /audio       WebSocket with the screen audio: PulseAudio (monitor of the "c64" card), PCM s16le stereo 44100 Hz
//   /input       WebSocket of the overlay keys (C64 keyboard, joysticks) of live.html: text "d <keysym>", "u <keysym>", "f"
//                (= pointer to the screen center: with no window manager the keys go to the window under the pointer)
//   /out/        the project out/ folder, read-only (mounted at /srv/out), with folder listings
//   /control     (14/11) POST JSON {"cmd":"status"|"play"|"basic"|"stop","disk":"releases/v<V>/<file>.d64"}: VICE on the live
//                screen, forwarded to the player (containers/tools/py/viewer_player.py, container lab64-player) through the Unix socket in lab64-x11
//   /screen      (1.12) GET -> {"ok":true,"on":bool}; POST JSON {"on":true|false}: turns the remote screen (Xvnc :99) on or off. OFF at start
//                (VIEW_SCREEN=on starts it with the viewer): with it off nothing draws, encodes or streams the screen, and /websockify, /input
//                answer 503. Same Host / same-origin / JSON-only / password rules as /control
//   /render      (1.8) POST JSON {"src": "releases/v1/x.sid" | "sid_b64": "<base64 of a .sid>", "params": {...}}: SID Studio renders a
//                tune with sidplayfp in the player container (containers/tools/py/sidrender.py) -> {"ok":true,"file":"cache/sidrender/<sha>.wav",
//                "seconds","took","cached","params","tune"}; the WAV is then fetched from /out/cache/sidrender/<sha>.wav. Same
//                Host / same-origin / JSON-only / password rules as /control; body at most 160 KB (413), answers 400 invalid,
//                429 busy (one render at a time), 500 failed, 503 player not running, 504 timeout
// VIEW_PASSWORD (optional, none by default): HTTP Basic authentication on EVERYTHING (pages, out/, screen, audio).
// Protections (14/11): Host must be localhost/127.0.0.1/[::1] (or in VIEW_HOSTS, comma separated) against DNS rebinding;
// WebSockets and /control accept only same-origin requests (another site open in the browser cannot drive the viewer);
// /control wants Content-Type application/json (a form of another site cannot send it without a preflight, never granted here).
'use strict';
const http = require('http'), fs = require('fs'), path = require('path'), net = require('net');
const { spawn } = require('child_process');
const { WebSocketServer, WebSocket } = require('ws');
const PulseAudio = require('pulseaudio2');

const PORT = 6080, VNC_PORT = 6901, PASS = process.env.VIEW_PASSWORD || '';
const DISK = (process.env.VIEW_DISK || '').replace(/["\\]/g, '');
const PLAYER = JSON.stringify((process.env.VIEW_PLAYER || '').slice(0, 200)).replace(/</g, '\\u003c');   // player command (for the page)
const TITLE = JSON.stringify((process.env.VIEW_TITLE || '').slice(0, 80)).replace(/</g, '\\u003c');   // project name in the page
const PLAYER_SOCK = '/tmp/.X11-unix/lab64-player.sock';
const HOSTS = new Set(['localhost', '127.0.0.1', '[::1]', ...(process.env.VIEW_HOSTS || '').split(',').map(s => s.trim().toLowerCase()).filter(Boolean)]);
function hostOk(req) {                                          // Host name without the port
  const h = String(req.headers.host || '').toLowerCase().replace(/:\d+$/, '');
  return HOSTS.has(h);
}
function sameOrigin(req) {                                      // no Origin (curl, local scripts) or equal to the Host
  const o = req.headers.origin;
  if (!o) return true;
  try { return new URL(o).host === req.headers.host; } catch (e) { return false; }
}
// --- the remote screen (1.12): Xvnc :99 is a child of this process, started on request. Local clients without X authorization (-ac),
// no TCP for X, WebSocket on 127.0.0.1:6901 (not published). -PublicIP: without it Xvnc 1.5 queries STUN servers on the Internet.
const X_SOCK = '/tmp/.X11-unix/X99';
const GEOM = String(process.env.VIEW_SIZE || '1280x1000').split('x').slice(0, 2).join('x');
let xvnc = null, xstarting = null;
const screenOn = () => xvnc !== null && fs.existsSync(X_SOCK);
function vncUp() { return new Promise(r => { const c = net.connect(VNC_PORT, '127.0.0.1', () => { c.destroy(); r(true); }); c.on('error', () => r(false)); }); }
function startScreen() {
  if (xstarting) return xstarting;
  if (screenOn()) return Promise.resolve(true);
  xstarting = (async () => {
    for (const f of ['/tmp/.X99-lock', X_SOCK]) { try { fs.unlinkSync(f); } catch (e) { /* not there */ } }
    const log = fs.openSync('/tmp/xvnc.log', 'a');
    const p = spawn('Xvnc', [':99', '-geometry', GEOM, '-depth', '24', '-ac', '-nolisten', 'tcp', '-extension', 'MIT-SHM', '-PublicIP', '127.0.0.1',
      '-websocketPort', String(VNC_PORT), '-interface', '127.0.0.1', '-disableBasicAuth', '-SecurityTypes', 'None', '-sslOnly', '0', '-AlwaysShared',
      '-httpd', '/usr/share/kasmvnc/www', '-RectThreads', '0', '-Log', '*:stderr:30'], { stdio: ['ignore', log, log] });
    xvnc = p;
    p.on('exit', () => { if (xvnc === p) xvnc = null; for (const f of ['/tmp/.X99-lock', X_SOCK]) { try { fs.unlinkSync(f); } catch (e) { /* gone */ } } });
    for (let i = 0; i < 100 && xvnc === p; i++) {
      if (fs.existsSync(X_SOCK) && await vncUp()) { try { fs.chmodSync(X_SOCK, 0o777); } catch (e) { /* ignore */ } return true; }
      await new Promise(r => setTimeout(r, 100));
    }
    return screenOn();
  })().finally(() => { xstarting = null; });
  return xstarting;
}
function stopScreen() {
  return new Promise(resolve => {
    if (!xvnc) return resolve();
    const p = xvnc; p.once('exit', () => resolve()); p.kill('SIGTERM');
    setTimeout(() => { try { p.kill('SIGKILL'); } catch (e) { /* gone */ } }, 3000);
  });
}
function screenApi(req, res) {
  const send = (code, o) => { res.statusCode = code; res.setHeader('Content-Type', 'application/json'); res.setHeader('Cache-Control', 'no-store'); res.end(JSON.stringify(o)); };
  if (req.method === 'GET') return send(200, { ok: true, on: screenOn() });
  if (req.method !== 'POST') return send(405, { ok: false, error: 'GET or POST only' });
  if (!sameOrigin(req)) return send(403, { ok: false, error: 'different origin' });
  if (!String(req.headers['content-type'] || '').startsWith('application/json')) return send(415, { ok: false, error: 'application/json required' });
  let body = '';
  req.on('data', d => { body += d; if (body.length > 256) req.destroy(); });
  req.on('end', async () => {
    let q;
    try { q = JSON.parse(body); } catch (e) { return send(400, { ok: false, error: 'invalid JSON' }); }
    if (typeof q.on !== 'boolean') return send(400, { ok: false, error: '"on" must be true or false' });
    if (q.on) { const ok = await startScreen(); return send(ok ? 200 : 500, { ok, on: screenOn(), error: ok ? undefined : 'Xvnc did not start (see /tmp/xvnc.log in the viewer container)' }); }
    await stopScreen(); send(200, { ok: true, on: screenOn() });
  });
}
function control(req, res) {
  const fail = (code, msg) => { res.statusCode = code; res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ ok: false, error: msg })); };
  if (req.method !== 'POST') return fail(405, 'POST only');
  if (!sameOrigin(req)) return fail(403, 'different origin');
  if (!String(req.headers['content-type'] || '').startsWith('application/json')) return fail(415, 'application/json required');
  let body = '';
  req.on('data', d => { body += d; if (body.length > 2048) req.destroy(); });
  req.on('end', () => {
    let q;
    try { q = JSON.parse(body); } catch (e) { return fail(400, 'invalid JSON'); }
    const line = JSON.stringify({ cmd: String(q.cmd || ''), disk: q.disk === undefined ? undefined : String(q.disk) }) + '\n';
    const c = net.connect(PLAYER_SOCK);
    let out = '', done = false;
    const finish = (code, txt) => { if (done) return; done = true; res.statusCode = code; res.setHeader('Content-Type', 'application/json'); res.setHeader('Cache-Control', 'no-store'); res.end(txt); };
    c.setTimeout(8000, () => { c.destroy(); finish(504, JSON.stringify({ ok: false, error: 'the player does not answer' })); });
    c.on('connect', () => c.write(line));
    c.on('data', d => { out += d; });
    c.on('end', () => finish(200, out.trim() || JSON.stringify({ ok: false, error: 'empty answer' })));
    c.on('error', () => finish(503, JSON.stringify({ ok: false, error: 'player not running (lab64 stop, then lab64 view)' })));
  });
}
// (1.8) /render: the same protections as /control, a larger body (a .sid of 65 KB in base64 is about 88 KB), a long timeout (a render
// takes seconds to minutes). The server forwards only the three fields it knows; the player checks everything again.
const RENDER_BODY = 160000, RENDER_WAIT = 330000, RENDER_CODES = { invalid: 400, busy: 429, failed: 500 };
function render(req, res) {
  let done = false;
  const reply = (code, obj) => {
    if (done) return; done = true;
    res.statusCode = code; res.setHeader('Content-Type', 'application/json'); res.setHeader('Cache-Control', 'no-store');
    res.end(JSON.stringify(obj));
  };
  const fail = (code, msg) => reply(code, { ok: false, error: msg });
  if (req.method !== 'POST') return fail(405, 'POST only');
  if (!sameOrigin(req)) return fail(403, 'different origin');
  if (!String(req.headers['content-type'] || '').startsWith('application/json')) return fail(415, 'application/json required');
  if (Number(req.headers['content-length'] || 0) > RENDER_BODY) return fail(413, 'request too large');
  const chunks = []; let size = 0;
  req.on('data', d => {
    size += d.length;
    if (size > RENDER_BODY) { fail(413, 'request too large'); req.destroy(); return; }
    chunks.push(d);
  });
  req.on('end', () => {
    if (done) return;
    let q;
    try { q = JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch (e) { return fail(400, 'invalid JSON'); }
    if (!q || typeof q !== 'object' || Array.isArray(q)) return fail(400, 'invalid request');
    if ((q.src === undefined) === (q.sid_b64 === undefined)) return fail(400, 'give src or sid_b64');
    if (q.src !== undefined && (typeof q.src !== 'string' || !/^[A-Za-z0-9._-][A-Za-z0-9._\/-]{0,199}\.sid$/i.test(q.src) || q.src.split('/').includes('..'))) return fail(400, 'invalid src');
    if (q.sid_b64 !== undefined && (typeof q.sid_b64 !== 'string' || q.sid_b64.length > 90000)) return fail(413, 'the .sid is too large');
    if (q.params !== undefined && (q.params === null || typeof q.params !== 'object' || Array.isArray(q.params))) return fail(400, 'params must be an object');
    const line = JSON.stringify({ cmd: 'render', src: q.src, sid_b64: q.sid_b64, params: q.params }) + '\n';
    const c = net.connect(PLAYER_SOCK);
    let out = '';
    c.setTimeout(RENDER_WAIT, () => { c.destroy(); fail(504, 'the render took too long'); });
    c.on('connect', () => c.write(line));
    c.on('data', d => { out += d; });
    c.on('end', () => {
      let a;
      try { a = JSON.parse(out.trim()); } catch (e) { return fail(502, 'invalid answer of the player'); }
      reply(a && a.ok ? 200 : (a && RENDER_CODES[a.code]) || 500, a);
    });
    c.on('error', () => fail(503, 'player not running (lab64 stop, then lab64 view)'));
  });
}
// (1.10) the portable vc64web page(s) live in the lab64-vc64web image (c64d: GET /pages/); the viewer only shows them, through this
// proxy, so they stay on the viewer origin (the page loads disks from /out/ with fetch). Only that prefix, GET/HEAD, no other path of c64d.
const EMU = process.env.VIEW_EMU || 'http://lab64-vc64web:7064';
function emuPages(req, res, urlPath) {
  const name = urlPath.slice('/out/cache/vc64web/'.length);
  if (name !== '' && !/^VirtualC64-v\d+\.html$/.test(name)) { res.statusCode = 404; return res.end('not found'); }
  const u = new URL(EMU);
  const r = http.request({ host: u.hostname, port: u.port, path: '/pages/' + name, method: 'GET', timeout: 5000 }, up => {
    const h = { 'Content-Type': up.headers['content-type'] || 'text/html; charset=utf-8', 'Cache-Control': 'no-cache' };
    if (up.headers['content-length']) h['Content-Length'] = up.headers['content-length'];
    res.writeHead(up.statusCode, h);
    if (req.method === 'HEAD') { up.resume(); return res.end(); }
    up.pipe(res);
  });
  r.on('timeout', () => r.destroy());
  r.on('error', () => { if (res.headersSent) return res.destroy(); res.statusCode = 503; res.setHeader('Content-Type', 'text/plain'); res.end('vc64web not running (lab64 up vc64web)'); });
  r.end();
}
const ROOTS = [['/out/', '/srv/out', true], ['/vnc/', '/usr/share/kasmvnc/www', false], ['/', path.join(__dirname, 'www'), false]];
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.txt': 'text/plain; charset=utf-8',
  '.wasm': 'application/wasm', '.woff2': 'font/woff2', '.woff': 'font/woff', '.ttf': 'font/ttf', '.md': 'text/plain; charset=utf-8',
  '.sid': 'application/octet-stream', '.wav': 'audio/wav', '.mp3': 'audio/mpeg' };

function authorized(req) {
  if (!PASS) return true;
  const h = req.headers.authorization || '';
  if (!h.startsWith('Basic ')) return false;
  const s = Buffer.from(h.slice(6), 'base64').toString(), i = s.indexOf(':');
  return i >= 0 && s.slice(i + 1) === PASS;                       // any user, the password is what counts
}
const esc = s => s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function serveFile(req, res, file, st) {
  const lm = st.mtime.toUTCString();
  res.setHeader('Last-Modified', lm);
  res.setHeader('Cache-Control', 'no-cache');                    // the browser always asks whether the file changed (304)
  const ims = req.headers['if-modified-since'];
  if (ims && Math.floor(st.mtimeMs / 1000) <= Math.floor(Date.parse(ims) / 1000)) { res.statusCode = 304; return res.end(); }
  res.setHeader('Content-Type', MIME[path.extname(file).toLowerCase()] || 'application/octet-stream');
  res.setHeader('Content-Length', st.size);
  if (req.method === 'HEAD') return res.end();
  // (15/11) the page polls out/ while a build rewrites it: a file can vanish between stat and read. Without this handler the
  // stream error is thrown and node (the whole viewer) dies.
  const stream = fs.createReadStream(file);
  stream.on('error', () => {
    if (res.headersSent) return res.destroy();                    // half sent: the browser sees a broken transfer and asks again
    res.removeHeader('Content-Length'); res.removeHeader('Last-Modified');
    res.statusCode = 404; res.setHeader('Content-Type', 'text/plain'); res.end('not found');
  });
  stream.pipe(res);
}

function listing(res, dir, urlPath) {                           // HTML listing (read by the index page)
  let items;
  try {
    items = fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))
      .map(d => d.name + (d.isDirectory() ? '/' : ''));
  } catch (e) { res.statusCode = 404; return res.end('not found'); }   // folder removed meanwhile (build in progress)
  res.setHeader('Content-Type', 'text/html; charset=utf-8'); res.setHeader('Cache-Control', 'no-cache');
  res.end(`<!doctype html><meta charset="utf-8"><title>${esc(urlPath)}</title><h1>${esc(urlPath)}</h1><ul>` +
    items.map(n => `<li><a href="${encodeURIComponent(n.replace(/\/$/, '')) + (n.endsWith('/') ? '/' : '')}">${esc(n)}</a></li>`).join('') + '</ul>');
}

const server = http.createServer((req, res) => {
  if (!hostOk(req)) { res.statusCode = 421; return res.end('Host not allowed (VIEW_HOSTS)'); }
  if (!authorized(req)) { res.statusCode = 401; res.setHeader('WWW-Authenticate', 'Basic realm="c64 viewer"'); return res.end(); }
  let urlPath;
  try { urlPath = decodeURIComponent(new URL(req.url, 'http://x').pathname); } catch (e) { res.statusCode = 400; return res.end(); }
  if (urlPath === '/config.js') {
    res.setHeader('Content-Type', 'text/javascript'); res.setHeader('Cache-Control', 'no-cache');
    return res.end(`window.VIEW_DISK = "${DISK}";\nwindow.VIEW_TITLE = ${TITLE};\nwindow.VIEW_PLAYER = ${PLAYER};\n`);
  }
  if (urlPath === '/control') return control(req, res);
  if (urlPath === '/screen') return screenApi(req, res);
  if (urlPath === '/render') return render(req, res);
  if (urlPath === '/out') { res.statusCode = 301; res.setHeader('Location', '/out/'); return res.end(); }
  if ((req.method === 'GET' || req.method === 'HEAD') && (urlPath === '/out/cache/vc64web/' || urlPath.startsWith('/out/cache/vc64web/'))) return emuPages(req, res, urlPath);
  const [prefix, root, list] = ROOTS.find(([p]) => urlPath.startsWith(p));
  const file = path.normalize(path.join(root, urlPath.slice(prefix.length)));
  if (file !== root && !file.startsWith(root + path.sep)) { res.statusCode = 403; return res.end(); }   // no ../
  fs.stat(file, (err, st) => {
    if (err) { res.statusCode = 404; return res.end('not found'); }
    if (!st.isDirectory() && !st.isFile()) { res.statusCode = 404; return res.end('not found'); }   // sockets, FIFOs
    if (st.isDirectory()) {
      const idx = path.join(file, 'index.html');
      let ist = null;
      try { ist = fs.statSync(idx); } catch (e) { /* no index.html (or removed meanwhile) */ }
      if (ist && ist.isFile()) return serveFile(req, res, idx, ist);
      if (list) return listing(res, file, urlPath);
      res.statusCode = 404; return res.end();
    }
    serveFile(req, res, file, st);
  });
});

// --- audio: one PulseAudio record stream, open while there is at least one listener
const wss = new WebSocketServer({ noServer: true });
const pulse = new PulseAudio();
let pulseOk = true, rec = null;
pulse.on('error', e => { pulseOk = false; console.log('audio not available:', e && e.message); });
function startRec() {
  if (rec || !pulseOk) return;
  rec = pulse.createRecordStream({ device: 'c64.monitor', channels: 2, rate: 44100, format: 'S16LE' });
  rec.on('connection', () => rec.on('data', chunk => { for (const c of wss.clients) if (c.readyState === 1) c.send(chunk); }));
}
function stopRec() { if (rec && wss.clients.size === 0) { try { rec.end(); } catch (e) { /* already closed */ } rec = null; } }
wss.on('connection', ws => { startRec(); ws.on('close', () => setTimeout(stopRec, 100)); });

// --- /input: keys injected into Xvnc as a second RFB client (KeyEvent and PointerEvent only; the image is never requested).
// Every /input connection opens its own RFB client (so the screen size is the current one) and at the end releases the keys still down.
const inWss = new WebSocketServer({ noServer: true });
inWss.on('connection', ws => {
  const down = new Set(), pending = [];
  let st = 0, buf = Buffer.alloc(0), w = 1280, h = 1000, ready = false;
  const up = new WebSocket(`ws://127.0.0.1:${VNC_PORT}/websockify`, ['binary'], { headers: { Origin: `http://127.0.0.1:${VNC_PORT}` } });   // without Origin Xvnc answers 404
  const key = (sym, d) => { const m = Buffer.alloc(8); m[0] = 4; m[1] = d; m.writeUInt32BE(sym >>> 0, 4); up.send(m); };
  const ptr = (x, y) => { const m = Buffer.alloc(11); m[0] = 5; m.writeUInt16BE(x, 3); m.writeUInt16BE(y, 5); up.send(m); };   // KasmVNC: 5, u16 mask, x, y, x and y scroll (s16): 11 bytes, not 6 as in standard RFB
  const run = c => {
    const [op, a] = c.split(' '), sym = parseInt(a, 10);
    if (op === 'f') ptr(w >> 1, h >> 1);
    else if ((op === 'd' || op === 'u') && Number.isInteger(sym)) {
      if (op === 'd') down.add(sym); else down.delete(sym);
      key(sym, op === 'd' ? 1 : 0);
    }
  };
  function step() {                                            // RFB 3.8 handshake with no security
    for (;;) {
      if (st === 0) { if (buf.length < 12) return; buf = buf.subarray(12); up.send(Buffer.from('RFB 003.008\n')); st = 1; }
      else if (st === 1) {
        if (!buf.length || buf.length < 1 + buf[0]) return;
        const types = [...buf.subarray(1, 1 + buf[0])]; buf = buf.subarray(1 + buf[0]);
        if (!types.includes(1)) { up.close(); return; }
        up.send(Buffer.from([1])); st = 2;
      } else if (st === 2) { if (buf.length < 4) return; if (buf.readUInt32BE(0) !== 0) { up.close(); return; } buf = buf.subarray(4); up.send(Buffer.from([1])); st = 3; }
      else if (st === 3) {
        if (buf.length < 24 || buf.length < 24 + buf.readUInt32BE(20)) return;
        w = buf.readUInt16BE(0); h = buf.readUInt16BE(2); buf = Buffer.alloc(0); st = 4;
        ready = true; for (const c of pending.splice(0)) run(c);
      } else { buf = Buffer.alloc(0); return; }
    }
  }
  up.on('message', d => { if (st < 4) { buf = Buffer.concat([buf, d]); step(); } });
  up.on('error', () => ws.close()); up.on('close', () => ws.close());
  ws.on('message', m => { const c = String(m).slice(0, 40); if (ready) run(c); else if (pending.length < 100) pending.push(c); });
  ws.on('close', () => { if (ready && up.readyState === 1) for (const s of down) key(s, 0); up.close(); });
  ws.on('error', () => ws.close());
});

// --- WebSocket: /audio and /input here, everything else (KasmVNC client) goes to Xvnc as is
server.on('upgrade', (req, sock, head) => {
  if (!hostOk(req) || !sameOrigin(req)) { sock.end('HTTP/1.1 403 Forbidden\r\n\r\n'); return; }
  if (!authorized(req)) { sock.end('HTTP/1.1 401 Unauthorized\r\n\r\n'); return; }
  if (!req.url.startsWith('/audio') && !screenOn()) { sock.end('HTTP/1.1 503 Service Unavailable\r\n\r\n'); return; }   // remote screen off
  if (req.url.startsWith('/input')) { inWss.handleUpgrade(req, sock, head, ws => inWss.emit('connection', ws, req)); return; }
  if (req.url.startsWith('/audio')) { wss.handleUpgrade(req, sock, head, ws => wss.emit('connection', ws, req)); return; }
  const up = net.connect(VNC_PORT, '127.0.0.1', () => {
    let h = `${req.method} ${req.url} HTTP/${req.httpVersion}\r\n`;
    for (let i = 0; i < req.rawHeaders.length; i += 2) {
      if (req.rawHeaders[i].toLowerCase() === 'authorization') continue;      // Xvnc does not use the authentication: it stays with the viewer
      h += `${req.rawHeaders[i]}: ${req.rawHeaders[i + 1]}\r\n`;
    }
    up.write(h + '\r\n'); if (head && head.length) up.write(head);
    sock.pipe(up).pipe(sock);
  });
  up.on('error', () => sock.destroy()); sock.on('error', () => up.destroy());
});

if (process.env.VIEW_SCREEN === 'on') startScreen();
server.listen(PORT, () => console.log(`viewer ready: http://localhost:${PORT}` + (PASS ? ' (password)' : '')));
