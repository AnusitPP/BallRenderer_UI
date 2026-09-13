import math
import cv2
import numpy as np
from engines.circle.physics import *

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


