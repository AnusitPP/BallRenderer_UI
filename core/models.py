from dataclasses import dataclass
import numpy as np

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


