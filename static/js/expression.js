// VRM facial expression state and smooth transitions.
// Called by websocket.js on incoming expression actions,
// and updated each frame from app.js.

let currentExpression = null;
let expressionValue = 0;
const FADE_IN_SPEED = 5.0;
const FADE_OUT_SPEED = 2.0;
const HOLD_DURATION = 4.0;
let holdTimer = 0;
let phase = "idle"; // "fadein" | "hold" | "fadeout" | "idle"

let vrm = null;

function setVRM(v) {
  vrm = v;
}

function setExpression(name) {
  if (currentExpression && currentExpression !== name && vrm?.expressionManager) {
    vrm.expressionManager.setValue(currentExpression, 0);
  }
  currentExpression = name;
  expressionValue = 0;
  holdTimer = 0;
  phase = "fadein";
}

function updateExpression(delta) {
  if (!vrm?.expressionManager || !currentExpression || phase === "idle") return;

  if (phase === "fadein") {
    expressionValue = Math.min(1, expressionValue + delta * FADE_IN_SPEED);
    if (expressionValue >= 1) {
      expressionValue = 1;
      phase = "hold";
      holdTimer = 0;
    }
  } else if (phase === "hold") {
    holdTimer += delta;
    if (holdTimer >= HOLD_DURATION) {
      phase = "fadeout";
    }
  } else if (phase === "fadeout") {
    expressionValue = Math.max(0, expressionValue - delta * FADE_OUT_SPEED);
    if (expressionValue <= 0) {
      expressionValue = 0;
      phase = "idle";
      vrm.expressionManager.setValue(currentExpression, 0);
      currentExpression = null;
      return;
    }
  }

  vrm.expressionManager.setValue(currentExpression, expressionValue);
}

export { setVRM, setExpression, updateExpression };
