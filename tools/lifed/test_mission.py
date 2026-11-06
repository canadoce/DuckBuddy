# -*- coding: utf-8 -*-
"""python -m unittest tools/lifed/test_mission.py — missions: the spoken route, and running it on SimRobot."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mission import Mission, SimRobot, distance_m, en_number, parse_route  # noqa: E402


def steps(text):
    r = parse_route(text)
    return None if r is None else (r.problem or [(s.skill, next(iter(s.args.values()), None)) for s in r.steps])


class NumbersTest(unittest.TestCase):
    def test_numbers_and_distances(self):
        for s, want in (("one", 1), ("two", 2), ("fifteen", 15), ("ninety", 90), ("one hundred eighty", 180),
                        ("a hundred and eighty", 180), ("forty-five", 45), ("forty five", 45), ("zero point five", 0.5),
                        ("1.5", 1.5), ("half", 0.5), ("half a", 0.5), ("a", 1), ("one point two", 1.2),
                        ("one and a half", 1.5), ("2 and a half", 2.5)):
            self.assertEqual(en_number(s), want, s)
        for s, want in (("one meter", 1.0), ("half a meter", 0.5), ("a meter and a half", 1.5), ("fifty centimeters", 0.5),
                        ("50cm", 0.5), ("0.5m", 0.5), ("0.5 m", 0.5), ("two metres", 2.0), ("thirty centimetres", 0.3),
                        ("a meter", 1.0), ("one and a half meters", 1.5), ("1 meter", 1.0)):
            self.assertAlmostEqual(distance_m(s), want, msg=s)


class RouteTest(unittest.TestCase):
    def test_the_first_route(self):
        # the user, 2026-10-17 (the second walk forward after the turn, not a sidestep)
        want = [("walk", 1.0), ("turn", 90.0), ("walk", 0.5), ("sit", None)]
        for text in ("walk forward one meter, then turn left, then walk forward half a meter, and finally sit down",
                     "first walk forward 1m then turn left and walk forward 0.5m and sit down",
                     "Walk forward one meter, turn left and walk forward fifty centimeters, sit down.",
                     "Go forward 1 meter. After that, turn left. Next, go ahead 0.5 m. Finally sit."):
            self.assertEqual(steps(text), want, text)

    def test_turns(self):
        self.assertEqual(steps("turn right forty five degrees"), [("turn", -45.0)])
        self.assertEqual(steps("turn 90 degrees to the right"), [("turn", -90.0)])
        self.assertEqual(steps("turn to the left"), [("turn", 90.0)])
        self.assertEqual(steps("turn around"), [("turn", 180.0)])
        self.assertEqual(steps("turn left and walk half a meter"), [("turn", 90.0), ("walk", 0.5)])

    def test_what_it_asks_about_rather_than_guess(self):
        self.assertEqual(steps("go left half a meter"), "turn_or_side", "turn and walk, or sidestep?")
        self.assertEqual(steps("walk to the right"), "turn_or_side")
        self.assertEqual(steps("sidestep left half a meter"), "no_sidestep")
        self.assertEqual(steps("step sideways a bit"), "no_sidestep")
        self.assertEqual(steps("walk forward"), "how_far")
        self.assertEqual(steps("walk forward two meters, then walk forward two meters"), "too_far")
        self.assertEqual(steps("back up one meter"), "too_far_back")
        self.assertEqual(steps("back up twenty centimeters"), [("walk", -0.2)])
        self.assertEqual(steps("walk backwards 20 cm"), [("walk", -0.2)])

    def test_no_route(self):
        for text in ("sit down", "I walked ten thousand steps today", "look ahead", "I look forward to it",
                     "let's go", "go ahead", "go right ahead and tell me", "stand up", "hello there",
                     "turn your head left", "turn it up", "go to sleep", "stop", "stop walking forward",
                     "don't walk forward one meter", "come here"):
            self.assertIsNone(parse_route(text), text)

    def test_the_steps_are_said_in_english(self):
        r = parse_route("walk forward one meter, turn right, back up 20 cm, turn around, sit down, stand up")
        self.assertEqual([s.words() for s in r.steps], ["walk forward 1 m", "turn right 90°", "walk back 0.2 m",
                                                        "turn around", "sit down", "stand up"])


def run(m, robot, seconds, dt=0.1, obstacle=lambda t: None):
    events = []
    t = 0.0
    while t < seconds and m.state in ("running", "paused", "proposed"):
        tk = m.tick(t, robot.pose, robot.posture, obstacle(t))
        robot.step(dt, tk.twist, tk.skill)
        events += tk.events
        t += dt
    return events


class RunTest(unittest.TestCase):
    def mission(self, text="walk forward one meter, then turn left, then walk forward half a meter, and finally sit down"):
        r = parse_route(text)
        return Mission(text, r.steps)

    def test_the_route_on_a_slow_robot(self):
        m, robot = self.mission(), SimRobot(scale=0.85, turn_scale=0.9)
        m.start(0.0)
        events = run(m, robot, 60)
        self.assertEqual(m.state, "done", m.snapshot())
        self.assertEqual([e[0] for e in events], ["step_done"] * 4 + ["done"])
        p = robot.pose
        self.assertAlmostEqual(p.x, 1.0, delta=0.15)
        self.assertAlmostEqual(p.y, 0.5, delta=0.15)
        self.assertAlmostEqual(math.degrees(p.yaw), 90, delta=8)
        self.assertEqual(robot.posture, "sitting")
        from mission import ODOM_SIGMA_PER_M
        self.assertAlmostEqual(m.snapshot()["sigma_m"], 1.5 * ODOM_SIGMA_PER_M, delta=0.01, msg="1.5 m walked")

    def test_an_odometry_that_reads_short_is_scaled(self):
        # the robot's odometry reads 0.917 of the true distance: SimRobot's pose is the truth, so a
        # mission told its odometry is short by that much must stop at 1 / 0.917 of the reading
        from mission import Pose

        class ShortOdom(SimRobot):
            @property
            def odom(self):
                return Pose(self.pose.x * 0.917, self.pose.y * 0.917, self.pose.yaw)
        m = Mission("x", parse_route("walk forward one meter").steps, odom_scale=1 / 0.917)
        robot = ShortOdom()
        m.start(0.0)
        t = 0.0
        while m.state == "running" and t < 30:
            tk = m.tick(t, robot.odom, robot.posture)
            robot.step(0.1, tk.twist, tk.skill)
            t += 0.1
        self.assertEqual(m.state, "done")
        self.assertAlmostEqual(robot.pose.x, 1.0, delta=0.05)

    def test_nothing_moves_before_start(self):
        m, robot = self.mission(), SimRobot()
        self.assertEqual(run(m, robot, 3), [])
        self.assertEqual((robot.pose.x, robot.pose.y), (0.0, 0.0))

    def test_an_obstacle_pauses_and_it_goes_on_after(self):
        m, robot = self.mission("walk forward one meter"), SimRobot()
        m.start(0.0)
        events = run(m, robot, 30, obstacle=lambda t: 0.2 if 2.0 < t < 2.5 else None)
        self.assertIn(("paused", "obstacle"), events)
        self.assertEqual(m.state, "paused")
        x_at_pause = robot.pose.x
        run(m, robot, 3)
        self.assertEqual(robot.pose.x, x_at_pause, "paused: still")
        m.resume(0.0)
        run(m, robot, 30)
        self.assertEqual(m.state, "done")
        self.assertAlmostEqual(robot.pose.x, 1.0, delta=0.15, msg="the same target, not a new metre")

    def test_a_robot_that_does_not_move_fails_the_step(self):
        m, robot = self.mission("walk forward half a meter"), SimRobot(scale=0.0)
        m.start(0.0)
        events = run(m, robot, 60)
        self.assertEqual((m.state, events[-1]), ("failed", ("failed", "timeout")))
        self.assertEqual(m.snapshot()["steps"][0]["status"], "failed")

    def test_no_odometry_pauses(self):
        m = self.mission("walk forward half a meter")
        m.start(0.0)
        tk = m.tick(0.0, None, "standing")
        self.assertEqual((m.state, tk.events), ("paused", [("paused", "no odometry")]))

    def test_cancel(self):
        m, robot = self.mission(), SimRobot()
        m.start(0.0)
        run(m, robot, 2)
        m.cancel()
        self.assertEqual(m.tick(2.0, robot.pose, "standing").twist, (0.0, 0.0, 0.0))
        self.assertEqual(m.state, "cancelled")


if __name__ == "__main__":
    unittest.main()
