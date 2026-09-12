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


@dataclass
class Ball:
    pos: np.ndarray
    vel: np.ndarray
    radius: float
    color: tuple
    alive: bool = True
    respawn_timer: float = 0.0
    wall_hit_cooldown: float = 0.0
    life: int = 10
    max_life: int = 10
    spike_hit_cooldown: float = 0.0
    eliminated: bool = False
    escaped_arena: bool = False
    target_radius: float = 0.0


@dataclass
class Particle:
    pos: np.ndarray
    vel: np.ndarray
    radius: float
    life: float
    alive: bool = True


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
    elif key == "wall_friction":
        state["wall_friction"] = max(0.0, float(value))
    elif key == "air_drag":
        state["air_drag"] = max(0.0, float(value))


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


def extract_midi_melody(path):
    midi = mido.MidiFile(str(path))
    absolute_tick = 0
    grouped = {}

    for msg in mido.merge_tracks(midi.tracks):
        absolute_tick += int(msg.time)
        if msg.type == "note_on" and getattr(msg, "velocity", 0) > 0:
            grouped.setdefault(absolute_tick, []).append(int(msg.note))

    return [max(grouped[tick]) for tick in sorted(grouped)]


def load_melody_file(path):
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        notes = [int(n) for n in data.get("notes", [])]
        if not notes:
            raise ValueError(f"No notes found in {path.name}")

        return {
            "name": str(data.get("name", path.stem)),
            "notes": notes,
            "instrument": str(data.get("instrument", "piano")).lower(),
            "volume": float(data.get("volume", 0.80)),
            "loop": bool(data.get("loop", True)),
            "restart_on_break": bool(data.get("restart_on_break", True)),
        }

    if suffix in (".mid", ".midi"):
        notes = extract_midi_melody(path)
        if not notes:
            raise ValueError(f"No note_on events found in {path.name}")

        return {
            "name": path.stem,
            "notes": notes,
            "instrument": "piano",
            "volume": 0.80,
            "loop": True,
            "restart_on_break": True,
        }

    raise ValueError("Melody file must be .json, .mid, or .midi")


def midi_to_hz(note):
    return 440.0 * (2.0 ** ((float(note) - 69.0) / 12.0))


def synth_note(note, duration, sample_rate, instrument, volume):
    f = midi_to_hz(note)
    n = max(1, int(duration * sample_rate))
    x = np.arange(n, dtype=np.float64) / sample_rate

    attack = np.minimum(1.0, x / 0.006)

    if instrument == "pluck":
        env = attack * np.exp(-x * 13.0)
        sig = (
            0.76 * np.sin(2 * np.pi * f * x)
            + 0.16 * np.sin(2 * np.pi * f * 2.0 * x)
            + 0.08 * np.sin(2 * np.pi * f * 3.0 * x)
        )
    elif instrument == "bell":
        env = attack * np.exp(-x * 4.8)
        sig = (
            0.58 * np.sin(2 * np.pi * f * x)
            + 0.23 * np.sin(2 * np.pi * f * 2.01 * x)
            + 0.13 * np.sin(2 * np.pi * f * 3.98 * x)
            + 0.06 * np.sin(2 * np.pi * f * 6.05 * x)
        )
    elif instrument == "synth":
        env = attack * np.exp(-x * 6.5)
        sig = (
            0.55 * np.sin(2 * np.pi * f * x)
            + 0.30 * np.sin(2 * np.pi * f * 1.005 * x)
            + 0.15 * np.sin(2 * np.pi * f * 2.0 * x)
        )
    else:  # piano
        env = attack * np.exp(-x * 7.0)
        sig = (
            0.68 * np.sin(2 * np.pi * f * x)
            + 0.14 * np.sin(2 * np.pi * f * 2.0 * x)
            + 0.06 * np.sin(2 * np.pi * f * 3.0 * x)
            + 0.12 * np.sin(2 * np.pi * f * 1.003 * x)
        )

    return sig * env * float(volume)


def make_audio(events, seconds, sample_rate, out_wav, instrument="piano", note_volume=0.8):
    total = int(seconds * sample_rate)
    audio = np.zeros(total, dtype=np.float64)

    for event in events:
        t, kind, value = event
        start = int(float(t) * sample_rate)
        if start >= total:
            continue

        if kind == "note":
            sig = synth_note(
                int(value),
                0.26 if instrument == "bell" else 0.22,
                sample_rate,
                instrument,
                note_volume * 0.18,
            )
        elif kind == "spike":
            n = int(0.14 * sample_rate)
            x = np.arange(n, dtype=np.float64) / sample_rate
            env = np.exp(-x * 24.0)
            sig = (
                0.55 * np.sin(2 * np.pi * 120.0 * x)
                + 0.45 * np.sin(2 * np.pi * 70.0 * x)
            ) * env * 0.20
        else:
            n = int(0.06 * sample_rate)
            x = np.arange(n, dtype=np.float64) / sample_rate
            sig = np.sin(2 * np.pi * 660.0 * x) * np.exp(-x * 35.0) * 0.06

        n = min(len(sig), total - start)
        if n > 0:
            audio[start:start + n] += sig[:n]

    audio = np.clip(audio, -1.0, 1.0)
    pcm = (audio * 32767).astype(np.int16)

    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())



def read_wav_mono(path):
    """Read 16-bit PCM WAV as mono float32 in [-1, 1]."""
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        sample_rate = wf.getframerate()
        frame_count = wf.getnframes()
        raw = wf.readframes(frame_count)

    if sample_width != 2:
        raise ValueError("Decoded source WAV must be 16-bit PCM")

    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    if channels > 1:
        pcm = pcm.reshape(-1, channels).mean(axis=1)

    return pcm / 32768.0, int(sample_rate)


def detect_audio_onsets(audio, sample_rate, min_gap_seconds=0.09):
    """
    Lightweight onset detector for extracting sequential song snippets.
    Uses short-time RMS rises, so it needs no extra audio-analysis package.
    """
    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    if x.size == 0:
        return []

    sr = max(1, int(sample_rate))
    frame = max(8, int(sr * 0.020))
    hop = max(1, int(sr * 0.005))

    # Efficient moving RMS using cumulative sums.
    sq = x.astype(np.float64) ** 2
    csum = np.concatenate(([0.0], np.cumsum(sq)))
    starts = np.arange(0, max(1, x.size - frame + 1), hop, dtype=np.int64)
    ends = np.minimum(starts + frame, x.size)
    lengths = np.maximum(1, ends - starts)
    energy = (csum[ends] - csum[starts]) / lengths
    rms = np.sqrt(np.maximum(energy, 0.0))

    if rms.size < 3:
        return [0]

    novelty = np.maximum(0.0, np.diff(rms, prepend=rms[0]))
    positive = novelty[novelty > 0]

    if positive.size == 0:
        return [0]

    median = float(np.median(positive))
    mad = float(np.median(np.abs(positive - median))) + 1e-12
    percentile = float(np.percentile(positive, 70))
    threshold = max(median + 0.6 * mad, percentile * 0.75)
    threshold = min(threshold, float(np.max(positive)) * 0.85)

    candidates = []
    for i in range(1, novelty.size - 1):
        if (
            novelty[i] >= threshold
            and novelty[i] >= novelty[i - 1]
            and novelty[i] >= novelty[i + 1]
        ):
            candidates.append((i, float(novelty[i])))

    if not candidates:
        strongest = int(np.argmax(novelty))
        return [int(starts[min(strongest, len(starts) - 1)])]

    min_gap_frames = max(1, int(round(min_gap_seconds * sr / hop)))
    selected = []
    group = []

    for item in candidates:
        if not group or item[0] - group[-1][0] <= min_gap_frames:
            group.append(item)
        else:
            selected.append(max(group, key=lambda pair: pair[1]))
            group = [item]

    if group:
        selected.append(max(group, key=lambda pair: pair[1]))

    positions = [
        int(starts[min(index, len(starts) - 1)])
        for index, _strength in selected
    ]

    # Avoid a useless leading near-silence trigger unless it is the only one.
    if len(positions) > 1 and positions[0] < int(sr * 0.03):
        positions = positions[1:]

    return positions or [0]


def extract_bounce_samples(audio, sample_rate, onset_positions, sample_ms=240):
    """Extract fixed-length, softly faded snippets from detected attacks."""
    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    sr = max(1, int(sample_rate))
    sample_len = max(16, int(round(sr * max(40, int(sample_ms)) / 1000.0)))
    pre_roll = int(round(sr * 0.012))
    fade_len = min(sample_len // 4, max(1, int(round(sr * 0.012))))

    result = []
    for onset in onset_positions:
        start = max(0, int(onset) - pre_roll)
        chunk = np.zeros(sample_len, dtype=np.float32)
        available = min(sample_len, max(0, x.size - start))
        if available > 0:
            chunk[:available] = x[start:start + available]

        if fade_len > 0:
            fade_in = np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
            fade_out = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
            chunk[:fade_len] *= fade_in
            chunk[-fade_len:] *= fade_out

        peak = float(np.max(np.abs(chunk))) if chunk.size else 0.0
        if peak > 1.0:
            chunk /= peak

        result.append(chunk)

    return result


def mix_bounce_sample_events(
    events,
    seconds,
    sample_rate,
    source_samples,
    volume=0.85,
):
    total = max(1, int(round(float(seconds) * int(sample_rate))))
    output = np.zeros(total, dtype=np.float32)

    if not source_samples:
        return output

    for t, kind, value in events:
        if kind != "sample":
            continue

        start = int(round(float(t) * sample_rate))
        if start >= total:
            continue

        sample = source_samples[int(value) % len(source_samples)]
        n = min(len(sample), total - start)
        if n > 0:
            output[start:start + n] += sample[:n] * float(volume)

    return output


def decode_audio_to_wav(ffmpeg_path, source_path, out_wav, sample_rate):
    cmd = [
        str(ffmpeg_path),
        "-y",
        "-hide_banner",
        "-loglevel", "error",
        "-i", str(source_path),
        "-vn",
        "-ac", "1",
        "-ar", str(int(sample_rate)),
        "-c:a", "pcm_s16le",
        str(out_wav),
    ]
    subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **hidden_process_kwargs(),
    )


def prepare_bounce_samples(
    ffmpeg_path,
    source_path,
    temp_wav,
    sample_rate,
    sample_ms,
):
    decode_audio_to_wav(
        ffmpeg_path,
        source_path,
        temp_wav,
        sample_rate,
    )
    try:
        audio, decoded_sr = read_wav_mono(temp_wav)
        onsets = detect_audio_onsets(
            audio,
            decoded_sr,
            min_gap_seconds=max(0.055, min(0.14, sample_ms / 1000.0 * 0.40)),
        )
        samples = extract_bounce_samples(
            audio,
            decoded_sr,
            onsets,
            sample_ms=sample_ms,
        )
        return samples
    finally:
        Path(temp_wav).unlink(missing_ok=True)


def write_float_audio_wav(audio, sample_rate, out_wav):
    audio = np.asarray(audio, dtype=np.float32)
    audio = np.clip(audio, -1.0, 1.0)
    pcm = (audio * 32767.0).astype(np.int16)

    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm.tobytes())


def make_bounce_sample_audio(
    events,
    seconds,
    sample_rate,
    out_wav,
    source_samples,
    source_volume=0.85,
):
    audio = mix_bounce_sample_events(
        events,
        seconds,
        sample_rate,
        source_samples,
        volume=source_volume,
    )

    # Keep the existing synthesized crash cue for spike / oversize explosions.
    for t, kind, _value in events:
        if kind != "spike":
            continue

        start = int(float(t) * sample_rate)
        if start >= len(audio):
            continue

        n = int(0.14 * sample_rate)
        x = np.arange(n, dtype=np.float64) / sample_rate
        env = np.exp(-x * 24.0)
        sig = (
            0.55 * np.sin(2 * np.pi * 120.0 * x)
            + 0.45 * np.sin(2 * np.pi * 70.0 * x)
        ) * env * 0.16
        count = min(len(sig), len(audio) - start)
        if count > 0:
            audio[start:start + count] += sig[:count].astype(np.float32)

    write_float_audio_wav(audio, sample_rate, out_wav)


def _append_video_encoder_options(cmd, use_nvenc):
    if use_nvenc:
        cmd += [
            "-c:v", "h264_nvenc",
            "-preset", "p7",
            "-tune", "hq",
            "-rc", "vbr",
            "-cq", "15",
            "-b:v", "0",
        ]
    else:
        cmd += [
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "15",
        ]
    return cmd


def build_original_audio_ffmpeg_cmd(
    ffmpeg_path,
    silent_video,
    source_audio,
    final_out,
    use_nvenc,
    source_volume=1.0,
):
    cmd = [
        str(ffmpeg_path),
        "-y",
        "-i", str(silent_video),
        "-i", str(source_audio),
        "-map", "0:v:0",
        "-map", "1:a:0",
    ]
    _append_video_encoder_options(cmd, use_nvenc)

    if abs(float(source_volume) - 1.0) > 1e-6:
        cmd += ["-filter:a", f"volume={float(source_volume):.4f}"]

    cmd += [
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-progress", "pipe:1",
        "-nostats",
        str(final_out),
    ]
    return cmd


def find_ffmpeg(search_root=None):
    roots = []

    if search_root is not None:
        roots.append(Path(search_root))
    else:
        found = shutil.which("ffmpeg")
        if found:
            return found

        if os.name == "nt":
            userprofile = os.environ.get("USERPROFILE")
            if userprofile:
                roots.append(Path(userprofile) / "Downloads")

    for root in roots:
        if not root.exists():
            continue

        direct = root / "bin" / "ffmpeg.exe"
        if direct.exists():
            return str(direct)

        for exe in sorted(root.glob("ffmpeg-*/bin/ffmpeg.exe"), reverse=True):
            if exe.exists():
                return str(exe)

    if search_root is not None:
        return shutil.which("ffmpeg")

    return None


def ffmpeg_has_nvenc_from_text(text):
    return "h264_nvenc" in text


def ffmpeg_has_nvenc(ffmpeg_path):
    try:
        result = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            **hidden_process_kwargs(),
        )
        combined = (result.stdout or "") + "\n" + (result.stderr or "")
        return ffmpeg_has_nvenc_from_text(combined)
    except Exception:
        return False


def build_ffmpeg_cmd(ffmpeg_path, silent_video, audio_wav, final_out, use_nvenc):
    cmd = [
        ffmpeg_path,
        "-y",
        "-i", str(silent_video),
        "-i", str(audio_wav),
    ]

    _append_video_encoder_options(cmd, use_nvenc)

    cmd += [
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "160k",
        "-shortest",
        "-progress", "pipe:1",
        "-nostats",
        str(final_out),
    ]
    return cmd


def report_progress(value, stage):
    value = max(0.0, min(100.0, float(value)))
    print(f"APP_PROGRESS {value:.2f} {stage}", flush=True)


def run_ffmpeg_with_progress(cmd, duration_seconds, progress_start=92.0, progress_end=100.0):
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        universal_newlines=True,
        **hidden_process_kwargs(),
    )

    last = progress_start
    report_progress(last, "Muxing audio/video")

    for raw in proc.stdout:
        line = raw.strip()
        seconds = None

        if line.startswith("out_time_us="):
            try:
                seconds = int(line.split("=", 1)[1]) / 1_000_000.0
            except ValueError:
                pass
        elif line.startswith("out_time_ms="):
            try:
                seconds = int(line.split("=", 1)[1]) / 1_000_000.0
            except ValueError:
                pass

        if seconds is not None and duration_seconds > 0:
            ratio = max(0.0, min(1.0, seconds / duration_seconds))
            value = progress_start + ratio * (progress_end - progress_start)
            if value >= last:
                last = value
                report_progress(value, "Muxing audio/video")

    code = proc.wait()
    if code != 0:
        raise subprocess.CalledProcessError(code, cmd)

    report_progress(progress_end, "Complete")


def draw_rainbow_ring(
    img,
    center,
    radius,
    rotation_phase,
    thickness,
    gap_position_deg=0.0,
    gap_size_deg=0.0,
):
    c = np.asarray(center, dtype=np.float64)
    segments = 180
    step = math.tau / segments

    for i in range(segments):
        a0 = i * step
        a1 = (i + 1.25) * step
        mid_deg = math.degrees((a0 + a1) * 0.5)
        if angle_in_gap_deg(mid_deg, gap_position_deg, gap_size_deg):
            continue
        hue = (i / segments + rotation_phase) % 1.0
        color = hsv_to_bgr(hue, 0.92, 1.0)

        p0 = c + np.array([math.cos(a0), math.sin(a0)]) * radius
        p1 = c + np.array([math.cos(a1), math.sin(a1)]) * radius

        cv2.line(
            img,
            tuple(np.round(p0).astype(int)),
            tuple(np.round(p1).astype(int)),
            color,
            thickness,
            cv2.LINE_AA,
        )


def draw_plain_ring(
    img,
    center,
    radius,
    color,
    thickness,
    gap_position_deg=0.0,
    gap_size_deg=0.0,
):
    c = np.asarray(center, dtype=np.float64)
    segments = 180
    step = math.tau / segments
    for i in range(segments):
        a0 = i * step
        a1 = (i + 1.25) * step
        mid_deg = math.degrees((a0 + a1) * 0.5)
        if angle_in_gap_deg(mid_deg, gap_position_deg, gap_size_deg):
            continue
        p0 = c + np.array([math.cos(a0), math.sin(a0)]) * radius
        p1 = c + np.array([math.cos(a1), math.sin(a1)]) * radius
        cv2.line(
            img,
            tuple(np.round(p0).astype(int)),
            tuple(np.round(p1).astype(int)),
            color,
            thickness,
            cv2.LINE_AA,
        )


def draw_triangle(img, tri, color):
    pts = np.round(tri).astype(np.int32).reshape((-1, 1, 2))
    cv2.fillPoly(img, [pts], color, lineType=cv2.LINE_AA)


def parse_hex_color(value):
    value = str(value).strip().lstrip("#")
    if len(value) != 6:
        return (255, 255, 255)
    try:
        r, g, b = int(value[0:2],16), int(value[2:4],16), int(value[4:6],16)
    except ValueError:
        return (255, 255, 255)
    return (b, g, r)


def draw_skin_circle(img, skin, cx, cy, r):
    """Draw a skin image clipped to a circle. Returns True if drawn."""
    if skin is None:
        return False
    size = max(2, int(2 * r))
    im = cv2.resize(skin, (size, size), interpolation=cv2.INTER_AREA)
    yy1 = max(0, cy - r)
    yy2 = min(img.shape[0], cy + r)
    xx1 = max(0, cx - r)
    xx2 = min(img.shape[1], cx + r)
    if yy2 <= yy1 or xx2 <= xx1:
        return False
    sy1 = yy1 - (cy - r)
    sy2 = sy1 + (yy2 - yy1)
    sx1 = xx1 - (cx - r)
    sx2 = sx1 + (xx2 - xx1)
    crop = im[sy1:sy2, sx1:sx2]
    mask = np.zeros((crop.shape[0], crop.shape[1]), np.uint8)
    cv2.circle(mask, (crop.shape[1] // 2, crop.shape[0] // 2), min(crop.shape[:2]) // 2, 255, -1)
    if len(crop.shape) == 3 and crop.shape[2] == 4:
        alpha = (crop[:, :, 3].astype(np.float32) / 255.0) * (mask.astype(np.float32) / 255.0)
        rgb = crop[:, :, :3]
    else:
        alpha = mask.astype(np.float32) / 255.0
        rgb = crop[:, :, :3] if len(crop.shape) == 3 else cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
    roi = img[yy1:yy2, xx1:xx2]
    img[yy1:yy2, xx1:xx2] = (rgb * alpha[:, :, None] + roi * (1 - alpha[:, :, None])).astype(np.uint8)
    return True


def load_ball_images(paths_str):
    """Parse comma-separated image paths and load them. Returns dict of {index: cv2_image}."""
    result = {}
    if not paths_str:
        return result
    paths = paths_str.split(",")
    for i, p in enumerate(paths):
        p = p.strip()
        if not p or not os.path.isfile(p):
            continue
        im = cv2.imread(p, cv2.IMREAD_UNCHANGED)
        if im is not None:
            result[i] = im
    return result


def draw_ball(img, ball, border_width, show_number=True, number_color=(255,255,255), skin=None):

    p = tuple(np.round(ball.pos).astype(int))
    rr = max(1, int(round(ball.radius)))

    # Try drawing skin first
    if skin is not None:
        drawn = draw_skin_circle(img, skin, p[0], p[1], rr)
        if drawn:
            if show_number:
                _draw_ball_number(img, ball, number_color)
            return

    cv2.circle(img, p, rr, ball.color, -1, cv2.LINE_AA)
    cv2.circle(img, p, rr, (248, 248, 248), border_width, cv2.LINE_AA)

    if not show_number:
        return
    _draw_ball_number(img, ball, number_color)


def _draw_ball_number(img, ball, number_color):
    label = str(int(ball.life))
    font_scale = max(0.24, min(1.2, ball.radius / 42.0))
    text_thickness = max(1, int(round(ball.radius / 18.0)))
    (tw, th), baseline = cv2.getTextSize(
        label,
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        text_thickness,
    )
    text_org = (
        int(round(ball.pos[0] - tw * 0.5)),
        int(round(ball.pos[1] + (th - baseline) * 0.5)),
    )
    cv2.putText(
        img,
        label,
        text_org,
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        (20, 20, 20),
        text_thickness + 2,
        cv2.LINE_AA,
    )
    cv2.putText(
        img,
        label,
        text_org,
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        number_color,
        text_thickness,
        cv2.LINE_AA,
    )


def draw_particles(img, particles):
    for p in particles:
        alpha = max(0.0, min(1.0, p.life / 0.50))
        brightness = int(100 + 155 * alpha)
        rr = max(1, int(round(p.radius * (0.50 + 0.50 * alpha))))
        cv2.circle(
            img,
            tuple(np.round(p.pos).astype(int)),
            rr,
            (brightness, brightness, brightness),
            -1,
            cv2.LINE_AA,
        )


def build_arg_parser():
    ap = argparse.ArgumentParser()

    ap.add_argument("--out", default="tiktok_final.mp4")
    ap.add_argument("--fps", type=int, default=240)
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1920)
    ap.add_argument("--substeps", type=int, default=6)

    ap.add_argument("--initial-angle", type=float, default=35.0)
    ap.add_argument("--initial-speed", type=float, default=600.0)
    ap.add_argument("--arena-scale", type=float, default=1.0)
    ap.add_argument("--gap-enabled", type=int, choices=(0, 1), default=0)
    ap.add_argument("--gap-size", type=float, default=45.0)
    ap.add_argument("--gap-position", type=float, default=-90.0)

    ap.add_argument("--gravity", type=float, default=900.0)
    ap.add_argument("--wall-restitution", type=float, default=0.985)
    ap.add_argument("--wall-friction", type=float, default=0.0006)
    ap.add_argument("--air-drag", type=float, default=0.00018)
    ap.add_argument("--max-speed", type=float, default=1750.0)
    ap.add_argument("--speed-growth", type=float, default=1.004)

    ap.add_argument("--ball-count", type=int, default=1)
    ap.add_argument("--ball-lives", default="10")
    ap.add_argument("--pattern-file", default="")
    ap.add_argument(
        "--ball-color-mode",
        choices=("random", "same", "per-ball"),
        default=None,
    )
    ap.add_argument(
        "--ball-colors",
        default=",".join(DEFAULT_BALL_COLORS),
    )
    ap.add_argument("--base-radius", type=float, default=24.0)
    ap.add_argument("--growth", type=float, default=5.0)
    ap.add_argument("--max-ball-radius", type=float, default=None, help=argparse.SUPPRESS)
    ap.add_argument("--smooth-growth-speed", type=float, default=24.0)
    ap.add_argument("--motion-trail", type=int, choices=(0, 1), default=0)
    ap.add_argument("--trail-rainbow-speed", type=float, default=0.11)
    ap.add_argument("--trail-stamp-spacing", type=float, default=0.16)

    ap.add_argument("--spike-count", type=int, default=3)
    ap.add_argument("--rotation-speed", type=float, default=0.85)
    ap.add_argument("--spike-depth", type=float, default=34.0)
    ap.add_argument("--spike-width", type=float, default=15.0)
    ap.add_argument("--respawn-delay", type=float, default=0.12)

    ap.add_argument("--rainbow-speed", type=float, default=0.12)
    ap.add_argument("--rainbow-border", type=int, choices=(0, 1), default=1)
    ap.add_argument("--random-ball-color", type=int, choices=(0, 1), default=1)
    ap.add_argument("--show-hud", type=int, choices=(0, 1), default=0)
    ap.add_argument("--show-ball-numbers", type=int, choices=(0, 1), default=1)
    ap.add_argument("--ball-number-color", default="#ffffff")

    ap.add_argument("--audio", type=int, choices=(0, 1), default=1)
    ap.add_argument(
        "--audio-mode",
        choices=("synth", "original", "bounce-samples"),
        default="synth",
    )
    ap.add_argument("--audio-file", default="")
    ap.add_argument("--source-volume", type=float, default=0.85)
    ap.add_argument("--sample-ms", type=int, default=240)
    ap.add_argument("--melody-file", default="")
    ap.add_argument("--instrument", choices=("piano", "pluck", "bell", "synth"), default="piano")
    ap.add_argument("--note-volume", type=float, default=0.80)
    ap.add_argument("--transpose", type=int, default=0)
    ap.add_argument("--melody-loop", type=int, choices=(0, 1), default=1)
    ap.add_argument("--restart-melody-on-break", type=int, choices=(0, 1), default=1)
    ap.add_argument("--sample-rate", type=int, default=48000)

    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--ball-images", default="")
    return ap


def main(argv=None):
    args = build_arg_parser().parse_args(argv)

    args.ball_count = max(1, min(8, int(args.ball_count)))
    args.spike_count = max(0, min(12, int(args.spike_count)))
    args.gap_size = max(0.0, min(300.0, float(args.gap_size))) if args.gap_enabled else 0.0
    args.gap_position = normalize_angle_deg(args.gap_position)
    ball_lives = parse_ball_lives(args.ball_lives, args.ball_count, default=10)
    args.note_volume = max(0.0, min(1.5, float(args.note_volume)))
    args.source_volume = max(0.0, min(2.0, float(args.source_volume)))
    args.sample_ms = max(80, min(800, int(args.sample_ms)))

    # Backward compatibility: old CLI only had --random-ball-color.
    ball_color_mode = args.ball_color_mode
    if ball_color_mode is None:
        ball_color_mode = "random" if args.random_ball_color else "same"
    ball_colors = parse_ball_colors(args.ball_colors)

    # Load optional ball skin images
    ball_skins = load_ball_images(getattr(args, "ball_images", ""))

    rng = np.random.default_rng(args.seed)

    runtime_state = {
        "gap_enabled": bool(args.gap_enabled),
        "gap_size": float(args.gap_size),
        "gap_position": float(args.gap_position),
        "spike_count": int(args.spike_count),
        "rotation_speed": float(args.rotation_speed),
        "gravity": float(args.gravity),
        "speed_growth": float(args.speed_growth),
        "max_speed": float(args.max_speed),
        "wall_restitution": float(args.wall_restitution),
        "wall_friction": float(args.wall_friction),
        "air_drag": float(args.air_drag),
    }
    pattern_name = "Manual"
    pattern_events = []
    pattern_index = 0
    if args.pattern_file:
        loaded_pattern = load_pattern_file(args.pattern_file)
        pattern_name = loaded_pattern["name"]
        apply_pattern_defaults(runtime_state, loaded_pattern["defaults"])
        pattern_events = loaded_pattern["events"]
        pattern_index = apply_pattern_events_up_to(runtime_state, pattern_events, 0, 0.0)

    W, H = int(args.width), int(args.height)
    FPS = max(1, int(args.fps))
    substeps = max(1, int(args.substeps))
    dt = 1.0 / FPS / substeps
    total_frames = max(1, int(args.seconds * FPS))

    center = np.array([W * 0.5, H * 0.52], dtype=np.float64)
    arena_scale = max(0.55, min(1.10, float(args.arena_scale)))
    arena_radius = min(W * 0.42, H * 0.275) * arena_scale
    scale = W / 1080.0

    base_radius = args.base_radius * scale
    growth = args.growth * scale
    oversize_margin = max(2.0, 8.0 * scale)
    spike_depth = args.spike_depth * scale
    spike_half_width = args.spike_width * scale

    ring_width = max(2, int(round(5 * scale)))
    border_width = max(2, int(round(4 * scale)))

    final_out = Path(args.out).expanduser().resolve()
    final_out.parent.mkdir(parents=True, exist_ok=True)
    silent_video = final_out.with_suffix(".silent.mp4")
    audio_wav = final_out.with_suffix(".wav")
    source_temp_wav = final_out.with_suffix(".source.wav")

    ffmpeg = None
    source_samples = []
    if args.audio and args.audio_mode in ("original", "bounce-samples"):
        source_path = Path(args.audio_file).expanduser()
        if not args.audio_file:
            raise ValueError(
                f"--audio-file is required for audio mode: {args.audio_mode}"
            )
        if not source_path.exists():
            raise FileNotFoundError(f"Audio file not found: {source_path}")

        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            raise RuntimeError(
                "FFmpeg is required for Original MP3 / Bounce Samples audio mode."
            )

        if args.audio_mode == "bounce-samples":
            report_progress(0.0, "Analyzing source audio")
            source_samples = prepare_bounce_samples(
                ffmpeg,
                source_path,
                source_temp_wav,
                args.sample_rate,
                args.sample_ms,
            )
            if not source_samples:
                raise RuntimeError("Could not extract bounce samples from audio file.")
            print(
                f"Prepared {len(source_samples)} source-audio bounce samples.",
                flush=True,
            )

    melody = {
        "name": "Built-in",
        "notes": list(DEFAULT_MELODY_NOTES),
        "instrument": args.instrument,
        "volume": args.note_volume,
        "loop": bool(args.melody_loop),
        "restart_on_break": bool(args.restart_melody_on_break),
    }

    if args.melody_file:
        loaded = load_melody_file(args.melody_file)
        melody["notes"] = loaded["notes"]
        melody["name"] = loaded["name"]

    notes = [max(0, min(127, int(n) + args.transpose)) for n in melody["notes"]]
    melody_index = 0
    print(f"Pattern: {pattern_name}", flush=True)

    balls = [
        spawn_ball(
            center,
            arena_radius,
            base_radius,
            rng,
            i,
            args.ball_count,
            color=resolve_ball_color(ball_color_mode, ball_colors, i, rng),
            initial_angle_deg=args.initial_angle,
            initial_speed=args.initial_speed * scale,
            max_life=ball_lives[i],
        )
        for i in range(args.ball_count)
    ]
    for ball in balls:
        ball.target_radius = ball.radius

    particles = []
    sound_events = []
    trail_layer = np.zeros((H, W, 3), dtype=np.uint8)
    trail_last_pos = [ball.pos.copy() for ball in balls]

    rotation_angle = 0.0
    sim_time = 0.0

    writer = cv2.VideoWriter(
        str(silent_video),
        cv2.VideoWriter_fourcc(*"mp4v"),
        FPS,
        (W, H),
    )
    if not writer.isOpened():
        raise RuntimeError("Cannot create video writer")

    render_started = time.perf_counter()
    report_progress(0.0, "Rendering frames")

    for frame in range(total_frames):
        for _ in range(substeps):
            pattern_index = apply_pattern_events_up_to(
                runtime_state,
                pattern_events,
                pattern_index,
                sim_time,
            )
            sim_time += dt
            rotation_angle += runtime_state["rotation_speed"] * dt
            gravity = np.array([0.0, runtime_state["gravity"] * scale], dtype=np.float64)

            spikes = get_spikes(
                center,
                arena_radius,
                rotation_angle,
                spike_depth,
                spike_half_width,
                runtime_state["spike_count"],
                gap_position_deg=runtime_state["gap_position"] if runtime_state["gap_enabled"] else 0.0,
                gap_size_deg=runtime_state["gap_size"] if runtime_state["gap_enabled"] else 0.0,
            )

            for i, ball in enumerate(balls):
                if not ball.alive:
                    if ball.eliminated:
                        continue
                    ball.respawn_timer -= dt
                    if ball.respawn_timer <= 0.0:
                        balls[i] = spawn_ball(
                            center,
                            arena_radius,
                            base_radius,
                            rng,
                            i,
                            args.ball_count,
                            color=ball.color,
                            initial_angle_deg=args.initial_angle,
                            initial_speed=args.initial_speed * scale,
                            max_life=ball.max_life,
                            current_life=ball.life,
                            center_spawn=True,
                        )
                        balls[i].target_radius = balls[i].radius
                        trail_last_pos[i] = balls[i].pos.copy()
                    continue

                ball.wall_hit_cooldown = max(0.0, ball.wall_hit_cooldown - dt)
                ball.spike_hit_cooldown = max(0.0, ball.spike_hit_cooldown - dt)
                if ball.target_radius <= 0.0:
                    ball.target_radius = ball.radius
                if ball.radius < ball.target_radius:
                    ball.radius = min(
                        ball.target_radius,
                        ball.radius + max(0.0, args.smooth_growth_speed) * scale * dt,
                    )
                ball.vel += gravity * dt
                ball.vel *= math.exp(-runtime_state["air_drag"] * dt)
                ball.vel = clamp_speed(ball.vel, runtime_state["max_speed"] * scale)
                ball.pos += ball.vel * dt

                hit_spike = any(
                    circle_hits_triangle(ball.pos, ball.radius, tri)
                    for tri in spikes
                )

                if hit_spike and ball.spike_hit_cooldown <= 0.0:
                    eliminated = apply_spike_damage(
                        ball,
                        center,
                        arena_radius,
                        cooldown=args.respawn_delay,
                    )
                    particles.extend(create_particles(ball, rng))
                    sound_events.append((sim_time, "spike", 1.0))
                    if args.restart_melody_on_break:
                        melody_index = 0
                    if eliminated:
                        continue
                    # Lost one life: burst and restart from the middle on next respawn.
                    continue

                wall_hit = solve_ball_wall(
                    ball,
                    center,
                    arena_radius,
                    runtime_state["wall_restitution"],
                    runtime_state["wall_friction"],
                    gap_position_deg=runtime_state["gap_position"] if runtime_state["gap_enabled"] else 0.0,
                    gap_size_deg=runtime_state["gap_size"] if runtime_state["gap_enabled"] else 0.0,
                )

                if wall_hit and ball.wall_hit_cooldown <= 0.0:
                    if args.audio:
                        if args.audio_mode == "bounce-samples" and source_samples:
                            if melody_index < len(source_samples):
                                sound_events.append((sim_time, "sample", melody_index))
                                melody_index += 1
                            elif args.melody_loop:
                                melody_index = 0
                                sound_events.append((sim_time, "sample", melody_index))
                                melody_index += 1
                        elif args.audio_mode == "synth" and notes:
                            if melody_index < len(notes):
                                sound_events.append((sim_time, "note", notes[melody_index]))
                                melody_index += 1
                            elif args.melody_loop:
                                melody_index = 0
                                sound_events.append((sim_time, "note", notes[melody_index]))
                                melody_index += 1

                    if ball_color_mode == "random":
                        ball.color = random_vivid_bgr(rng)

                    # Smooth unlimited growth: each bounce raises the target size.
                    # The visible radius eases toward it every physics step.
                    ball.target_radius += growth

                    speed_now = length(ball.vel)
                    if speed_now > 1e-9:
                        target = min(
                            runtime_state["max_speed"] * scale,
                            speed_now * runtime_state["speed_growth"],
                        )
                        ball.vel *= target / speed_now

                    offset = ball.pos - center
                    dist = length(offset)
                    allowed = arena_radius - ball.radius
                    if dist > allowed:
                        ball.pos = center + normalize(offset) * allowed

                    ball.wall_hit_cooldown = 0.018

            if args.ball_count > 1:
                solve_ball_pairs(balls)

            if particles:
                update_particles(particles, dt, gravity)

        if args.motion_trail:
            spacing_ratio = max(0.02, float(args.trail_stamp_spacing))
            for i, ball in enumerate(balls):
                if not ball.alive:
                    continue
                # Ball and its permanent stamp always share the same current rainbow color.
                hue = (sim_time * args.trail_rainbow_speed + i / max(1, args.ball_count)) % 1.0
                ball.color = hsv_to_bgr(hue)
                moved = length(ball.pos - trail_last_pos[i])
                if moved >= max(1.0, ball.radius * spacing_ratio):
                    stamp_pos = tuple(np.round(ball.pos).astype(int))
                    stamp_radius = max(1, int(round(ball.radius)))
                    cv2.circle(trail_layer, stamp_pos, stamp_radius, ball.color, -1, cv2.LINE_AA)
                    cv2.circle(
                        trail_layer, stamp_pos, stamp_radius, (248, 248, 248),
                        max(1, int(round(ball.radius * 0.025))), cv2.LINE_AA,
                    )
                    trail_last_pos[i] = ball.pos.copy()

        img = np.zeros((H, W, 3), dtype=np.uint8)
        if args.motion_trail:
            img = cv2.add(img, trail_layer)
        c = tuple(np.round(center).astype(int))

        if args.rainbow_border:
            draw_rainbow_ring(
                img,
                center,
                arena_radius,
                (sim_time * args.rainbow_speed) % 1.0,
                ring_width,
                gap_position_deg=runtime_state["gap_position"] if runtime_state["gap_enabled"] else 0.0,
                gap_size_deg=runtime_state["gap_size"] if runtime_state["gap_enabled"] else 0.0,
            )
        else:
            draw_plain_ring(
                img,
                center,
                arena_radius,
                (242, 242, 242),
                ring_width,
                gap_position_deg=args.gap_position,
                gap_size_deg=args.gap_size,
            )

        spikes = get_spikes(
            center,
            arena_radius,
            rotation_angle,
            spike_depth,
            spike_half_width,
            runtime_state["spike_count"],
            gap_position_deg=runtime_state["gap_position"] if runtime_state["gap_enabled"] else 0.0,
            gap_size_deg=runtime_state["gap_size"] if runtime_state["gap_enabled"] else 0.0,
        )
        for tri in spikes:
            draw_triangle(img, tri, (45, 45, 245))

        draw_particles(img, particles)

        for bi, ball in enumerate(balls):
            if ball.alive:
                draw_ball(img, ball, border_width, bool(args.show_ball_numbers), parse_hex_color(args.ball_number_color), skin=ball_skins.get(bi))

        if args.show_hud:
            alive_count = sum(1 for b in balls if b.alive)
            cv2.putText(
                img,
                f"BALLS {alive_count}/{args.ball_count}",
                (24, 46),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.70 * scale,
                (145, 145, 145),
                max(1, int(round(2 * scale))),
                cv2.LINE_AA,
            )
            cv2.putText(
                img,
                f"NOTE {melody_index + 1 if notes else 0}",
                (24, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55 * scale,
                (125, 125, 125),
                max(1, int(round(1 * scale))),
                cv2.LINE_AA,
            )

        writer.write(img)

        render_ratio = (frame + 1) / total_frames
        overall = render_ratio * 90.0
        elapsed = time.perf_counter() - render_started
        eta = elapsed * (1.0 - render_ratio) / render_ratio if render_ratio > 0 else 0.0

        if frame == total_frames - 1 or frame % max(1, FPS // 3) == 0:
            report_progress(overall, "Rendering frames")
            print(
                f"\rRendering {render_ratio * 100:6.2f}% "
                f"| {frame + 1}/{total_frames} "
                f"| Elapsed {int(elapsed // 60):02d}:{int(elapsed % 60):02d} "
                f"| ETA {int(eta // 60):02d}:{int(eta % 60):02d}",
                end="",
                flush=True,
            )

    writer.release()
    print()

    if not args.audio:
        report_progress(96.0, "Finalizing silent video")
        silent_video.replace(final_out)
        report_progress(100.0, "Complete")
    else:
        if args.audio_mode == "original":
            report_progress(92.0, "Preparing original audio")
            if ffmpeg is None:
                ffmpeg = find_ffmpeg()
            if not ffmpeg:
                raise RuntimeError("FFmpeg is required for Original MP3 / Audio mode.")

            source_audio = Path(args.audio_file).expanduser()
            use_nvenc = ffmpeg_has_nvenc(ffmpeg)
            cmd = build_original_audio_ffmpeg_cmd(
                ffmpeg,
                silent_video,
                source_audio,
                final_out,
                use_nvenc,
                source_volume=args.source_volume,
            )

            try:
                run_ffmpeg_with_progress(
                    cmd,
                    args.seconds,
                    progress_start=92.0,
                    progress_end=100.0,
                )
            except subprocess.CalledProcessError:
                if not use_nvenc:
                    raise

                print("NVENC failed. Retrying with CPU x264...", flush=True)
                report_progress(92.0, "Retrying with CPU x264")
                cmd = build_original_audio_ffmpeg_cmd(
                    ffmpeg,
                    silent_video,
                    source_audio,
                    final_out,
                    False,
                    source_volume=args.source_volume,
                )
                run_ffmpeg_with_progress(
                    cmd,
                    args.seconds,
                    progress_start=92.0,
                    progress_end=100.0,
                )

            silent_video.unlink(missing_ok=True)

        else:
            if args.audio_mode == "bounce-samples":
                report_progress(90.5, "Building bounce samples audio")
                make_bounce_sample_audio(
                    sound_events,
                    args.seconds,
                    args.sample_rate,
                    audio_wav,
                    source_samples,
                    source_volume=args.source_volume,
                )
            else:
                report_progress(90.5, "Creating note audio")
                make_audio(
                    sound_events,
                    args.seconds,
                    args.sample_rate,
                    audio_wav,
                    instrument=args.instrument,
                    note_volume=args.note_volume,
                )

            report_progress(92.0, "Preparing encoder")

            if ffmpeg is None:
                ffmpeg = find_ffmpeg()

            if not ffmpeg:
                silent_video.replace(final_out)
                audio_wav.unlink(missing_ok=True)
                print("WARNING: ffmpeg not found. Saved silent video only.")
                report_progress(100.0, "Complete (silent: FFmpeg missing)")
            else:
                use_nvenc = ffmpeg_has_nvenc(ffmpeg)
                cmd = build_ffmpeg_cmd(
                    ffmpeg,
                    silent_video,
                    audio_wav,
                    final_out,
                    use_nvenc,
                )

                try:
                    run_ffmpeg_with_progress(
                        cmd,
                        args.seconds,
                        progress_start=92.0,
                        progress_end=100.0,
                    )
                except subprocess.CalledProcessError:
                    if not use_nvenc:
                        raise

                    print("NVENC failed. Retrying with CPU x264...", flush=True)
                    report_progress(92.0, "Retrying with CPU x264")
                    cmd = build_ffmpeg_cmd(
                        ffmpeg,
                        silent_video,
                        audio_wav,
                        final_out,
                        False,
                    )
                    run_ffmpeg_with_progress(
                        cmd,
                        args.seconds,
                        progress_start=92.0,
                        progress_end=100.0,
                    )

                silent_video.unlink(missing_ok=True)
                audio_wav.unlink(missing_ok=True)

    print(f"Saved: {final_out}")
    print(f"Ball count: {args.ball_count}")
    print(f"Spike count: {args.spike_count}")
    print(f"Audio mode: {args.audio_mode}")
    if args.audio_mode == "synth":
        print(f"Melody: {melody['name']}")
        print(f"Instrument: {args.instrument}")
    elif args.audio_file:
        print(f"Source audio: {args.audio_file}")


if __name__ == "__main__":
    main()
