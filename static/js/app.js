import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { VRMLoaderPlugin } from "@pixiv/three-vrm";

import { scene, camera, renderer, controls } from "./scene.js";
import {
  animationClips,
  loadMixamoAnimation,
  playAnimationByName,
  setMixer,
} from "./animations.js";
import { connectWebSocket } from "./websocket.js";
import { initChat } from "./chat.js";
import { initWakeWord } from "./wakeword.js";

let mixer = null;
let currentVRM = null;

// Load VRM
const loader = new GLTFLoader();
loader.register((parser) => new VRMLoaderPlugin(parser));

loader.load(
  "./avatar.vrm",
  async (gltf) => {
    const vrm = gltf.userData.vrm;
    currentVRM = vrm;
    scene.add(vrm.scene);

    mixer = new THREE.AnimationMixer(vrm.scene);
    setMixer(mixer);

    // Fetch animation list from server and preload all
    try {
      const res = await fetch("/api/animations");
      const data = await res.json();
      const animNames = data.animations || [];

      for (const name of animNames) {
        try {
          const url = `./anims/${encodeURIComponent(name)}.fbx`;
          const clip = await loadMixamoAnimation(url, vrm);
          animationClips[name] = clip;
          console.log("Loaded animation:", name);
        } catch (e) {
          console.warn("Failed to load animation:", name, e);
        }
      }

      const loadedNames = Object.keys(animationClips);
      const defaultAnim = loadedNames.includes("Idle")
        ? "Idle"
        : loadedNames[0];
      if (defaultAnim) {
        playAnimationByName(defaultAnim);
      }
      console.log(`Ready — ${loadedNames.length} animation(s) loaded`);
    } catch (e) {
      console.error("Failed to fetch animation list:", e);
    }

    // Connect WebSocket after animations are loaded
    connectWebSocket();
  },
  undefined,
  (error) => {
    console.error("Error loading VRM:", error);
  },
);

// Init chat UI
initChat();

// Init wake word (async, non-blocking)
initWakeWord().catch((e) => console.warn("Wake word init failed:", e));

// Resize handler
window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

// Animation loop
const clock = new THREE.Clock();
function animate() {
  requestAnimationFrame(animate);
  const delta = clock.getDelta();
  if (mixer) mixer.update(delta);
  if (currentVRM) currentVRM.update(delta);
  controls.update();
  renderer.render(scene, camera);
}
animate();
