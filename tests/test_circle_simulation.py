import json
import hashlib
import unittest
from pathlib import Path
import numpy as np
from core.config import build_arg_parser
from engines.circle.simulation import CircleSimulation

class CircleRegressionTests(unittest.TestCase):
    def test_legacy_frame_states(self):
        cases=json.loads((Path(__file__).parent/'circle_baselines.json').read_text())
        for name,case in cases.items():
            with self.subTest(name=name):
                engine=CircleSimulation(build_arg_parser().parse_args(case['argv']))
                for expected in case['frames']:
                    state=engine.advance_frame()
                    actual={'balls':[{k:(v.tolist() if isinstance(v,np.ndarray) else v) for k,v in vars(b).items()} for b in state.balls], 'particles':[{k:(v.tolist() if isinstance(v,np.ndarray) else v) for k,v in vars(b).items()} for b in state.particles], 'events':[list(e) for e in state.audio_events], 'time':state.elapsed_time,'rotation':state.rotation, 'collision_count':state.collision_count,'raster_hash':hashlib.sha256(engine.draw_frame().tobytes()).hexdigest() if expected['raster_hash'] else None}
                    self.assertEqual(json.loads(json.dumps(actual)),expected)
                self.assertEqual(engine.frame_index,600)
                self.assertEqual(state.collision_count,len(state.audio_events))
    def test_proxy_drawing_does_not_change_state(self):
        engine=CircleSimulation(build_arg_parser().parse_args(['--fps','60']))
        engine.advance_frame()
        before=[b.pos.copy() for b in engine.state.balls]
        self.assertEqual(engine.draw_frame(270,480).shape,(480,270,3))
        for a,b in zip(before,engine.state.balls): np.testing.assert_array_equal(a,b.pos)
        elapsed=engine.state.elapsed_time
        self.assertAlmostEqual(engine.step(engine.dt).elapsed_time,elapsed+engine.dt)

