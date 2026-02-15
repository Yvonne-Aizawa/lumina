import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { VRMLoaderPlugin } from "@pixiv/three-vrm";

import { scene, camera, renderer, controls } from "./scene.js";
import {
  ensureAnimation,
  playAnimationByName,
  setMixer,
  setVRM,
} from "./animations.js";
import { connectWebSocket } from "./websocket.js";
import { initChat } from "./chat.js";
import { initSettings } from "./settings.js";
import { initWakeWord } from "./wakeword.js";
import { checkAuth, initAuth } from "./auth.js";

let mixer = null;
let currentVRM = null;

// Init auth and gate app startup
initAuth();
const authed = await checkAuth();

// Load VRM
const loader = new GLTFLoader();
loader.register((parser) => new VRMLoaderPlugin(parser));

if (!authed) {
  // Still start the render loop but don't load anything
  const clock = new THREE.Clock();
  function animate() {
    requestAnimationFrame(animate);
    renderer.render(scene, camera);
  }
  animate();
  // Re-check after login (page reloads on successful login)
} else {
  loader.load(
    "./avatar.vrm",
    async (gltf) => {
      const vrm = gltf.userData.vrm;
      currentVRM = vrm;
      scene.add(vrm.scene);

      mixer = new THREE.AnimationMixer(vrm.scene);
      setMixer(mixer);
      setVRM(vrm);

      // Preload Idle animation, others load on demand
      const idleClip = await ensureAnimation("Idle");
      if (idleClip) {
        playAnimationByName("Idle");
      }
      console.log("Ready — animations load on demand");

      connectWebSocket();
    },
    undefined,
    (error) => {
      console.error("Error loading VRM:", error);
    },
  );

  // Init UI
  initChat();
  initSettings();

  // Init wake word (async, non-blocking)
  initWakeWord().catch((e) => console.warn("Wake word init failed:", e));
} // end auth gate

// Resize handler
window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

// Random blink state
let blinkTime = 0;
let nextBlinkAt = 2 + Math.random() * 4; // seconds until next blink
const BLINK_DURATION = 0.12; // seconds eyes stay closed

// Animation loop
const clock = new THREE.Clock();
function animate() {
  requestAnimationFrame(animate);
  const delta = clock.getDelta();
  if (mixer) mixer.update(delta);

  // Random blinking
  if (currentVRM?.expressionManager) {
    blinkTime += delta;
    if (blinkTime >= nextBlinkAt + BLINK_DURATION) {
      // Blink finished, open eyes and schedule next
      currentVRM.expressionManager.setValue("blink", 0);
      blinkTime = 0;
      nextBlinkAt = 2 + Math.random() * 4;
    } else if (blinkTime >= nextBlinkAt) {
      // Blink in progress, close eyes
      currentVRM.expressionManager.setValue("blink", 1);
    }
  }

  if (currentVRM) currentVRM.update(delta);
  controls.update();
  renderer.render(scene, camera);
}
animate();
