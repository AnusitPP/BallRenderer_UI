from engines.drop_engine import cli
from engines.drop.simulation import DropSimulation, recommended_foam_count


def test_ball_falls_and_shatters_with_configured_particle_count():
    args = cli([
        '--width', '360', '--height', '640', '--fps', '60',
        '--seconds', '2', '--ball-size', '30', '--gravity', '1800',
        '--particle-count', '73', '--spawn-interval', '5', '--seed', '4',
    ])
    sim = DropSimulation(args)
    for _ in range(120):
        sim.advance_frame()
    assert sim.shatter_count == 1
    assert len(sim.audio_events) == 1
    assert sim.total_particles_created == 73


def test_remove_foam_on_floor_releases_particles_early():
    sim = DropSimulation(cli(['--width','360','--height','640','--particle-count','20','--remove-foam-on-floor','1']))
    sim._shatter(sim.balls[0])
    for particle in sim.particles:
        particle.pos[:]=(sim.box_left+20,sim.box_bottom)
        particle.vel[:]=0
    sim.advance_frame()
    assert sim.particles == []
    assert sim.audio_events[-1][2] is True
    assert sum(event[2] for event in sim.audio_events) == 10


def test_ball_style_and_frame_size_are_applied():
    args = cli(['--width', '320', '--height', '480', '--ball-size', '44', '--ball-color', '#1234ab'])
    sim = DropSimulation(args)
    assert sim.balls[0].radius == 44
    assert sim.balls[0].color == (171, 52, 18)
    assert sim.draw_frame().shape == (480, 320, 3)


def test_one_shot_mode_drops_only_one_ball_and_keeps_foam_alive():
    args = cli([
        '--width', '360', '--height', '640', '--fps', '60', '--seconds', '8',
        '--one-shot', '1', '--gravity', '500', '--ball-size', '30',
        '--particle-count', '300', '--particle-life', '6', '--seed', '2',
    ])
    sim = DropSimulation(args)
    for _ in range(60 * 5):
        sim.advance_frame()
    assert len(sim.balls) == 1
    assert sim.shatter_count == 1
    assert sim.total_particles_created == 300
    assert len(sim.particles) > 0


def test_single_center_spike_and_configurable_white_foam():
    args = cli(['--width', '360', '--height', '640', '--foam-color', '#ffffff'])
    sim = DropSimulation(args)
    assert len(sim.spikes) == 1
    tip = sim.spikes[0][2]
    assert tip[0] == 180
    sim._shatter(sim.balls[0])
    assert {particle.color for particle in sim.particles} == {(255, 255, 255)}


def test_foam_uses_exact_lifetime_and_stays_inside_collection_box():
    args = cli([
        '--width', '360', '--height', '640', '--fps', '60',
        '--particle-count', '40', '--particle-life', '20',
        '--particle-speed', '300', '--foam-color', '#abcdef', '--seed', '7',
    ])
    sim = DropSimulation(args)
    sim._shatter(sim.balls[0])
    assert {particle.life for particle in sim.particles} == {20.0}
    for _ in range(60 * 5):
        sim.advance_frame()
    assert sim.particles
    assert all(sim.box_left + p.radius - 1e-6 <= p.pos[0] <= sim.box_right - p.radius + 1e-6 for p in sim.particles)
    assert all(p.pos[1] <= sim.box_bottom - p.radius + 1e-6 for p in sim.particles)


def test_foam_particles_separate_instead_of_passing_through_each_other():
    args = cli(['--width', '360', '--height', '640', '--particle-count', '2'])
    sim = DropSimulation(args)
    sim._shatter(sim.balls[0])
    first, second = sim.particles
    first.pos[:] = (180, 500)
    second.pos[:] = (180, 500)
    sim._solve_particle_pairs()
    distance = float(((second.pos - first.pos) ** 2).sum() ** .5)
    assert distance >= first.radius + second.radius - 1e-6


def test_auto_foam_count_scales_with_ball_percent():
    assert recommended_foam_count(1080, 10, 8) > recommended_foam_count(1080, 5, 8)
    assert 80 <= recommended_foam_count(1080, 10, 8) <= 5000
    assert recommended_foam_count(1080, 100, 8) > recommended_foam_count(1080, 10, 8)
    assert recommended_foam_count(1080, 100, 8) == 5000


def test_shatter_starts_foam_across_burst_area():
    args = cli(['--particle-count', '80', '--ball-size', '60', '--seed', '3'])
    sim = DropSimulation(args)
    sim._shatter(sim.balls[0])
    unique_positions = {tuple(p.pos.round(2)) for p in sim.particles}
    assert len(unique_positions) > 60


def test_size_script_spawns_each_percent_every_five_seconds():
    args = cli([
        '--width', '1000', '--height', '1200', '--fps', '10', '--seconds', '30',
        '--gravity', '0', '--size-script', '5,10,25,50,75,100',
        '--segment-seconds', '5', '--auto-foam-from-size', '1',
    ])
    sim = DropSimulation(args)
    for _ in range(10 * 25):
        sim.advance_frame()
    assert [ball.radius for ball in sim.balls] == [25, 50, 125, 250, 375, 500]


def test_auto_foam_uses_physics_budget_and_scales_piece_size():
    args = cli([
        '--width', '1080', '--height', '1920', '--size-script', '100',
        '--auto-foam-from-size', '1', '--particle-budget', '600',
        '--particle-size', '8', '--seed', '5',
    ])
    sim = DropSimulation(args)
    sim._shatter(sim.balls[0])
    assert len(sim.particles) == 600
    assert sim.total_particles_created == 600
    assert max(p.radius for p in sim.particles) > 8
