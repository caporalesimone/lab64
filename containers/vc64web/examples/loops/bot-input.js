// Bot for the determinism test (API 24): it uses ALL the input kinds (held joystick, joystick with duration,
// held key, key with duration) and keeps the host CPU busy 0-13 ms per step, to provoke browser delays.
// The target (shell/11-determinism.sh) is a program at $C000 that reads $DC00 without pause and builds a histogram at $C100,
// plus the KERNAL keyboard buffer: an input lost or moved by one frame changes the RAM and so the hash.
const t = performance.now(), d = (i * 7919) % 14;
while (performance.now() - t < d) {}
const D = ['up', 'down', 'left', 'right', 'fire'], st = {};
D.forEach((x, k) => st[x] = ((i >> k) & 1) === 1 && !(x === 'down' && (i & 1)));
c64.joy(2, st);
if (i % 7 === 0) c64.keyDown('a');
if (i % 7 === 3) c64.keyUp('a');
if (i % 11 === 0) c64.type('s', { frames: 5 });
if (i % 13 === 5) c64.joy(1, { fire: true }, 3);
