import math
import unittest

from core.config import build_arg_parser
from engines.circle import simulation


class EscapeHudTests(unittest.TestCase):
    def test_groups_alive_balls_by_color_and_uses_integer_countdown(self):
        self.assertTrue(hasattr(simulation, "build_escape_hud_data"))
        args = build_arg_parser().parse_args([
            "--seconds", "45",
            "--escape-duplicate", "1",
            "--escape-hud", "1",
            "--escape-countdown", "1",
        ])
        engine = simulation.CircleSimulation(args)
        red = engine.balls[0]
        blue = simulation.copy.deepcopy(red)
        blue.color = (255, 166, 77)
        engine.balls.append(blue)
        data = simulation.build_escape_hud_data(engine.balls, 15.2, 45.0)
        self.assertEqual(data["counts"], [(tuple(red.color), 1), ((255, 166, 77), 1)])
        self.assertEqual(data["countdown"], math.ceil(45.0 - 15.2))


if __name__ == "__main__":
    unittest.main()
