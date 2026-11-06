# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["mujoco", "onnxruntime", "numpy", "pillow", "imageio", "imageio-ffmpeg", "trimesh",
#                 "better-actuator-models @ git+https://github.com/Rhoban/bam@62bd8ce12154340be97e06f7f41a0ca8f116d967"]
# ///
"""Film the HL-2915 policies in the simulation with the LiPo plate on the robot.

Run from hardware/cad/lipo-plate, after src/build_plate.py:

    uv run tools/policy_videos.py [MJLAB_DIR]

It uses the `lipo` scene of tools/policy_poses.py (the plate, the pack and the BNO055 shown, their
collision boxes and the trunk's new mass) under the nominal condition, with robotd's target
low-pass and 0.35 deg of gear play, and films from behind the robot's right side so the pack and
the plate stay in view. Clips: walking at 0.2 m/s, getting up from lying face up, face down and on
the left side, sitting down and standing up, the forward roll. Each clip carries its name, the
clock and the trunk's pitch, and they are joined into tmp/lipo_plate_policies.mp4.
"""

import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import policy_poses as pp  # noqa: E402

OUT = pp.ROOT / "tmp/lipo_plate_policies.mp4"
CLIP_DIR = pp.ROOT / "tmp/videos"
# (file name, caption, skill, start pose, seconds)
CLIPS = [
    ("walk", "walk 0.2 m/s", "walk", "stand", 8.0),
    ("standup_face_up", "stand-up from face up", "standup", "face_up", 5.0),
    ("standup_face_down", "stand-up from face down", "standup", "face_down", 5.0),
    ("standup_side_left", "stand-up from the left side", "standup", "side_left", 5.0),
    ("sitstand", "sit down and stand up", "sitstand", "stand", 12.0),
    ("roulade", "forward roll", "roulade", "stand", 6.0),
]


def film(scene, name, caption, skill, init, seconds):
    os.chdir(pp.REPO)
    import eval_skills_hl2915 as ev
    import sim_hl2915 as sh

    label, extra, delay = ev.CONDITIONS[0]
    assert label == "nominal"
    if skill == "walk":
        a = ev.args_for(str(pp.WALK), extra, delay, init, seconds, None, ev.ROBOTD_LOWPASS, pp.BACKLASH)
        cmd, policy = dict(ev.ZERO, twist=[0.2, 0.0, 0.0]), pp.WALK
    else:
        cmd_fn = ev.SKILLS[skill][2]
        policy = pp.SKILL_POLICIES[skill]
        a = ev.args_for(str(policy), extra, delay, init, seconds, cmd_fn, ev.ROBOTD_LOWPASS, pp.BACKLASH)
        cmd = ev.ZERO
    if skill != "walk":
        # the simulator marks a fall when the trunk is low or tilted: how a stand-up starts and a
        # roll goes, so leave it off these captions
        caption_frame = sh.caption_frame
        sh.caption_frame = lambda frame, title, t, pitch, pushes, fell: caption_frame(frame, title, t, pitch, pushes, None)
    a.scene = str(scene)
    a.video = str(CLIP_DIR / f"{name}.mp4")
    a.video_size = "960x540"
    a.caption = f"LiPo plate - {caption}"
    a.video_speed = 1.0
    a.cam_distance, a.cam_elevation, a.cam_azimuth, a.cam_follow_yaw = 0.45, -15.0, 30.0, True
    log = sh.run(a, str(scene), str(policy), cmd)
    if skill == "walk":
        score = "ok" if log["fell"] is None else f"fell {log['fell']:.1f}s"
    else:
        score = ev.SKILLS[skill][3](log)[1] if seconds >= ev.SKILLS[skill][1] else "-"
    return name, score


def main():
    import imageio.v2 as iio

    mjlab = sys.argv[1] if len(sys.argv) > 1 else str(pp.DEFAULT_MJLAB)
    scene = pp.scene_with_meshes(mjlab, "lipo")
    CLIP_DIR.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(len(CLIPS)) as ex:
        for name, score in ex.map(film, *zip(*[(scene, *c) for c in CLIPS])):
            print(f"  {name}: {score}")
    clips = [iio.get_reader(CLIP_DIR / f"{name}.mp4") for name, *_ in CLIPS]
    fps = clips[0].get_meta_data()["fps"]
    with iio.get_writer(OUT, fps=fps, macro_block_size=1, quality=8) as out:
        for clip in clips:
            assert clip.get_meta_data()["fps"] == fps
            for frame in clip:
                out.append_data(frame)
            clip.close()
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
