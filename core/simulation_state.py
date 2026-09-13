from dataclasses import dataclass, field

@dataclass
class SimulationState:
    balls: list = field(default_factory=list)
    particles: list = field(default_factory=list)
    spikes: list = field(default_factory=list)
    elapsed_time: float = 0.0
    rotation: float = 0.0
    audio_events: list = field(default_factory=list)
    collision_count: int = 0
    status: str = "ready"
