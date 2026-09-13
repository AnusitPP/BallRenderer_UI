"""Deterministic legacy Circle simulation shared by previews and final rendering."""
import copy
from core.simulation_state import SimulationState
from engines.circle.physics import *
from engines.circle.drawing import *


def build_escape_hud_data(balls, sim_time, total_seconds):
    counts = {}
    for ball in balls:
        if not ball.alive:
            continue
        color = tuple(int(channel) for channel in ball.color)
        counts[color] = counts.get(color, 0) + 1
    return {
        'counts': list(counts.items()),
        'countdown': max(0, int(math.ceil(float(total_seconds) - float(sim_time)))),
    }

class CircleSimulation:
    def __init__(self, config, source_samples=None):
        self.args = copy.deepcopy(config)
        self.config = self.args
        self.source_samples = source_samples if source_samples is not None else []
        self.frame_index = 0
        self.collision_count = 0
        self.state = SimulationState()
        self.args.ball_count = max(1, min(8, int(self.args.ball_count)))
        self.args.spike_count = max(0, min(12, int(self.args.spike_count)))
        self.args.gap_size = max(0.0, min(300.0, float(self.args.gap_size))) if self.args.gap_enabled else 0.0
        self.args.gap_position = normalize_angle_deg(self.args.gap_position)
        self.ball_lives = parse_ball_lives(self.args.ball_lives, self.args.ball_count, default=10)
        self.args.note_volume = max(0.0, min(1.5, float(self.args.note_volume)))
        self.args.source_volume = max(0.0, min(2.0, float(self.args.source_volume)))
        self.args.sample_ms = max(80, min(800, int(self.args.sample_ms)))
        self.ball_color_mode = self.args.ball_color_mode
        if self.ball_color_mode is None:
            self.ball_color_mode = 'random' if self.args.random_ball_color else 'same'
        self.ball_colors = parse_ball_colors(self.args.ball_colors)
        self.ball_skins = load_ball_images(getattr(self.args, 'ball_images', ''))
        self.rng = np.random.default_rng(self.args.seed)
        self.runtime_state = {'gap_enabled': bool(self.args.gap_enabled), 'gap_size': float(self.args.gap_size), 'gap_position': float(self.args.gap_position), 'spike_count': int(self.args.spike_count), 'rotation_speed': float(self.args.rotation_speed), 'gravity': float(self.args.gravity), 'speed_growth': float(self.args.speed_growth), 'max_speed': float(self.args.max_speed), 'wall_restitution': float(self.args.wall_restitution), 'bounce_growth': float(self.args.bounce_growth), 'wall_friction': float(self.args.wall_friction), 'air_drag': float(self.args.air_drag), 'growth': float(self.args.growth), 'ball_color_mode': self.ball_color_mode, 'show_ball_numbers': bool(self.args.show_ball_numbers), '_spawn_ball_chance': 1.0, 'special_spawn_interval': 20, 'special_spawn_color': '#4da6ff'}
        self.pattern_name = 'Manual'
        self.pattern_events = []
        self.pattern_index = 0
        if self.args.pattern_file:
            self.loaded_pattern = load_pattern_file(self.args.pattern_file)
            self.pattern_name = self.loaded_pattern['name']
            apply_pattern_defaults(self.runtime_state, self.loaded_pattern['defaults'])
            self.pattern_events = self.loaded_pattern['events']
            self.pattern_index = apply_pattern_events_up_to(self.runtime_state, self.pattern_events, 0, 0.0)
            self.ball_color_mode = self.runtime_state.get('ball_color_mode', self.ball_color_mode)
        self.W, self.H = (int(self.args.width), int(self.args.height))
        self.FPS = max(1, int(self.args.fps))
        self.substeps = max(1, int(self.args.substeps))
        self.dt = 1.0 / self.FPS / self.substeps
        self.total_frames = max(1, int(self.args.seconds * self.FPS))
        self.center = np.array([self.W * 0.5, self.H * 0.52], dtype=np.float64)
        self.arena_scale = max(0.55, min(1.1, float(self.args.arena_scale)))
        self.arena_radius = min(self.W * 0.42, self.H * 0.275) * self.arena_scale
        self.scale = self.W / 1080.0
        self.base_radius = self.args.base_radius * self.scale
        self.growth = self.args.growth * self.scale
        self.oversize_margin = max(2.0, 8.0 * self.scale)
        configured_max_radius = getattr(self.args, 'max_ball_radius', None)
        self.max_ball_radius = min(self.arena_radius - self.oversize_margin, float(configured_max_radius) * self.scale) if configured_max_radius else self.arena_radius - self.oversize_margin
        self.spike_depth = self.args.spike_depth * self.scale
        self.spike_half_width = self.args.spike_width * self.scale
        self.ring_width = max(2, int(round(5 * self.scale)))
        self.border_width = max(2, int(round(4 * self.scale)))
        self.melody = {'name': 'Built-in', 'notes': list(DEFAULT_MELODY_NOTES), 'instrument': self.args.instrument, 'volume': self.args.note_volume, 'loop': bool(self.args.melody_loop), 'restart_on_break': bool(self.args.restart_melody_on_break)}
        if self.args.melody_file:
            self.loaded = load_melody_file(self.args.melody_file)
            self.melody['notes'] = self.loaded['notes']
            self.melody['name'] = self.loaded['name']
        self.notes = [max(0, min(127, int(n) + self.args.transpose)) for n in self.melody['notes']]
        self.melody_index = 0
        self.balls = [spawn_ball(self.center, self.arena_radius, self.base_radius, self.rng, i, self.args.ball_count, color=resolve_ball_color(self.ball_color_mode, self.ball_colors, i, self.rng), initial_angle_deg=self.args.initial_angle, initial_speed=self.args.initial_speed * self.scale, max_life=self.ball_lives[i]) for i in range(self.args.ball_count)]
        self.dynamic_spawn_count = 0
        for ball in self.balls:
            ball.target_radius = ball.radius
        self.particles = []
        self.sound_events = []
        # The practical limit is the packing capacity of the arena, not an
        # arbitrary gameplay cap.  512 is only a safety guard for pathological
        # settings with very tiny balls.
        # Dynamic multiplication is bounded by the actual disk packing
        # capacity, with a generous safety ceiling for pathological settings.
        self.max_dynamic_balls = 4096
        self.trail_layer = np.zeros((self.H, self.W, 3), dtype=np.uint8)
        self.trail_last_pos = [ball.pos.copy() for ball in self.balls]
        self.rotation_angle = 0.0
        self.sim_time = 0.0
        self.spikes = []
        self._sync_state()

    def _sync_state(self):
        self.state.balls = self.balls
        self.state.particles = self.particles
        self.state.spikes = self.spikes
        self.state.elapsed_time = self.sim_time
        self.state.rotation = self.rotation_angle
        self.state.audio_events = self.sound_events
        self.state.collision_count = self.collision_count
        self.state.status = "complete" if self.frame_index >= self.total_frames else "running"
        return self.state

    def _apply_dynamic_spawn_color(self, clone):
        self.dynamic_spawn_count += 1
        interval = int(self.runtime_state.get('special_spawn_interval', 20))
        if interval > 0 and self.dynamic_spawn_count % interval == 0:
            color = str(self.runtime_state.get('special_spawn_color', '#4da6ff'))
            clone.color = hex_to_bgr(color if color.startswith('#') else '#4da6ff')
        return clone

    def step(self, dt=None):
        configured_dt = self.dt
        if dt is not None:
            self.dt = float(dt)
        self.pattern_index = apply_pattern_events_up_to(self.runtime_state, self.pattern_events, self.pattern_index, self.sim_time)
        spawn_color = self.runtime_state.pop('_spawn_ball_color', None)
        if spawn_color and self.rng.random() <= float(self.runtime_state.get('_spawn_ball_chance', 1.0)):
            active = [item for item in self.balls if item.alive]
            if active:
                source = active[int(self.rng.integers(0, len(active)))]
                radius = source.radius
                placed = None
                for _attempt in range(160):
                    angle = self.rng.uniform(0.0, math.tau)
                    candidate = source.pos + np.array([math.cos(angle), math.sin(angle)]) * (radius * 2.0 + 2.0)
                    if length(candidate - self.center) + radius > self.arena_radius - 1.0:
                        continue
                    if all(length(candidate - other.pos) >= radius + other.radius + 1.0 for other in active):
                        placed = candidate
                        break
                if placed is None:
                    # Keep the one-blue-ball event reliable when the local
                    # neighbourhood is packed: find another legal pocket in
                    # the arena instead of silently losing the event.
                    for _attempt in range(320):
                        angle = self.rng.uniform(0.0, math.tau)
                        radial = math.sqrt(self.rng.uniform(0.0, 1.0)) * max(0.0, self.arena_radius - radius - 1.0)
                        candidate = self.center + np.array([math.cos(angle), math.sin(angle)]) * radial
                        if all(length(candidate - other.pos) >= radius + other.radius + 1.0 for other in active):
                            placed = candidate
                            break
                if placed is not None:
                    clone = copy.deepcopy(source)
                    clone.pos = placed
                    clone.vel = source.vel.copy() * np.array([-1.0, 1.0])
                    clone.color = hex_to_bgr(spawn_color) if str(spawn_color).startswith('#') else hex_to_bgr('#4da6ff')
                    clone.spike_hit_cooldown = max(0.01, float(self.args.respawn_delay))
                    self.balls.append(self._apply_dynamic_spawn_color(clone))
        self.sim_time += self.dt
        self.rotation_angle += self.runtime_state['rotation_speed'] * self.dt
        gravity = np.array([0.0, self.runtime_state['gravity'] * self.scale], dtype=np.float64)
        self.spikes = get_spikes(self.center, self.arena_radius, self.rotation_angle, self.spike_depth, self.spike_half_width, self.runtime_state['spike_count'], gap_position_deg=self.runtime_state['gap_position'] if self.runtime_state['gap_enabled'] else 0.0, gap_size_deg=self.runtime_state['gap_size'] if self.runtime_state['gap_enabled'] else 0.0)
        duplicate_targets = []
        escaped_balls = []
        for i, ball in enumerate(self.balls):
            if not ball.alive:
                if ball.eliminated:
                    continue
                ball.respawn_timer -= self.dt
                if ball.respawn_timer <= 0.0:
                    self.balls[i] = spawn_ball(self.center, self.arena_radius, self.base_radius, self.rng, i, self.args.ball_count, color=ball.color, initial_angle_deg=self.args.initial_angle, initial_speed=self.args.initial_speed * self.scale, max_life=ball.max_life, current_life=ball.life, center_spawn=True)
                    self.balls[i].target_radius = self.balls[i].radius
                    self.trail_last_pos[i] = self.balls[i].pos.copy()
                continue
            ball.wall_hit_cooldown = max(0.0, ball.wall_hit_cooldown - self.dt)
            ball.spike_hit_cooldown = max(0.0, ball.spike_hit_cooldown - self.dt)
            if ball.target_radius <= 0.0:
                ball.target_radius = ball.radius
            if ball.radius < ball.target_radius:
                ball.radius = min(ball.target_radius, ball.radius + max(0.0, self.args.smooth_growth_speed) * self.scale * self.dt)
            # A growing ball must burst before its collision radius leaves the arena.
            # Without this guard the allowed wall distance becomes negative and the
            # ball can tunnel through the ring while continuing to grow forever.
            if ball.radius >= self.max_ball_radius:
                self.collision_count += 1
                self.particles.extend(create_particles(ball, self.rng, min_count=34, max_count=140))
                self.sound_events.append((self.sim_time, 'spike', 1.0))
                ball.alive = False
                ball.eliminated = False
                ball.respawn_timer = max(0.01, float(self.args.respawn_delay))
                ball.life = ball.max_life
                ball.radius = self.base_radius
                ball.target_radius = self.base_radius
                ball.vel[:] = 0.0
                continue
            ball.vel += gravity * self.dt
            ball.vel *= math.exp(-self.runtime_state['air_drag'] * self.dt)
            ball.vel = clamp_speed(ball.vel, self.runtime_state['max_speed'] * self.scale)
            ball.pos += ball.vel * self.dt
            hit_spike = any((circle_hits_triangle(ball.pos, ball.radius, tri) for tri in self.spikes))
            if hit_spike and ball.spike_hit_cooldown <= 0.0:
                self.collision_count += 1
                if getattr(self.args, 'spike_duplicate', 0):
                    if not any(item is ball for item in duplicate_targets): duplicate_targets.append(ball)
                    ball.spike_hit_cooldown = max(0.01, float(self.args.respawn_delay))
                    self.particles.extend(create_particles(ball, self.rng, min_count=12, max_count=45))
                    self.sound_events.append((self.sim_time, 'spike', 1.0))
                    continue
                eliminated = apply_spike_damage(ball, self.center, self.arena_radius, cooldown=self.args.respawn_delay)
                self.particles.extend(create_particles(ball, self.rng))
                self.sound_events.append((self.sim_time, 'spike', 1.0))
                if self.args.restart_melody_on_break:
                    self.melody_index = 0
                if eliminated:
                    continue
                continue
            wall_hit = solve_ball_wall(ball, self.center, self.arena_radius, self.runtime_state['wall_restitution'], self.runtime_state['wall_friction'], gap_position_deg=self.runtime_state['gap_position'] if self.runtime_state['gap_enabled'] else 0.0, gap_size_deg=self.runtime_state['gap_size'] if self.runtime_state['gap_enabled'] else 0.0)
            if getattr(self.args, 'escape_duplicate', 0) and ball.escaped_arena:
                escaped_balls.append(ball)
                continue
            if wall_hit and ball.wall_hit_cooldown <= 0.0:
                self.collision_count += 1
                if self.args.audio:
                    if self.args.audio_mode == 'bounce-samples' and self.source_samples:
                        if self.melody_index < len(self.source_samples):
                            self.sound_events.append((self.sim_time, 'sample', self.melody_index))
                            self.melody_index += 1
                        elif self.args.melody_loop:
                            self.melody_index = 0
                            self.sound_events.append((self.sim_time, 'sample', self.melody_index))
                            self.melody_index += 1
                    elif self.args.audio_mode == 'synth' and self.notes:
                        if self.melody_index < len(self.notes):
                            self.sound_events.append((self.sim_time, 'note', self.notes[self.melody_index]))
                            self.melody_index += 1
                        elif self.args.melody_loop:
                            self.melody_index = 0
                            self.sound_events.append((self.sim_time, 'note', self.notes[self.melody_index]))
                            self.melody_index += 1
                if self.runtime_state.get('ball_color_mode', self.ball_color_mode) == 'random':
                    ball.color = random_vivid_bgr(self.rng)
                ball.target_radius += self.runtime_state['growth'] * self.scale
                speed_now = length(ball.vel)
                self.runtime_state['wall_restitution'] = min(1.2, self.runtime_state['wall_restitution'] + self.runtime_state['bounce_growth'])
                if speed_now > 1e-09:
                    target = min(self.runtime_state['max_speed'] * self.scale, speed_now * self.runtime_state['speed_growth'])
                    ball.vel *= target / speed_now
                offset = ball.pos - self.center
                dist = length(offset)
                allowed = self.arena_radius - ball.radius
                if dist > allowed:
                    ball.pos = self.center + normalize(offset) * allowed
                ball.wall_hit_cooldown = 0.018
        if duplicate_targets:
            active = [b for b in self.balls if b.alive]
            clones = []
            # Capacity is based on the available disk area. Once no legal
            # position remains, multiplication stops instead of stacking balls.
            largest_radius = max((b.radius for b in active), default=self.base_radius)
            area_capacity = int((self.arena_radius / max(1.0, largest_radius * 1.08)) ** 2 * 0.72)
            capacity = max(1, min(self.max_dynamic_balls, area_capacity))
            for ball in duplicate_targets:
                if not ball.alive: continue
                # One spike hit adds exactly two balls to the current total.
                # They are spawned around the ball that was hit, rather than
                # teleporting new balls to the centre of the arena.
                for _spawn_index in range(2):
                    if len(active) + len(clones) >= capacity: break
                    radius = ball.radius
                    placed = None
                    local_distance = radius + ball.radius + 2.0
                    for _attempt in range(96):
                        angle = self.rng.uniform(0.0, math.tau)
                        candidate = ball.pos + np.array([math.cos(angle), math.sin(angle)]) * local_distance
                        offset = candidate - self.center
                        if length(offset) + radius > self.arena_radius - 1.0:
                            continue
                        if all(length(candidate - other.pos) >= radius + other.radius + 1.0 for other in self.balls + clones if other.alive):
                            placed = candidate
                            break
                    # If the local neighbourhood is packed, search the whole
                    # disk for the nearest legal pocket before stopping.
                    for _attempt in range(320) if placed is None else range(0):
                        angle = self.rng.uniform(0.0, math.tau)
                        radial = math.sqrt(self.rng.uniform(0.0, 1.0)) * max(0.0, self.arena_radius - radius - 1.0)
                        candidate = self.center + np.array([math.cos(angle), math.sin(angle)]) * radial
                        if all(length(candidate - other.pos) >= radius + other.radius + 1.0 for other in self.balls + clones if other.alive):
                            placed = candidate
                            break
                # Near capacity, random sampling can miss a small remaining
                # pocket. Sweep concentric rings before giving up so we only
                # stop when there is genuinely no legal position left.
                    if placed is None:
                        clearance = max(2.0, radius * 1.75)
                        max_radial = max(0.0, self.arena_radius - radius - 1.0)
                        for radial in np.arange(0.0, max_radial + 0.01, clearance):
                            samples = max(8, int(math.ceil(math.tau * max(1.0, radial) / clearance)))
                            for sample in range(samples):
                                angle = math.tau * sample / samples
                                candidate = self.center + np.array([math.cos(angle), math.sin(angle)]) * radial
                                if all(length(candidate - other.pos) >= radius + other.radius + 1.0 for other in self.balls + clones if other.alive):
                                    placed = candidate
                                    break
                            if placed is not None:
                                break
                    if placed is None: continue
                    clone = copy.deepcopy(ball)
                    clone.pos = placed
                    clone.vel = ball.vel.copy() * np.array([1.0, -1.0])
                    clone.spike_hit_cooldown = max(0.01, float(self.args.respawn_delay))
                    clones.append(self._apply_dynamic_spawn_color(clone))
            self.balls.extend(clones)
            if len(self.particles) > 900:
                self.particles = self.particles[-900:]
        if escaped_balls:
            for ball in escaped_balls:
                if not any(item is ball for item in self.balls): continue
                if len(self.balls) + 1 >= self.max_dynamic_balls: continue
                ball.escaped_arena = False
                ball.pos = self.center.copy()
                ball.vel = np.array([self.rng.uniform(-1, 1), -abs(self.rng.uniform(0.45, 1.0))], dtype=np.float64) * max(1.0, self.args.initial_speed * self.scale)
                clone = copy.deepcopy(ball)
                clone.pos = self.center.copy() + np.array([self.rng.uniform(-8, 8), self.rng.uniform(-8, 8)])
                clone.vel = ball.vel.copy() * np.array([-1.0, 1.0])
                self.balls.append(self._apply_dynamic_spawn_color(clone))
        if len(self.balls) > 1:
            dynamic_mode = getattr(self.args, 'spike_duplicate', 0) or getattr(self.args, 'escape_duplicate', 0)
            active_count = sum(1 for item in self.balls if item.alive)
            pair_iterations = (8 if active_count <= 32 else 3 if active_count <= 96 else 1) if dynamic_mode else 1
            for _ in range(pair_iterations):
                solve_ball_pairs(self.balls, restitution=self.runtime_state['wall_restitution'])
        # Pair separation can push a ball back through the arena wall. Run a
        # final boundary projection so multiplication never leaks outside.
        if getattr(self.args, 'spike_duplicate', 0) and not getattr(self.args, 'escape_duplicate', 0):
            for ball in self.balls:
                if not ball.alive: continue
                solve_ball_wall(ball, self.center, self.arena_radius, self.runtime_state['wall_restitution'], self.runtime_state['wall_friction'])
        if self.particles:
            update_particles(self.particles, self.dt, gravity)
        self.dt = configured_dt
        return self._sync_state()

    def advance_frame(self):
        active_count = sum(1 for item in self.balls if item.alive)
        dynamic_mode = getattr(self.args, 'spike_duplicate', 0) or getattr(self.args, 'escape_duplicate', 0)
        # Keep the original high-accuracy stepping for normal scenes. Dense
        # multiplication scenes use fewer micro-steps once the broad phase is
        # active; this prevents the preview/render loop from stalling at high
        # ball counts while wall projection still keeps every ball in bounds.
        frame_substeps = 2 if dynamic_mode and active_count > 96 else self.substeps
        frame_dt = 1.0 / self.FPS / frame_substeps
        for _ in range(frame_substeps):
            self.step(dt=frame_dt)
        if self.args.motion_trail:
            spacing_ratio = max(0.02, float(self.args.trail_stamp_spacing))
            for i, ball in enumerate(self.balls):
                if not ball.alive:
                    continue
                hue = (self.sim_time * self.args.trail_rainbow_speed + i / max(1, self.args.ball_count)) % 1.0
                ball.color = hsv_to_bgr(hue)
                moved = length(ball.pos - self.trail_last_pos[i])
                if moved >= max(1.0, ball.radius * spacing_ratio):
                    stamp_pos = tuple(np.round(ball.pos).astype(int))
                    stamp_radius = max(1, int(round(ball.radius)))
                    cv2.circle(self.trail_layer, stamp_pos, stamp_radius, ball.color, -1, cv2.LINE_AA)
                    cv2.circle(self.trail_layer, stamp_pos, stamp_radius, (248, 248, 248), max(1, int(round(ball.radius * 0.025))), cv2.LINE_AA)
                    self.trail_last_pos[i] = ball.pos.copy()
        self.frame_index += 1
        return self._sync_state()

    def draw_frame(self, width=None, height=None):
        img = np.zeros((self.H, self.W, 3), dtype=np.uint8)
        if self.args.motion_trail:
            img = cv2.add(img, self.trail_layer)
        c = tuple(np.round(self.center).astype(int))
        if self.args.rainbow_border:
            draw_rainbow_ring(img, self.center, self.arena_radius, self.sim_time * self.args.rainbow_speed % 1.0, self.ring_width, gap_position_deg=self.runtime_state['gap_position'] if self.runtime_state['gap_enabled'] else 0.0, gap_size_deg=self.runtime_state['gap_size'] if self.runtime_state['gap_enabled'] else 0.0)
        else:
            draw_plain_ring(img, self.center, self.arena_radius, (242, 242, 242), self.ring_width, gap_position_deg=self.args.gap_position, gap_size_deg=self.args.gap_size)
        self.spikes = get_spikes(self.center, self.arena_radius, self.rotation_angle, self.spike_depth, self.spike_half_width, self.runtime_state['spike_count'], gap_position_deg=self.runtime_state['gap_position'] if self.runtime_state['gap_enabled'] else 0.0, gap_size_deg=self.runtime_state['gap_size'] if self.runtime_state['gap_enabled'] else 0.0)
        for tri in self.spikes:
            draw_triangle(img, tri, (45, 45, 245))
        draw_particles(img, self.particles)
        alive_count = sum((1 for b in self.balls if b.alive))
        dense_scene = alive_count > 160
        for bi, ball in enumerate(self.balls):
            if ball.alive:
                draw_ball(img, ball, 1 if dense_scene else self.border_width, (not dense_scene) and bool(self.runtime_state.get('show_ball_numbers', self.args.show_ball_numbers)), parse_hex_color(self.args.ball_number_color), skin=self.ball_skins.get(bi))
        if self.args.show_hud:
            cv2.putText(img, f'BALLS {alive_count}', (24, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.7 * self.scale, (145, 145, 145), max(1, int(round(2 * self.scale))), cv2.LINE_AA)
            cv2.putText(img, f'NOTE {(self.melody_index + 1 if self.notes else 0)}', (24, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.55 * self.scale, (125, 125, 125), max(1, int(round(1 * self.scale))), cv2.LINE_AA)
        if getattr(self.args, 'escape_duplicate', 0) and (getattr(self.args, 'escape_hud', 0) or getattr(self.args, 'escape_countdown', 0)):
            hud = build_escape_hud_data(self.balls, self.sim_time, self.args.seconds)
            x = int(self.W * max(0.0, min(100.0, float(self.args.escape_hud_x))) / 100.0)
            y = int(self.H * max(0.0, min(100.0, float(self.args.escape_hud_y))) / 100.0)
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = max(0.55, 0.9 * self.scale)
            thickness = max(1, int(round(2 * self.scale)))
            if getattr(self.args, 'escape_hud', 0) and hud['counts']:
                pieces = []
                total_width = 0
                radius = max(6, int(round(9 * self.scale)))
                gap = max(8, int(round(12 * self.scale)))
                for color, count in hud['counts']:
                    text = f': {count}'
                    (tw, th), _ = cv2.getTextSize(text, font, font_scale, thickness)
                    width = radius * 2 + max(4, int(round(6 * self.scale))) + tw
                    pieces.append((color, text, width, th))
                    total_width += width + gap
                cursor = x - max(0, total_width - gap) // 2
                for color, text, width, th in pieces:
                    cy = y - max(1, th // 3)
                    cv2.circle(img, (cursor + radius, cy), radius, color, -1, cv2.LINE_AA)
                    cv2.circle(img, (cursor + radius, cy), radius, (245, 245, 245), max(1, thickness), cv2.LINE_AA)
                    cv2.putText(img, text, (cursor + radius * 2 + max(4, int(round(6 * self.scale))), y), font, font_scale, (245, 245, 245), thickness, cv2.LINE_AA)
                    cursor += width + gap
            if getattr(self.args, 'escape_countdown', 0):
                text = str(hud['countdown'])
                (tw, th), _ = cv2.getTextSize(text, font, font_scale * 1.35, thickness + 1)
                timer_y = y + max(34, int(round(48 * self.scale)))
                cv2.putText(img, text, (x - tw // 2, timer_y), font, font_scale * 1.35, (255, 255, 255), thickness + 1, cv2.LINE_AA)
        if width is not None or height is not None:
            img = cv2.resize(img, (int(width or self.W), int(height or self.H)), interpolation=cv2.INTER_AREA)
        return img
