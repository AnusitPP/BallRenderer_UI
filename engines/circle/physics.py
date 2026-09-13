import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import cv2
import mido
import numpy as np


DEFAULT_MELODY_NOTES = [
    80, 81, 81, 83, 81, 80, 81, 76,
    81, 83, 81, 80, 81, 83, 85, 86, 88, 83, 81, 80,
    81, 83, 81, 80, 81, 76,
    81, 83, 81, 80, 81, 76,
    81, 83, 81, 80, 81, 83, 85, 86, 88, 83, 80,
    81, 81, 80, 81, 76, 81, 81,
]


from core.models import Ball, Particle

def length(v):
    return float(np.linalg.norm(v))


def normalize(v):
    n = length(v)
    if n <= 1e-12:
        return np.array([1.0, 0.0], dtype=np.float64)
    return v / n


def clamp_speed(v, max_speed):
    n = length(v)
    if n <= max_speed or n <= 1e-12:
        return v
    return v * (max_speed / n)


def normalize_angle_deg(angle):
    return ((float(angle) + 180.0) % 360.0) - 180.0


def angle_in_gap_deg(angle_deg, gap_position_deg, gap_size_deg):
    size = max(0.0, min(359.9, float(gap_size_deg)))
    if size <= 0.0:
        return False
    delta = normalize_angle_deg(float(angle_deg) - float(gap_position_deg))
    return abs(delta) <= size * 0.5


def gap_chord_width(arena_radius, gap_size_deg):
    """Approximate straight-line width of a circular opening in pixels/units."""
    radius = max(0.0, float(arena_radius))
    size = max(0.0, min(359.9, float(gap_size_deg)))
    if radius <= 0.0 or size <= 0.0:
        return 0.0
    return 2.0 * radius * math.sin(math.radians(size) * 0.5)


def ball_fits_gap(ball_radius, arena_radius, gap_size_deg, clearance=0.0):
    """Return True when the ball diameter fits through the opening chord."""
    diameter = max(0.0, float(ball_radius)) * 2.0 + max(0.0, float(clearance))
    return diameter <= gap_chord_width(arena_radius, gap_size_deg) + 1e-9


def parse_ball_lives(value, count, default=10):
    items = []
    for raw in str(value or '').split(','):
        raw = raw.strip()
        if not raw:
            continue
        try:
            items.append(max(1, int(float(raw))))
        except ValueError:
            items.append(int(default))
    if not items:
        items = [int(default)]
    while len(items) < int(count):
        items.append(items[-1])
    return items[:int(count)]


def load_pattern_file(path):
    source = Path(path).expanduser()
    if not source.exists():
        raise FileNotFoundError(f"Pattern file not found: {source}")

    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Pattern JSON must be an object")

    defaults = data.get("defaults") or {}
    events = data.get("events") or []
    if not isinstance(defaults, dict):
        raise ValueError("Pattern 'defaults' must be an object")
    if not isinstance(events, list):
        raise ValueError("Pattern 'events' must be a list")

    normalized_events = []
    for item in events:
        if not isinstance(item, dict):
            continue
        event = dict(item)
        event["time"] = max(0.0, float(event.get("time", 0.0)))
        normalized_events.append(event)

    normalized_events.sort(key=lambda item: item["time"])
    return {
        "name": str(data.get("name", source.stem)),
        "defaults": defaults,
        "events": normalized_events,
    }


def apply_pattern_value(state, key, value):
    if key == "gap_enabled":
        state["gap_enabled"] = bool(value)
    elif key == "gap_size":
        state["gap_size"] = max(0.0, min(300.0, float(value)))
    elif key == "gap_position":
        state["gap_position"] = normalize_angle_deg(float(value))
    elif key == "spike_count":
        state["spike_count"] = max(0, min(12, int(value)))
    elif key == "rotation_speed":
        state["rotation_speed"] = float(value)
    elif key == "gravity":
        state["gravity"] = float(value)
    elif key == "speed_growth":
        state["speed_growth"] = max(1.0, float(value))
    elif key == "max_speed":
        state["max_speed"] = max(50.0, float(value))
    elif key == "wall_restitution":
        state["wall_restitution"] = float(value)
    elif key == "bounce_growth":
        state["bounce_growth"] = max(0.0, float(value))
    elif key == "wall_friction":
        state["wall_friction"] = max(0.0, float(value))
    elif key == "air_drag":
        state["air_drag"] = max(0.0, float(value))
    elif key == "growth":
        state["growth"] = max(0.0, float(value))
    elif key == "ball_color_mode":
        state["ball_color_mode"] = str(value)
    elif key == "show_ball_numbers":
        state["show_ball_numbers"] = bool(value)
    elif key == "spawn_ball_color":
        state["_spawn_ball_color"] = str(value)
    elif key == "spawn_ball_chance":
        state["_spawn_ball_chance"] = max(0.0, min(1.0, float(value)))
    elif key == "special_spawn_interval":
        state["special_spawn_interval"] = max(0, int(value))
    elif key == "special_spawn_color":
        state["special_spawn_color"] = str(value)


def apply_pattern_defaults(state, defaults):
    for key, value in (defaults or {}).items():
        apply_pattern_value(state, key, value)


def apply_pattern_events_up_to(state, events, next_index, sim_time):
    while next_index < len(events) and float(events[next_index].get("time", 0.0)) <= sim_time + 1e-9:
        event = events[next_index]
        for key, value in event.items():
            if key == "time":
                continue
            apply_pattern_value(state, key, value)
        next_index += 1
    return next_index


def is_ball_oversized(ball_radius, arena_radius, margin):
    """True when the ball has grown so large it should burst."""
    return float(ball_radius) >= max(0.0, float(arena_radius) - float(margin))


def grow_ball(ball, growth, arena_radius, margin):
    """Grow without a size cap and report whether it has reached burst size."""
    ball.radius += growth
    return is_ball_oversized(ball.radius, arena_radius, margin)


def hsv_to_bgr(h, s=1.0, v=1.0):
    h = float(h % 1.0)
    i = int(h * 6.0)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)
    i %= 6

    if i == 0:
        r, g, b = v, t, p
    elif i == 1:
        r, g, b = q, v, p
    elif i == 2:
        r, g, b = p, v, t
    elif i == 3:
        r, g, b = p, q, v
    elif i == 4:
        r, g, b = t, p, v
    else:
        r, g, b = v, p, q

    return (
        int(round(b * 255)),
        int(round(g * 255)),
        int(round(r * 255)),
    )


def random_vivid_bgr(rng):
    return hsv_to_bgr(rng.uniform(0.0, 1.0), 0.80, 1.0)


DEFAULT_BALL_COLORS = [
    "#ff4d4d",
    "#4da6ff",
    "#5cff7a",
    "#ffd84d",
    "#c77dff",
    "#ff7ad9",
    "#61e7ff",
    "#ff9f43",
]


def normalize_hex_color(value):
    value = str(value).strip()
    if not value.startswith("#"):
        value = "#" + value
    if len(value) != 7:
        raise ValueError(f"Invalid color: {value}")
    try:
        int(value[1:], 16)
    except ValueError as exc:
        raise ValueError(f"Invalid color: {value}") from exc
    return value.lower()


def hex_to_bgr(value):
    value = normalize_hex_color(value)
    r = int(value[1:3], 16)
    g = int(value[3:5], 16)
    b = int(value[5:7], 16)
    return (b, g, r)


def parse_ball_colors(value):
    if not value:
        return list(DEFAULT_BALL_COLORS)
    colors = []
    for item in str(value).split(","):
        item = item.strip()
        if item:
            colors.append(normalize_hex_color(item))
    return colors or list(DEFAULT_BALL_COLORS)


def resolve_ball_color(mode, colors, index, rng):
    if mode == "random":
        return random_vivid_bgr(rng)

    colors = colors or DEFAULT_BALL_COLORS
    if mode == "same":
        return hex_to_bgr(colors[0])

    # per-ball
    return hex_to_bgr(colors[index % len(colors)])


def hidden_process_kwargs():
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def closest_point_on_segment(p, a, b):
    ab = b - a
    denom = float(np.dot(ab, ab))
    if denom <= 1e-12:
        return a.copy()
    t = float(np.dot(p - a, ab) / denom)
    t = max(0.0, min(1.0, t))
    return a + t * ab


def point_in_triangle(p, a, b, c):
    def sign(p1, p2, p3):
        return (
            (p1[0] - p3[0]) * (p2[1] - p3[1])
            - (p2[0] - p3[0]) * (p1[1] - p3[1])
        )

    d1 = sign(p, a, b)
    d2 = sign(p, b, c)
    d3 = sign(p, c, a)
    has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (has_neg and has_pos)


def circle_hits_triangle(center, radius, tri):
    a, b, c = tri
    if point_in_triangle(center, a, b, c):
        return True

    r2 = radius * radius
    for p1, p2 in ((a, b), (b, c), (c, a)):
        q = closest_point_on_segment(center, p1, p2)
        d = center - q
        if float(np.dot(d, d)) <= r2:
            return True
    return False


def spike_triangle(center, arena_radius, angle, spike_depth, spike_half_width):
    radial = np.array([math.cos(angle), math.sin(angle)], dtype=np.float64)
    tangent = np.array([-math.sin(angle), math.cos(angle)], dtype=np.float64)
    base_center = center + radial * arena_radius
    base_a = base_center + tangent * spike_half_width
    base_b = base_center - tangent * spike_half_width
    tip = center + radial * (arena_radius - spike_depth)
    return np.array([base_a, base_b, tip], dtype=np.float64)


def get_spikes(
    center,
    arena_radius,
    rotation_angle,
    spike_depth,
    spike_half_width,
    spike_count=3,
    gap_position_deg=0.0,
    gap_size_deg=0.0,
):
    if spike_count <= 0:
        return []

    result = []
    for i in range(spike_count):
        angle = rotation_angle + (math.tau * i / spike_count)
        angle_deg = math.degrees(angle)
        if angle_in_gap_deg(angle_deg, gap_position_deg, gap_size_deg):
            continue
        result.append(
            spike_triangle(
                center,
                arena_radius,
                angle,
                spike_depth,
                spike_half_width,
            )
        )
    return result


def solve_ball_wall(
    ball,
    center,
    arena_radius,
    restitution,
    wall_friction,
    gap_position_deg=0.0,
    gap_size_deg=0.0,
):
    if getattr(ball, "escaped_arena", False):
        return False

    offset = ball.pos - center
    dist = length(offset)
    max_dist = arena_radius - ball.radius
    if dist <= max_dist:
        return False

    angle_deg = math.degrees(math.atan2(offset[1], offset[0]))
    if angle_in_gap_deg(angle_deg, gap_position_deg, gap_size_deg):
        if dist >= arena_radius + ball.radius * 0.35:
            ball.escaped_arena = True
        return False

    normal = normalize(offset)
    ball.pos = center + normal * max_dist

    vn = float(np.dot(ball.vel, normal))
    if vn <= 0.0:
        return False

    normal_vel = vn * normal
    tangent_vel = ball.vel - normal_vel
    tangent_vel *= max(0.0, 1.0 - wall_friction)
    ball.vel = -restitution * normal_vel + tangent_vel
    return True


def solve_ball_pairs(balls, restitution=0.985):
    active = [b for b in balls if b.alive]
    # The original all-pairs pass is ideal for the small legacy scenes. Once
    # multiplication creates many balls, use a uniform-grid broad phase so
    # each ball only checks nearby candidates instead of every other ball.
    if len(active) > 32:
        cell_size = max(2.0, max((float(b.radius) for b in active), default=2.0) * 2.2)
        grid = {}
        for index, ball in enumerate(active):
            key = (int(math.floor(ball.pos[0] / cell_size)), int(math.floor(ball.pos[1] / cell_size)))
            grid.setdefault(key, []).append(index)
        checked = set()
        for i, a in enumerate(active):
            cx = int(math.floor(a.pos[0] / cell_size))
            cy = int(math.floor(a.pos[1] / cell_size))
            for gx in range(cx - 1, cx + 2):
                for gy in range(cy - 1, cy + 2):
                    for j in grid.get((gx, gy), ()):
                        if j <= i or (i, j) in checked:
                            continue
                        checked.add((i, j))
                        b = active[j]
                        delta = b.pos - a.pos
                        dist_sq = float(np.dot(delta, delta))
                        min_dist = a.radius + b.radius
                        if dist_sq >= min_dist * min_dist:
                            continue
                        if dist_sq <= 1e-12:
                            normal = np.array([1.0, 0.0], dtype=np.float64)
                            dist = 0.0
                        else:
                            dist = math.sqrt(dist_sq)
                            normal = delta / dist
                        ma = max(1.0, a.radius * a.radius)
                        mb = max(1.0, b.radius * b.radius)
                        inv_ma = 1.0 / ma
                        inv_mb = 1.0 / mb
                        inv_sum = inv_ma + inv_mb
                        penetration = min_dist - dist
                        a.pos -= normal * penetration * (inv_ma / inv_sum)
                        b.pos += normal * penetration * (inv_mb / inv_sum)
                        rel = b.vel - a.vel
                        vel_n = float(np.dot(rel, normal))
                        if vel_n < 0.0:
                            impulse_mag = -(1.0 + restitution) * vel_n / inv_sum
                            impulse = impulse_mag * normal
                            a.vel -= impulse * inv_ma
                            b.vel += impulse * inv_mb
        return
    for i in range(len(active)):
        a = active[i]
        for j in range(i + 1, len(active)):
            b = active[j]
            delta = b.pos - a.pos
            dist_sq = float(np.dot(delta, delta))
            min_dist = a.radius + b.radius
            if dist_sq >= min_dist * min_dist:
                continue

            if dist_sq <= 1e-12:
                normal = np.array([1.0, 0.0], dtype=np.float64)
                dist = 0.0
            else:
                dist = math.sqrt(dist_sq)
                normal = delta / dist

            ma = max(1.0, a.radius * a.radius)
            mb = max(1.0, b.radius * b.radius)
            inv_ma = 1.0 / ma
            inv_mb = 1.0 / mb
            inv_sum = inv_ma + inv_mb

            penetration = min_dist - dist
            a.pos -= normal * penetration * (inv_ma / inv_sum)
            b.pos += normal * penetration * (inv_mb / inv_sum)

            rel = b.vel - a.vel
            vel_n = float(np.dot(rel, normal))
            if vel_n >= 0.0:
                continue

            impulse_mag = -(1.0 + restitution) * vel_n / inv_sum
            impulse = impulse_mag * normal
            a.vel -= impulse * inv_ma
            b.vel += impulse * inv_mb


def spawn_ball(
    center,
    arena_radius,
    base_radius,
    rng,
    index=0,
    total=1,
    color=None,
    initial_angle_deg=None,
    initial_speed=None,
    max_life=10,
    current_life=None,
    center_spawn=False,
):
    if initial_angle_deg is None:
        if total <= 1:
            ang = rng.uniform(0.0, math.tau)
        else:
            ang = (math.tau * index / total) + rng.uniform(-0.08, 0.08)
        move_angle = ang + math.pi * 0.5 + rng.uniform(-0.65, 0.65)
    else:
        move_angle = math.radians(float(initial_angle_deg))
        if total > 1:
            move_angle += math.tau * index / total
        ang = move_angle - math.pi * 0.5

    spawn_r = 0.0 if center_spawn else arena_radius * (0.10 if total <= 2 else 0.20)
    pos = center + np.array(
        [math.cos(ang) * spawn_r, math.sin(ang) * spawn_r],
        dtype=np.float64,
    )

    speed = float(initial_speed) if initial_speed is not None else rng.uniform(520.0, 670.0)
    vel = np.array(
        [math.cos(move_angle) * speed, math.sin(move_angle) * speed],
        dtype=np.float64,
    )

    return Ball(
        pos=pos,
        vel=vel,
        radius=base_radius,
        color=color if color is not None else random_vivid_bgr(rng),
        alive=True,
        life=max(1, int(max_life if current_life is None else current_life)),
        max_life=max(1, int(max_life)),
    )


def apply_spike_damage(ball, center, arena_radius, cooldown=0.20):
    if not ball.alive or ball.eliminated or ball.spike_hit_cooldown > 0.0:
        return False

    ball.life = max(0, int(ball.life) - 1)
    ball.spike_hit_cooldown = max(0.01, float(cooldown))

    if ball.life <= 0:
        ball.alive = False
        ball.eliminated = True
        ball.respawn_timer = 0.0
        return True

    ball.alive = False
    ball.respawn_timer = max(0.01, float(cooldown))
    return False


def create_particles(ball, rng, min_count=22, max_count=105):
    size_ratio = max(1.0, ball.radius / 22.0)
    count = int(min(max_count, max(min_count, min_count * (size_ratio ** 1.30))))
    result = []

    for _ in range(count):
        ang = rng.uniform(0.0, math.tau)
        rr = ball.radius * math.sqrt(rng.uniform(0.0, 1.0)) * 0.70
        offset = np.array([math.cos(ang) * rr, math.sin(ang) * rr], dtype=np.float64)
        outward = normalize(offset) if length(offset) > 1e-9 else np.array([1.0, 0.0])

        vel = (
            outward * rng.uniform(230.0, 620.0)
            + ball.vel * rng.uniform(0.08, 0.20)
            + np.array([rng.uniform(-45.0, 45.0), rng.uniform(-90.0, 20.0)])
        )

        radius = rng.uniform(
            max(1.7, ball.radius * 0.028),
            max(2.8, ball.radius * 0.055),
        )

        result.append(
            Particle(
                pos=ball.pos + offset,
                vel=vel,
                radius=radius,
                life=rng.uniform(0.58, 1.08),
            )
        )

    return result


def update_particles(particles, dt, gravity):
    survivors = []
    for p in particles:
        if not p.alive:
            continue

        p.life -= dt
        if p.life <= 0.0:
            continue

        p.vel += gravity * dt
        p.vel *= math.exp(-1.05 * dt)
        p.pos += p.vel * dt
        survivors.append(p)

    particles[:] = survivors







from audio.melody import extract_midi_melody, load_melody_file
