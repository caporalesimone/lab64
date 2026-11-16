// Increments a byte in memory at every step and stops when it reaches 5:  c64 runLoop "$(cat loops/count-memory.js)"
// (at every step the loop advances 'every' frames; 'state' persists between steps and is returned)
if (i === 0) c64.poke(0xC000, 0);
const v = c64.peek(0xC000);
state.seen = (state.seen || []).concat(v);
if (v >= 5) return false;
c64.poke(0xC000, v + 1);
