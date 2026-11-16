// Control loop for  c64 runLoop "$(cat loops/bot-joy.js)" '{"frames":300,"every":2}'
// Function body with parameters (c64, i, state). return false = end.
// Inside runLoop joy(port,state,frames) presses and releases without advancing time (API 18).
c64.joy(2, { right: (i % 8) < 4, fire: (i % 2) === 0 }, 2);
state.steps = (state.steps || 0) + 1;
if (i >= 100) return false;
