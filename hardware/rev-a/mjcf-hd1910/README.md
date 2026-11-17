# Xiaohei HD-1910 (2S) MuJoCo model

The model's total mass is 806 g, set from Xiaohei's measured weight with a 2S battery fitted. Each HD-1910 (with its horns) is modelled as 22.8 g. The model reuses the STL meshes in the folder next to it, `../mjcf/assets/`, so keep the repository's folder layout when you download it.

- [scene_walk.xml](scene_walk.xml) · the walking scene.
- [scene.xml](scene.xml) · the scene with all collisions, for stand-up simulation.
- [robot_allcollisions_rollers.xml](robot_allcollisions_rollers.xml) · the robot model with roller joints.

With MuJoCo installed, run from the repository root:

```bash
python -m mujoco.viewer --mjcf=hardware/rev-a/mjcf-hd1910/scene_walk.xml
```

The meshes and the original model are based on Pollen Robotics' Microduck.

## Walk policy

The [HD-1910 walk policy (Kp 16, checkpoint 6500)](../../../training/policies/hd1910_walk_kp16_6500.onnx) is the baseline policy the `-r3` image sets up for the HD-1910 (2S). Loading the ONNX needs the DuckBuddy controller's observation and action interface.
