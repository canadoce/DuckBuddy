# Trained policies (HL-2915 rev-a)

All of them are `obs[1,61] → actions[1,14]`, and robotd loads them directly. To deploy, set both `[policy] action_scale` and
`standing_action_scale` to 1.0 (the action scale used in training), and set both `[bus] position_kp` / `position_kp_head` to 16.

| File | Source | Status |
|---|---|---|
| `walk-baseline.onnx` | Walking baseline trained on the original robot (XL330), 2026-08-30 | Default policy of `training/sim_walk.py` |
| `hl2915_walk_v1_3999.onnx` | `Mjlab-Velocity-Flat-HL2915`, rev-a 850 g + BAM m4, uniform randomization per environment | Real robot, 2026-10-05: stands very steadily; at 0.2 m/s it walks for 2.9 s, then falls forward (see `training/data/2026-10-05-hl2915-realtests/`) |
| `hl2915_walk_v2_3999.onnx` | Same as above + per-joint stiffness ×0.4–1.1, friction ×0.7–2.0, head mass ×0.95–1.3, center of mass 5 mm forward | Passes all sim stress tests (`training/bam/stress_hl2915.py`); the neck no longer dives forward; not yet tested on the real robot |
| `hl2915_walk_v2bl_3999.onnx` | The gear backlash version of v2 (`Mjlab-Velocity-Flat-Backlash-HL2915`) | Same as above, and walks farther under high latency; not yet tested on the real robot |

| `hl2915_standup_v1_5999.onnx` | `Mjlab-StandUp-Flat-HL2915` (same randomization as v2): gets up from lying face down / on its back / on its side and from sitting; once standing, follows body pose commands | In sim, gets up in all 5 stress conditions × 7 start poses (0.3–1.0 s); not yet tested on the real robot. robotd `stand` slot |
| `hl2915_sitstand_v1_3999.onnx` | `Mjlab-SitStand-Flat-HL2915`: the sit flag is in the twist vx slot (1 sit / 0 stand) | In sim, sits down and stands back up in all 5 conditions; not yet tested on the real robot. robotd `sitstand` slot |
| `hl2915_roulade_v1_6999.onnx` | `Mjlab-Roulade-Flat-HL2915`: starts from standing, puts the top of its head on the ground and rolls over; after landing on its back, it sits up and stands up | In sim, completes in all 5 conditions (360° roll in about 1.0 s, standing steady at 1.1 s); with head ×1.5 and the center of mass 20 mm forward, it cannot roll over. robotd `roulade` slot |

| `hl2915_walk_v3bl_3999.onnx` | v3: gear backlash + robotd low-pass in training (head 0.5 / legs 0.7) + head DR centered (after weighing) | In BAM sim (with low-pass), walks in all 5 conditions; not yet tested on the real robot |
| `hl2915_standup_v3bl_5999.onnx` | v3 stand-up: same as above + a head joint velocity penalty added after 3000 iterations | In BAM sim, gets up 35/35; the neck no longer hits the −90° limit (lowest −65°); peak head swing speed 540 → 360–490°/s; not yet tested on the real robot |
| `hl2915_sitstand_v3bl_3999.onnx` | v3 sit/stand | Same training metrics as v1, but in BAM sim **without gear backlash** it does not sit under normal conditions. The v3bl policy relies on the backlash readback it saw in training, so BAM sim cannot rate it correctly; not yet tested on the real robot |

v3 deployment: keep the robotd low-pass at its default (0.5 / 0.7, already in training), `standing_gain_ratio = 1.0`.

From v4 on, we no longer take the last checkpoint. We pick one with the sweep in `training/bam/checkpoint_sweep_hl2915.py` (in one training run, the
yaw while walking straight goes from −30 to +42 °/s between checkpoints, and the training metrics do not show this; results in `training/data/sim-hl2915/sweep-*/`). The files below are
exported on the CPU by `training/hl2915/ckpt_onnx.py` (they differ from the export.py output by <1e-5).

| File | Source | Status |
|---|---|---|
| `hl2915_walk_v2bl_3250.onnx` | v2bl, iteration 3250 | In sim at 0.2 m/s, yaw +5~+14°/8 s (3999: −88~−133°), no falls; meant to be run on the real robot to calibrate the sim's yaw ranking; not yet tested on the real robot |
| `hl2915_walk_v4bl_3500.onnx` | v4: v2bl recipe + random backlash ±0.3–1.0° per joint per episode (`Velocity-Flat-Backlash`, server 215ea1a) | Same training metrics as v2bl (episode 959 / falls 8.5%); at 0.2 m/s yaw 0~+11°/8 s, stress 0/20 falls (3999 drifts +27~+120°); not yet tested on the real robot |
| `hl2915_walk_v4bl_lowfric_3999.onnx` | v4 + foot friction 0.4–1.3 (`Velocity-Flat-Backlash-LowFriction`) | **Best in the sweep**: yaw −1~−11°/8 s, walks 71% or more of the commanded distance, stress 0/20 falls; not yet tested on the real robot |

| `hl2915_standup_v4bl_5999.onnx` | v4 stand-up: v2bl recipe (low-pass not in training) + random backlash ±0.3–1.0° per episode + head velocity penalty | BAM sim (backlash ±0.35°, low-pass): gets up 35/35 in 0.3–1.0 s; with legs ×0.4 it does not self-oscillate (v3bl under the same condition: in 2/7 start poses it jumps ~3° every step); not yet tested on the real robot |

v4 deployment is the same as v2bl: low-pass 0.5 / 0.7 (not in training), `standing_gain_ratio = 0.8` (while the stand-up policy is still v3bl).

To test again in sim:

```bash
python training/bam/stress_hl2915.py training/policies/hl2915_walk_v2_3999.onnx training/policies/hl2915_walk_v2bl_3999.onnx
python training/bam/eval_skills_hl2915.py --standup training/policies/hl2915_standup_v1_5999.onnx \
    --sitstand training/policies/hl2915_sitstand_v1_3999.onnx --roulade training/policies/hl2915_roulade_v1_6999.onnx
python training/bam/eval_skills_hl2915.py --head ...   # heads outside the training range
```

To deploy the stand-up / sit-stand / roulade policies: `standing_gain_ratio = 1.0` (training uses Kp 16 the whole time; the default 0.8 lowers it to 13 while standing).
After the `stand` slot holds the stand-up policy, set `[safety] limp_fall_hand_back = true` (after a fall, robotd hands over to it to get up). `roulade_duration = 1.0` matches the sim.
Videos and frame images: `training/data/sim-hl2915/skills/`.

### v5 and v4 skills (2026-10-10)

| File | Source | Status |
|---|---|---|
| `hl2915_walk_v5bl_delay50_2000.onnx` | v5: v4 recipe + command delay 10–50 ms (`Velocity-Flat-Backlash-Delay50`; the measured equivalent delay on the real robot is ≈40 ms), iteration 2000 | Sweep: all 11 checkpoints have 0/20 falls under the stress conditions; at iteration 2000, 0.2 m/s walks 0.97 m with yaw +4~+8° (later checkpoints stay in place at 0.2 m/s). Delay comparison (`training/data/sim-hl2915/delay-sweep-20261010/`): at 50 / 60 ms only 1/8 and 2/8 falls (v4bl_lowfric 4/8, 8/8; v2bl 3/8, 7/8); not yet tested on the real robot |
| `hl2915_sitstand_v4bl_3999.onnx` | v4 sit-stand (v2bl recipe + random backlash) | BAM sim (backlash 0.35°, low-pass): sits down and stands up 5/5, tilt ≤17° (v3bl 2/5); not yet tested on the real robot |
| `hl2915_roulade_v4bl_6999.onnx` | v4 roulade | 5/5 (same as v3bl); not yet tested on the real robot |

### v6 (2026-10-11)

| File | Source | Status |
|---|---|---|
| `hl2915_walk_v6lp_3250.onnx` | v6: v4lf recipe with four changes: IMU observation delay 0–40 ms, leg stiffness randomization 0.6–1.2, action gain 0.75–1.05 per episode, robotd low-pass in training (`Velocity-Flat-Backlash-LowFriction-V6LP`); iteration 3250 | Best overall in the sim matched to the real robot (`training/data/sim-hl2915/v6-sweep-20261011/`): 0 falls at amplitude 1.0, pitch rate RMS 21 °/s, neck swing 2.7°; no falls with 30 ms IMU delay either (v4lf at amplitude 1.0: 5/6 falls); not yet tested on the real robot |
| `hl2915_walk_v6lp_3999.onnx` | Same as above, iteration 3999 | Best at amplitude 0.8 with 30 ms (RMS 21, yaw 42° in 8 s, 0.81 m forward); not yet tested on the real robot |
| `hl2915_walk_v6lp_slip_3999.onnx` | v6lp recipe, ground friction 0.15–1.3 (`Velocity-Flat-Backlash-Slippery-V6LP`); iteration 3999 | **Best on the real robot on the evening of 10-11, on a hard floor with silicone foot pads**: amplitude 0.9, yaw rate p95 93°/s (v6lp 125–133), sway RMS 32, slow drift in one direction of −32° in 6 s; with heading hold v2 added, the yaw at the end is +8°. Config: `training/data/2026-10-12-feet/today-slip3999-09-st08-hold.toml` |

v6 deployment: low-pass 0.5 / 0.7 (already in training), `action_scale = 1.0` (try first), then try 0.9; everything else as in the group G config (median off, correction 3.3°, `walk_settle_s = 2.0`).

