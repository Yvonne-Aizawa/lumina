import * as THREE from "three";
import { FBXLoader } from "three/addons/loaders/FBXLoader.js";

// Shared animation state
let mixer = null;
let vrm = null;
let currentAnimName = null;
let currentAction = null;
const animationClips = {}; // name -> clip
const loadingClips = {}; // name -> Promise (in-flight loads)
const CROSSFADE_DURATION = 0.3;

function setMixer(m) {
  mixer = m;
}

function setVRM(v) {
  vrm = v;
}

// Mixamo bone name to VRM humanoid bone name mapping
function mixamoToVRMBone(mixamoName) {
  const map = {
    mixamorigHips: "hips",
    mixamorigSpine: "spine",
    mixamorigSpine1: "chest",
    mixamorigSpine2: "upperChest",
    mixamorigNeck: "neck",
    mixamorigHead: "head",
    mixamorigLeftShoulder: "leftShoulder",
    mixamorigLeftArm: "leftUpperArm",
    mixamorigLeftForeArm: "leftLowerArm",
    mixamorigLeftHand: "leftHand",
    mixamorigLeftHandThumb1: "leftThumbMetacarpal",
    mixamorigLeftHandThumb2: "leftThumbProximal",
    mixamorigLeftHandThumb3: "leftThumbDistal",
    mixamorigLeftHandIndex1: "leftIndexProximal",
    mixamorigLeftHandIndex2: "leftIndexIntermediate",
    mixamorigLeftHandIndex3: "leftIndexDistal",
    mixamorigLeftHandMiddle1: "leftMiddleProximal",
    mixamorigLeftHandMiddle2: "leftMiddleIntermediate",
    mixamorigLeftHandMiddle3: "leftMiddleDistal",
    mixamorigLeftHandRing1: "leftRingProximal",
    mixamorigLeftHandRing2: "leftRingIntermediate",
    mixamorigLeftHandRing3: "leftRingDistal",
    mixamorigLeftHandPinky1: "leftLittleProximal",
    mixamorigLeftHandPinky2: "leftLittleIntermediate",
    mixamorigLeftHandPinky3: "leftLittleDistal",
    mixamorigRightShoulder: "rightShoulder",
    mixamorigRightArm: "rightUpperArm",
    mixamorigRightForeArm: "rightLowerArm",
    mixamorigRightHand: "rightHand",
    mixamorigRightHandThumb1: "rightThumbMetacarpal",
    mixamorigRightHandThumb2: "rightThumbProximal",
    mixamorigRightHandThumb3: "rightThumbDistal",
    mixamorigRightHandIndex1: "rightIndexProximal",
    mixamorigRightHandIndex2: "rightIndexIntermediate",
    mixamorigRightHandIndex3: "rightIndexDistal",
    mixamorigRightHandMiddle1: "rightMiddleProximal",
    mixamorigRightHandMiddle2: "rightMiddleIntermediate",
    mixamorigRightHandMiddle3: "rightMiddleDistal",
    mixamorigRightHandRing1: "rightRingProximal",
    mixamorigRightHandRing2: "rightRingIntermediate",
    mixamorigRightHandRing3: "rightRingDistal",
    mixamorigRightHandPinky1: "rightLittleProximal",
    mixamorigRightHandPinky2: "rightLittleIntermediate",
    mixamorigRightHandPinky3: "rightLittleDistal",
    mixamorigLeftUpLeg: "leftUpperLeg",
    mixamorigLeftLeg: "leftLowerLeg",
    mixamorigLeftFoot: "leftFoot",
    mixamorigLeftToeBase: "leftToes",
    mixamorigRightUpLeg: "rightUpperLeg",
    mixamorigRightLeg: "rightLowerLeg",
    mixamorigRightFoot: "rightFoot",
    mixamorigRightToeBase: "rightToes",
  };
  return map[mixamoName] ?? null;
}

// Load a Mixamo FBX and convert to VRM clip
function loadMixamoAnimation(url, vrm) {
  return new Promise((resolve, reject) => {
    const fbxLoader = new FBXLoader();
    fbxLoader.load(
      url,
      (fbx) => {
        const clip = fbx.animations[0];
        if (!clip) {
          reject(new Error("No animation found in " + url));
          return;
        }

        const tracks = [];

        // Get hips height ratio for position scaling
        const mixamoHips = fbx.getObjectByName("mixamorigHips");
        const motionHipsHeight = mixamoHips ? mixamoHips.position.y : 1;
        const vrmHipsNode = vrm.humanoid?.getNormalizedBoneNode("hips");
        const vrmHipsY = vrmHipsNode
          ? vrmHipsNode.getWorldPosition(new THREE.Vector3()).y
          : 1;
        const hipsPositionScale = vrmHipsY / motionHipsHeight;

        const restRotationInverse = new THREE.Quaternion();
        const parentRestWorldRotation = new THREE.Quaternion();
        const _quatA = new THREE.Quaternion();

        clip.tracks.forEach((track) => {
          const trackSplitted = track.name.split(".");
          const mixamoRigName = trackSplitted[0];
          const vrmBoneName = mixamoToVRMBone(mixamoRigName);
          if (vrmBoneName == null) return;

          const vrmNode = vrm.humanoid.getNormalizedBoneNode(vrmBoneName);
          if (vrmNode == null) return;

          const mixamoRigNode = fbx.getObjectByName(mixamoRigName);
          if (mixamoRigNode == null) return;

          const propertyName = trackSplitted[1];

          // Get the bone's world rest rotation and its parent's
          mixamoRigNode.getWorldQuaternion(restRotationInverse).invert();
          mixamoRigNode.parent.getWorldQuaternion(parentRestWorldRotation);

          if (track instanceof THREE.QuaternionKeyframeTrack) {
            for (let i = 0; i < track.values.length; i += 4) {
              const flatQuaternion = track.values.slice(i, i + 4);
              _quatA.fromArray(flatQuaternion);

              // Transform: parentRestWorld * anim * restWorldInverse
              _quatA
                .premultiply(parentRestWorldRotation)
                .multiply(restRotationInverse);

              _quatA.toArray(flatQuaternion);
              flatQuaternion.forEach((v, index) => {
                track.values[index + i] = v;
              });
            }

            tracks.push(
              new THREE.QuaternionKeyframeTrack(
                `${vrmNode.name}.${propertyName}`,
                track.times,
                track.values.map((v, i) =>
                  vrm.meta?.metaVersion === "0" && i % 2 === 0 ? -v : v,
                ),
              ),
            );
          } else if (track instanceof THREE.VectorKeyframeTrack) {
            const value = track.values.map(
              (v, i) =>
                (vrm.meta?.metaVersion === "0" && i % 3 !== 1 ? -v : v) *
                hipsPositionScale,
            );
            tracks.push(
              new THREE.VectorKeyframeTrack(
                `${vrmNode.name}.${propertyName}`,
                track.times,
                value,
              ),
            );
          }
        });

        resolve(new THREE.AnimationClip("vrmAnimation", clip.duration, tracks));
      },
      undefined,
      reject,
    );
  });
}

// Load a single animation on demand (deduplicates concurrent requests)
async function ensureAnimation(name) {
  if (animationClips[name]) return animationClips[name];
  if (!vrm) return null;
  if (loadingClips[name]) return loadingClips[name];
  const url = `./anims/${encodeURIComponent(name)}.fbx`;
  loadingClips[name] = loadMixamoAnimation(url, vrm)
    .then((clip) => {
      animationClips[name] = clip;
      console.log("Loaded animation:", name);
      return clip;
    })
    .catch((e) => {
      console.warn("Failed to load animation:", name, e);
      return null;
    })
    .finally(() => {
      delete loadingClips[name];
    });
  return loadingClips[name];
}

// Play animation by name with crossfade blending
async function playAnimationByName(name) {
  if (!mixer) return;
  let clip = animationClips[name] || (await ensureAnimation(name));
  if (!clip) {
    console.warn("Animation not found:", name);
    return;
  }

  const idleClip = animationClips["Idle"] || (await ensureAnimation("Idle"));
  const isIdle = name === "Idle";

  // Remove any previous finished listener to avoid stacking
  if (mixer._onFinished) {
    mixer.removeEventListener("finished", mixer._onFinished);
    mixer._onFinished = null;
  }

  const previousAction = currentAction;
  const action = mixer.clipAction(clip);
  action.reset();

  if (!isIdle && idleClip) {
    action.setLoop(THREE.LoopOnce, 1);
    action.clampWhenFinished = true;
  } else {
    action.setLoop(THREE.LoopRepeat);
  }

  if (previousAction) {
    action.crossFadeFrom(previousAction, CROSSFADE_DURATION, true);
  }
  action.play();
  currentAction = action;
  currentAnimName = name;

  if (!isIdle && idleClip) {
    const onFinished = () => {
      mixer.removeEventListener("finished", onFinished);
      mixer._onFinished = null;
      const idleAction = mixer.clipAction(idleClip);
      idleAction.reset();
      idleAction.crossFadeFrom(action, CROSSFADE_DURATION, true);
      idleAction.play();
      currentAction = idleAction;
      currentAnimName = "Idle";
    };
    mixer._onFinished = onFinished;
    mixer.addEventListener("finished", onFinished);
  }
}

export {
  animationClips,
  ensureAnimation,
  loadMixamoAnimation,
  mixamoToVRMBone,
  playAnimationByName,
  setMixer,
  setVRM,
};
