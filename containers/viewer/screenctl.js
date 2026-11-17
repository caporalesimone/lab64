// Turns the remote screen of the viewer on or off from inside the container (1.12): used by the host command "lab64 screen on|off|status"
// through docker exec. Copyright (c) 2026 - Simone Caporale
'use strict';
const arg = process.argv[2];
if (!['on', 'off', 'status'].includes(arg)) { console.error('usage: screenctl.js on|off|status'); process.exit(2); }
const headers = { 'Content-Type': 'application/json' };
if (process.env.VIEW_PASSWORD) headers.Authorization = 'Basic ' + Buffer.from('viewer:' + process.env.VIEW_PASSWORD).toString('base64');
const opt = arg === 'status' ? { headers } : { method: 'POST', headers, body: JSON.stringify({ on: arg === 'on' }) };
// (1.14) retried for ~5 s: right after "lab64 view" the server may not listen yet
const go = n => fetch('http://localhost:6080/screen', opt).then(r => r.json()).then(j => { console.log(j.on ? 'on' : 'off'); process.exit(j.ok ? 0 : 1); })
  .catch(e => { if (n > 0) setTimeout(() => go(n - 1), 300); else { console.error('screenctl: ' + e.message); process.exit(1); } });
go(16);
