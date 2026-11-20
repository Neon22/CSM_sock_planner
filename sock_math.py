# Pure MicroPython calculation, step-timeline, SVG diagram, and CSM operation-sheet
# export utilities for toe-up Circular Sock Machine (CSM) pattern planning.

# Author Neon22 Nov 2026

import math

# ---------------------------------------------------------------------------
# Constants & Unit Helpers
# ---------------------------------------------------------------------------

CM_PER_INCH = 2.54

# Standard adult sizing ladder: (display label, bare foot length in cm).
# Rows remain ordered small -> large so clicking any row snaps foot length.
ADULT_SIZES = [
    ("EU 36-37 | NZ/UK 4-5   | US W 6-7", 23.0),
    ("EU 38-39 | NZ/UK 5.5-6 | US W 7.5-8", 24.5),
    ("EU 40-41 | NZ/UK 7-7.5 | US M 7.5-8", 25.5),
    ("EU 42-43 | NZ/UK 8-9   | US M 9-10", 27.0),
    ("EU 44-45 | NZ/UK 9.5-10| US M 10.5-11", 28.5),
    ("EU 46-47 | NZ/UK 11-12 | US M 12-13", 30.0),
]

# Phase metadata keyed by canonical phase id used in DOM `data-phase` attributes.
PHASE_META = {
    "toe": ("1. Short-Row Toe", "Half-cylinder short rows decreasing to center plateau, then increasing back."),
    "foot": ("2. Foot Tube", "Plain knitting in the round on all cylinder needles."),
    "heel": ("3. Short-Row Heel", "Back half-cylinder short rows decreasing to plateau, then increasing back."),
    "leg": ("4. Leg Tube", "Plain or stranded colourwork rounds in the round above the heel."),
    "rib": ("5. Ribbed Cuff", "Ribber dial/cylinder engagement for elasticated cuff rounds."),
    "hem": ("6. Hung Hem", "Picot / turning-row fold hung onto cylinder needles and latch bound off."),
}


def title(s):
    """Capitalize space-separated words safely without `str.title()` (MicroPython-safe)."""
    return " ".join(w[:1].upper() + w[1:].lower() for w in s.split(" "))


def to_cm(val, unit):
    """Convert a display-unit measurement ('metric' or 'imperial') to centimeters."""
    return val * CM_PER_INCH if unit == "imperial" else val


def from_cm(cm_val, unit):
    """Convert centimeters to the active UI display unit ('cm' or 'in')."""
    return cm_val / CM_PER_INCH if unit == "imperial" else cm_val


def unit_label(unit):
    """Return short display suffix ('in' or 'cm') for the active unit system."""
    return "in" if unit == "imperial" else "cm"


def compute_ribber_requirements(cylinder_needles, rib_setup):
    """Calculate required ribber dial slots & engaged needles for a cylinder count.

    CSM ribber mechanics:
    - 1x1: opposes every 2nd cylinder needle -> needs at least N/2 slots (half-pitch
      dial, or N-slot dial skipping every 2nd slot).
    - 2x2: places two ribber needles in adjacent cylinder slots -> requires 1:1
      slot spacing matching all N cylinder slots (loaded 2-in, 2-out).
    - 3x1: opposes every 4th cylinder needle -> needs at least N/4 slots (or every
      2nd slot on an N/2-slot dial / every 4th on an N-slot dial).
    - plain (Mock): cylinder-only cuff, 0 ribber slots required.
    """
    n = max(2, int(cylinder_needles))
    half = n // 2

    if rib_setup == "1x1":
        engaged = half
        return {
            "required_slots": half,
            "engaged_needles": engaged,
            "headline": f"{half} slots min",
            "short_spec": f"{half}-slot ribber",
            "detail": f"{engaged} ribber needles engaged (every 2nd cyl slot; {n}-slot dial also works skipping 1).",
            "is_clean_repeat": (n % 2 == 0),
            "repeat_note": "",
        }

    if rib_setup == "2x2":
        engaged = sum(1 for i in range(n) if i % 4 in (0, 1))
        rem = n % 4
        clean = (rem == 0)
        return {
            "required_slots": n,
            "engaged_needles": engaged,
            "headline": f"{n} slots (1:1 pitch)",
            "short_spec": f"{n}-slot ribber",
            "detail": f"{engaged} ribber needles loaded 2-in / 2-out across a full {n}-slot dial.",
            "is_clean_repeat": clean,
            "repeat_note": "" if clean else f"{n} is not divisible by 4 — 2×2 rib leaves an uneven {rem}-stitch seam.",
        }

    if rib_setup == "3x1":
        engaged = sum(1 for i in range(n) if i % 4 == 0)
        rem = n % 4
        clean = (rem == 0)
        min_slots = n // 4 if clean else engaged
        return {
            "required_slots": min_slots,
            "engaged_needles": engaged,
            "headline": f"{min_slots} slots min",
            "short_spec": f"{min_slots}+ slot ribber",
            "detail": f"{engaged} ribber needles (or every 2nd slot on {half}-slot / every 4th on {n}-slot dial).",
            "is_clean_repeat": clean,
            "repeat_note": "" if clean else f"{n} is not divisible by 4 — 3×1 rib leaves an uneven {rem}-stitch seam.",
        }

    return {
        "required_slots": 0,
        "engaged_needles": 0,
        "headline": "0 slots (no ribber)",
        "short_spec": "No ribber (mock)",
        "detail": "Cylinder-only mock rib or plain cuff transition.",
        "is_clean_repeat": True,
        "repeat_note": "",
    }


# ---------------------------------------------------------------------------
# Core CSM Pattern Math
# ---------------------------------------------------------------------------


def plateau_bounds(half_needles):
    """Return `(min_needles, max_needles, min_pct, max_pct)` for symmetric plateau.

    Legal plateau needle counts share the same parity as `half_needles` (so
    they always increment/decrement in steps of 2) and leave at least one
    short-row lift per side when `half_needles >= 4`.
    """
    half = max(2, int(half_needles))
    min_n = 2 if (half % 2 == 0) else 3
    max_n = (half - 2) if half >= 4 else half
    if max_n < min_n:
        max_n = min_n
    min_pct = (min_n / float(half)) * 100.0
    max_pct = (max_n / float(half)) * 100.0
    return min_n, max_n, min_pct, max_pct


def compute_plateau_needles(half_needles, plateau_pct=35.0, plateau_needles=None):
    """Resolve minimum active plateau needles & actual percentage with parity snap.

    Because short-row shaping lifts one needle per side symmetrically,
    `(half_needles - center_needles)` must be even, meaning valid needle
    counts step in increments of 2 starting from `min_n` (`2` for even half,
    `3` for odd half). Either a percentage or an explicit needle count can
    drive the result, snapping to the nearest legal parity value.
    """
    half = max(2, int(half_needles))
    min_n, max_n, _, _ = plateau_bounds(half)
    if plateau_needles is not None:
        target = float(plateau_needles)
    else:
        target = half * (plateau_pct / 100.0)

    k = round((target - min_n) / 2.0)
    center = min_n + (2 * k)
    if center < min_n:
        center = min_n
    if center > max_n:
        center = max_n

    actual_pct = (center / float(half)) * 100.0
    return center, actual_pct


def calculate_csm_sock(
    cylinder_needles,
    swatch_stitches,
    swatch_width_cm,
    swatch_rows,
    swatch_height_cm,
    foot_length_cm,
    colorwork_rows_in_swatch=None,
    leg_height_cm=14.0,
    rib_cuff_cm=4.0,
    hem_depth_cm=2.0,
    negative_ease_pct=10.0,
    toe_center_ratio=0.35,
    plateau_needles=None,
    deep_heel_extra=0,
):
    """Calculates exact CSM row/pass counts from swatch gauge and cylinder count.

    All length arguments are expected in centimeters (`cm`). If
    `colorwork_rows_in_swatch` is provided, leg rounds are computed using the
    separate stranded-colourwork vertical gauge while keeping plain gauge for
    toe, foot, heel, rib, and hung hem.

    Plateau control:
    - By default `toe_center_ratio` (0.35 = 35%) determines the minimum active
      center plateau needles via `compute_plateau_needles`.
    - Passing an explicit `plateau_needles` integer overrides `toe_center_ratio`
      so callers driven by a direct needle count avoid float rounding drift.

    Deep heel control:
    - `deep_heel_extra` (default 0) specifies extra needles per side borrowed
      from the front instep into the heel (`heel_work_needles = half_needles +
      2 * deep_heel_extra`, capped to always leave >= 4 instep needles held).
    - Because `heel_work_needles` widens while `center_needles` stays fixed,
      `heel_lift_per_side` and `heel_passes` increase by `deep_extra` and
      `4 * deep_extra` respectively, consuming more of `target_foot_cm` and
      reducing straight `foot_rows` accordingly (`foot_overflow` flags when
      toe + deep heel exceed `target_foot_cm`).
    """
    # Stitch & vertical row densities per cm
    st_per_cm = swatch_stitches / swatch_width_cm
    plain_rows_per_cm = swatch_rows / swatch_height_cm
    leg_rows_per_cm = (
        (colorwork_rows_in_swatch / swatch_height_cm)
        if colorwork_rows_in_swatch is not None
        else plain_rows_per_cm
    )

    # Target knitted foot length after lengthwise negative ease so the sock hugs the foot
    target_foot_cm = foot_length_cm * (1.0 - negative_ease_pct / 100.0)

    # Half-cylinder short-row toe math (scales automatically for any even cylinder count)
    half_needles = cylinder_needles // 2
    center_needles, actual_plateau_pct = compute_plateau_needles(
        half_needles, toe_center_ratio * 100.0, plateau_needles
    )

    toe_lift_per_side = max(0, (half_needles - center_needles) // 2)
    # 1 pass per lifted needle on the way down (both sides = 2 * lift_per_side),
    # mirrored on the way back up (* 2). Two half-cylinder passes equal 1 full row height.
    toe_passes = (toe_lift_per_side * 2) * 2
    toe_length_cm = (toe_passes / 2.0) / plain_rows_per_cm

    # Deep heel: borrow `deep_extra` needles per side from the front instep into heel work
    max_deep_extra = max(0, (half_needles - 4) // 2)
    deep_extra = max(0, min(max_deep_extra, int(deep_heel_extra)))
    heel_work_needles = half_needles + (2 * deep_extra)
    heel_held_needles = cylinder_needles - heel_work_needles
    heel_lift_per_side = max(0, (heel_work_needles - center_needles) // 2)
    heel_passes = (heel_lift_per_side * 2) * 2
    heel_length_cm = (heel_passes / 2.0) / plain_rows_per_cm

    # Straight foot rounds fill the remaining target foot length between toe and heel wedges
    raw_straight_cm = target_foot_cm - toe_length_cm - heel_length_cm
    foot_overflow = raw_straight_cm < 0.0
    straight_foot_cm = max(0.0, raw_straight_cm)
    foot_rows = round(straight_foot_cm * plain_rows_per_cm)

    # Leg (plain or colourwork), ribbed cuff, and hung hem ({h} outer + 1 loose + {h} inner)
    leg_rows = round(leg_height_cm * leg_rows_per_cm)
    rib_rows = round(rib_cuff_cm * plain_rows_per_cm)
    hem_half_rows = round(hem_depth_cm * plain_rows_per_cm)

    # Tube circumference unstretched vs. recommended wearer ball-of-foot circumference
    relaxed_circ_cm = cylinder_needles / st_per_cm
    ease_factor = max(0.1, 1.0 - negative_ease_pct / 100.0)

    return {
        "st_per_cm": st_per_cm,
        "plain_rows_per_cm": plain_rows_per_cm,
        "leg_rows_per_cm": leg_rows_per_cm,
        "target_foot_cm": target_foot_cm,
        "toe_length_cm": toe_length_cm,
        "heel_length_cm": heel_length_cm,
        "straight_foot_cm": straight_foot_cm,
        "foot_overflow": foot_overflow,
        "relaxed_circ_cm": round(relaxed_circ_cm, 1),
        "recommended_foot_circ_cm": round(relaxed_circ_cm / ease_factor, 1),
        "half_needles": half_needles,
        "center_needles": center_needles,
        "plateau_pct": round(actual_plateau_pct, 1),
        "lift_per_side": toe_lift_per_side,
        "toe_lift_per_side": toe_lift_per_side,
        "heel_lift_per_side": heel_lift_per_side,
        "deep_heel_extra": deep_extra,
        "max_deep_heel_extra": max_deep_extra,
        "heel_work_needles": heel_work_needles,
        "heel_held_needles": heel_held_needles,
        "toe_passes": toe_passes,
        "foot_rows": foot_rows,
        "heel_passes": heel_passes,
        "leg_rows": leg_rows,
        "rib_rows": rib_rows,
        "hem_half_rows": hem_half_rows,
    }


# ---------------------------------------------------------------------------
# Row / Pass Scrubber Timeline
# ---------------------------------------------------------------------------


def resolve_step(res, requested_step):
    """Map a 1-based global step (pass or round) across all sock phases.

    Returns active phase metadata, normalized progress within that phase,
    `in_work` / `held_needles` counts, and left/right lifted needle counts so
    both the 2D sock profile cursor and the cylinder needle-bed diagram stay
    synchronized—including asymmetric Deep Heel passes (`heel_work_needles`
    active vs. `heel_held_needles` on the front instep).
    """
    half = res["half_needles"]
    center = res["center_needles"]
    hem_h = res["hem_half_rows"]

    # Build contiguous step intervals for each non-zero phase in knit order
    raw_phases = [
        ("toe", max(1, res["toe_passes"])),
        ("foot", max(0, res["foot_rows"])),
        ("heel", max(1, res["heel_passes"])),
        ("leg", max(0, res["leg_rows"])),
        ("rib", max(0, res["rib_rows"])),
        ("hem", max(1, hem_h * 2 + 1)),
    ]

    segments = {}
    cursor = 1
    for name, count in raw_phases:
        if count > 0:
            segments[name] = (cursor, cursor + count - 1)
            cursor += count
    total_steps = max(1, cursor - 1)

    # Clamp requested scrubber position into [1, total_steps]
    step = int(requested_step)
    if step < 1:
        step = 1
    if step > total_steps:
        step = total_steps

    # Locate which phase owns `step`
    active_phase = "toe"
    phase_step = 1
    phase_total = 1
    for name, count in raw_phases:
        if name in segments:
            s0, s1 = segments[name]
            if s0 <= step <= s1:
                active_phase = name
                phase_step = step - s0 + 1
                phase_total = count
                break

    phase_progress = phase_step / float(max(1, phase_total))

    left_lifted = 0
    right_lifted = 0
    in_work = half
    held_needles = half
    subphase = ""
    hem_stage = ""

    if active_phase in ("toe", "heel"):
        if active_phase == "heel":
            phase_work = res["heel_work_needles"]
            phase_lift = res["heel_lift_per_side"]
            held_needles = res["heel_held_needles"]
        else:
            phase_work = half
            phase_lift = res["toe_lift_per_side"]
            held_needles = half

        # First half of passes lifts one needle per pass (alternating left/right);
        # second half returns one parked needle per pass back into work.
        mid = 2 * phase_lift
        if phase_step <= mid:
            subphase = "Decrease"
            lifted_total = phase_step
        else:
            subphase = "Increase"
            lifted_total = max(0, phase_total - phase_step)
        left_lifted = (lifted_total + 1) // 2
        right_lifted = lifted_total // 2
        in_work = max(center, phase_work - left_lifted - right_lifted)
    elif active_phase == "hem":
        # Hung hem sequence: {h} outer rounds -> 1 loose turning round -> {h} inner rounds
        if phase_step <= hem_h:
            hem_stage = "Outer Hem Face"
        elif phase_step == hem_h + 1:
            hem_stage = "Loose Turning Round"
        else:
            hem_stage = "Inner Hem & Hang Loops"

    return {
        "step": step,
        "total_steps": total_steps,
        "phase": active_phase,
        "phase_step": phase_step,
        "phase_total": phase_total,
        "phase_progress": phase_progress,
        "segments": segments,
        "subphase": subphase,
        "left_lifted": left_lifted,
        "right_lifted": right_lifted,
        "in_work": in_work,
        "held_needles": held_needles,
        "hem_stage": hem_stage,
    }


def phase_target_step(res, phase_name):
    """Return the midpoint global step for `phase_name` when jumping via phase buttons/rows."""
    info = resolve_step(res, 1)
    segs = info["segments"]
    if phase_name not in segs:
        return info["step"]
    s0, s1 = segs[phase_name]
    return s0 + (s1 - s0) // 2


# ---------------------------------------------------------------------------
# SVG Diagram Builders (2D Sock Profile & Cylinder Needle Bed)
# ---------------------------------------------------------------------------


def build_sock_svg(params, res, step_info, unit, rib_setup):
    """Render the interactive 2D toe-up sock side-profile schematic SVG and caption.

    Toe and heel widths scale independently from `toe_length_cm` and
    `heel_length_cm`, so increasing Deep Heel depth visibly widens the heel
    wedge into the foot while shortening the straight foot section.
    """
    phase = step_info["phase"]
    p_prog = step_info["phase_progress"]
    phase_order = ["toe", "foot", "heel", "leg", "rib", "hem"]
    active_idx = phase_order.index(phase)
    u = unit_label(unit)

    # Clamp minimum physical dimensions so extreme inputs keep readable SVG zones
    toe_cm = max(2.2, res["toe_length_cm"])
    straight_cm = max(2.0, res["straight_foot_cm"])
    heel_cm = max(2.2, res["heel_length_cm"])
    leg_cm = max(3.0, params["leg_height_cm"])
    rib_cm = max(1.0, params["rib_cuff_cm"])
    hem_cm = max(0.8, params["hem_depth_cm"])

    # Fit foot horizontally and leg+rib+hem vertically inside the 540x355 viewBox
    tube_h = 84.0
    foot_total_cm = toe_cm + straight_cm + heel_cm
    px_per_cm_h = min(14.0, 310.0 / max(12.0, foot_total_cm))
    px_per_cm_v = min(11.0, 175.0 / max(10.0, leg_cm + rib_cm + hem_cm))

    toe_w = toe_cm * px_per_cm_h
    straight_w = straight_cm * px_per_cm_h
    heel_w = heel_cm * px_per_cm_h

    leg_h = leg_cm * px_per_cm_v
    rib_h = rib_cm * px_per_cm_v
    hem_h = max(12.0, hem_cm * px_per_cm_v)

    y_sole = 296.0
    y_instep = y_sole - tube_h
    x_toe_tip = 58.0
    x_toe_end = x_toe_tip + toe_w
    x_foot_end = x_toe_end + straight_w
    x_heel_back = x_foot_end + heel_w

    y_leg_top = y_instep - leg_h
    y_rib_top = y_leg_top - rib_h
    y_hem_top = y_rib_top - hem_h

    def zone_style(name, base_fill="#f8fafc", done_fill="#eff6ff", accent="#0284c7", active_fill="#e0f2fe"):
        """Return (fill, stroke, stroke_width) reflecting completed, active, or upcoming state."""
        idx = phase_order.index(name)
        if name == phase:
            return active_fill, accent, "2.2"
        if idx < active_idx:
            return done_fill, "#475569", "1.35"
        return base_fill, "#94a3b8", "1.15"

    hem_fill, hem_stroke, hem_sw = zone_style("hem", "#fffbeb", "#fef3c7", "#d97706", "#fde68a")
    rib_fill, rib_stroke, rib_sw = zone_style("rib", "#f8fafc", "#e0f2fe", "#0284c7", "#dbeafe")
    leg_fill, leg_stroke, leg_sw = zone_style(
        "leg",
        "#fffdf5" if params["use_colorwork"] else "#f8fafc",
        "#fef3c7" if params["use_colorwork"] else "#e0f2fe",
        "#d97706" if params["use_colorwork"] else "#0284c7",
        "#fde68a" if params["use_colorwork"] else "#dbeafe",
    )
    heel_fill, heel_stroke, heel_sw = zone_style("heel", "#f8fafc", "#e0f2fe", "#0284c7", "#bae6fd")
    foot_fill, foot_stroke, foot_sw = zone_style("foot", "#f8fafc", "#e0f2fe", "#0284c7", "#dbeafe")
    toe_fill, toe_stroke, toe_sw = zone_style("toe", "#f8fafc", "#e0f2fe", "#0284c7", "#bae6fd")

    rib_lines = []
    step_x = 10.0 if rib_setup == "1x1" else (14.0 if rib_setup == "2x2" else 18.0)
    rx = x_foot_end + 8.0
    while rx < x_heel_back - 6.0:
        rib_lines.append(
            f'<line x1="{rx:.1f}" y1="{y_rib_top + 2:.1f}" x2="{rx:.1f}" y2="{y_leg_top - 2:.1f}" '
            f'stroke="#94a3b8" stroke-width="1" stroke-dasharray="3 2" pointer-events="none" />'
        )
        rx += step_x

    cw_lines = []
    if params["use_colorwork"]:
        cy = y_leg_top + 10.0
        row_idx = 0
        while cy < y_instep - 8.0:
            dash = "4 4" if row_idx % 2 == 0 else "2 6"
            cw_lines.append(
                f'<line x1="{x_foot_end + 6:.1f}" y1="{cy:.1f}" x2="{x_heel_back - 6:.1f}" y2="{cy:.1f}" '
                f'stroke="#d97706" stroke-opacity="0.45" stroke-width="1.4" stroke-dasharray="{dash}" pointer-events="none" />'
            )
            cy += 11.0
            row_idx += 1

    cursor_svg = ""
    if phase == "toe":
        cx_cur = x_toe_tip + p_prog * toe_w
        cursor_svg = (
            f'<line x1="{cx_cur:.1f}" y1="{y_instep + 3:.1f}" x2="{cx_cur:.1f}" y2="{y_sole - 3:.1f}" '
            f'stroke="#0369a1" stroke-width="2.4" stroke-dasharray="4 2"/>'
            f'<circle cx="{cx_cur:.1f}" cy="{y_instep:.1f}" r="3.5" fill="#0284c7"/>'
        )
    elif phase == "foot":
        cx_cur = x_toe_end + p_prog * straight_w
        cursor_svg = (
            f'<line x1="{cx_cur:.1f}" y1="{y_instep:.1f}" x2="{cx_cur:.1f}" y2="{y_sole:.1f}" '
            f'stroke="#0369a1" stroke-width="2.4" stroke-dasharray="4 2"/>'
            f'<circle cx="{cx_cur:.1f}" cy="{y_instep:.1f}" r="3.5" fill="#0284c7"/>'
        )
    elif phase == "heel":
        ang = (1.0 - p_prog) * (math.pi / 2.0)
        hx2 = x_foot_end + heel_w * math.cos(ang * 0.85)
        hy2 = y_instep + tube_h * math.sin(ang * 0.85)
        cursor_svg = (
            f'<line x1="{x_foot_end:.1f}" y1="{y_instep:.1f}" x2="{hx2:.1f}" y2="{hy2:.1f}" '
            f'stroke="#0369a1" stroke-width="2.4" stroke-dasharray="4 2"/>'
            f'<circle cx="{hx2:.1f}" cy="{hy2:.1f}" r="3.5" fill="#0284c7"/>'
        )
    elif phase == "leg":
        cy_cur = y_instep - p_prog * leg_h
        col = "#b45309" if params["use_colorwork"] else "#0369a1"
        cursor_svg = (
            f'<line x1="{x_foot_end:.1f}" y1="{cy_cur:.1f}" x2="{x_heel_back:.1f}" y2="{cy_cur:.1f}" '
            f'stroke="{col}" stroke-width="2.4" stroke-dasharray="4 2"/>'
            f'<circle cx="{x_foot_end:.1f}" cy="{cy_cur:.1f}" r="3.5" fill="{col}"/>'
        )
    elif phase == "rib":
        cy_cur = y_leg_top - p_prog * rib_h
        cursor_svg = (
            f'<line x1="{x_foot_end:.1f}" y1="{cy_cur:.1f}" x2="{x_heel_back:.1f}" y2="{cy_cur:.1f}" '
            f'stroke="#0369a1" stroke-width="2.4" stroke-dasharray="4 2"/>'
            f'<circle cx="{x_foot_end:.1f}" cy="{cy_cur:.1f}" r="3.5" fill="#0284c7"/>'
        )
    elif phase == "hem":
        cy_cur = y_rib_top - p_prog * hem_h
        cursor_svg = (
            f'<line x1="{x_foot_end - 3:.1f}" y1="{cy_cur:.1f}" x2="{x_heel_back + 3:.1f}" y2="{cy_cur:.1f}" '
            f'stroke="#b45309" stroke-width="2.4" stroke-dasharray="4 2"/>'
            f'<circle cx="{x_foot_end - 3:.1f}" cy="{cy_cur:.1f}" r="3.5" fill="#d97706"/>'
        )

    toe_mid_y = (y_instep + y_sole) / 2.0
    heel_corner_x = x_foot_end
    heel_corner_y = y_instep

    foot_disp = from_cm(params["foot_length_cm"], unit)
    leg_disp = from_cm(params["leg_height_cm"], unit)
    rib_disp = from_cm(params["rib_cuff_cm"], unit)
    hem_disp = from_cm(params["hem_depth_cm"], unit)

    svg = f'''<svg viewBox="0 0 540 355" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="2D toe-up sock profile schematic">
      <defs>
        <pattern id="draft-grid" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M 20 0 L 0 0 0 20" fill="none" stroke="#f1f5f9" stroke-width="1"/>
        </pattern>
      </defs>
      <rect width="540" height="355" fill="url(#draft-grid)" rx="4"/>

      <!-- 1. Hung Hem (Top folded collar) -->
      <g class="sock-zone" data-phase="hem">
        <rect x="{x_foot_end - 3:.1f}" y="{y_hem_top:.1f}" width="{heel_w + 6:.1f}" height="{hem_h:.1f}" rx="2"
              fill="{hem_fill}" stroke="{hem_stroke}" stroke-width="{hem_sw}"/>
        <line x1="{x_foot_end - 3:.1f}" y1="{y_hem_top + hem_h * 0.45:.1f}"
              x2="{x_heel_back + 3:.1f}" y2="{y_hem_top + hem_h * 0.45:.1f}"
              stroke="#d97706" stroke-width="1" stroke-dasharray="3 2" pointer-events="none"/>
      </g>

      <!-- 2. Ribbed Cuff -->
      <g class="sock-zone" data-phase="rib">
        <rect x="{x_foot_end:.1f}" y="{y_rib_top:.1f}" width="{heel_w:.1f}" height="{rib_h:.1f}"
              fill="{rib_fill}" stroke="{rib_stroke}" stroke-width="{rib_sw}"/>
        {"".join(rib_lines)}
      </g>

      <!-- 3. Leg Tube -->
      <g class="sock-zone" data-phase="leg">
        <rect x="{x_foot_end:.1f}" y="{y_leg_top:.1f}" width="{heel_w:.1f}" height="{leg_h:.1f}"
              fill="{leg_fill}" stroke="{leg_stroke}" stroke-width="{leg_sw}"/>
        {"".join(cw_lines)}
      </g>

      <!-- 4. Short-Row Heel Wedge -->
      <g class="sock-zone" data-phase="heel">
        <path d="M {x_foot_end:.1f} {y_instep:.1f} L {x_heel_back:.1f} {y_instep:.1f} L {x_heel_back:.1f} {y_sole - 18:.1f} Q {x_heel_back:.1f} {y_sole:.1f} {x_heel_back - 18:.1f} {y_sole:.1f} L {x_foot_end:.1f} {y_sole:.1f} Z"
              fill="{heel_fill}" stroke="{heel_stroke}" stroke-width="{heel_sw}"/>
        <line x1="{heel_corner_x:.1f}" y1="{heel_corner_y:.1f}" x2="{x_heel_back - 6:.1f}" y2="{y_sole - 6:.1f}"
              stroke="#0284c7" stroke-opacity="0.45" stroke-width="1" stroke-dasharray="4 3" pointer-events="none"/>
      </g>

      <!-- 5. Straight Foot Tube -->
      <g class="sock-zone" data-phase="foot">
        <rect x="{x_toe_end:.1f}" y="{y_instep:.1f}" width="{straight_w:.1f}" height="{tube_h:.1f}"
              fill="{foot_fill}" stroke="{foot_stroke}" stroke-width="{foot_sw}"/>
      </g>

      <!-- 6. Short-Row Toe -->
      <g class="sock-zone" data-phase="toe">
        <path d="M {x_toe_end:.1f} {y_instep:.1f} L {x_toe_tip + 22:.1f} {y_instep:.1f} Q {x_toe_tip:.1f} {y_instep:.1f} {x_toe_tip:.1f} {toe_mid_y:.1f} Q {x_toe_tip:.1f} {y_sole:.1f} {x_toe_tip + 22:.1f} {y_sole:.1f} L {x_toe_end:.1f} {y_sole:.1f} Z"
              fill="{toe_fill}" stroke="{toe_stroke}" stroke-width="{toe_sw}"/>
        <line x1="{x_toe_end:.1f}" y1="{toe_mid_y:.1f}" x2="{x_toe_tip + 4:.1f}" y2="{toe_mid_y:.1f}"
              stroke="#0284c7" stroke-opacity="0.45" stroke-width="1" stroke-dasharray="4 3" pointer-events="none"/>
      </g>

      <!-- Active Row / Pass Cursor -->
      <g pointer-events="none">
        {cursor_svg}
      </g>

      <!-- Toe-Up Direction Flow Arrow -->
      <g pointer-events="none">
        <line x1="{x_toe_tip + 14:.1f}" y1="{y_sole + 20:.1f}" x2="{x_heel_back - 10:.1f}" y2="{y_sole + 20:.1f}"
              stroke="#0f172a" stroke-width="1.2"/>
        <polyline points="{x_heel_back - 16:.1f},{y_sole + 16:.1f} {x_heel_back - 10:.1f},{y_sole + 20:.1f} {x_heel_back - 16:.1f},{y_sole + 24:.1f}"
                  fill="none" stroke="#0f172a" stroke-width="1.2"/>
        <text x="{(x_toe_tip + x_heel_back) / 2:.1f}" y="{y_sole + 36:.1f}" text-anchor="middle"
              font-family="Inter, sans-serif" font-size="11" fill="#334155">
          TOE-UP KNIT DIRECTION · Foot {foot_disp:.1f} {u} (eased {from_cm(res['target_foot_cm'], unit):.1f} {u})
        </text>
      </g>

      <!-- Callout Labels on Right Rail -->
      <g font-family="Inter, sans-serif" font-size="11" fill="#0f172a" pointer-events="none">
        <line x1="{x_heel_back + 4:.1f}" y1="{y_hem_top + hem_h / 2:.1f}" x2="{x_heel_back + 22:.1f}" y2="{y_hem_top + hem_h / 2:.1f}" stroke="#94a3b8" stroke-width="1"/>
        <text x="{x_heel_back + 26:.1f}" y="{y_hem_top + hem_h / 2 + 4:.1f}" fill="#b45309">
          Hem: {res['hem_half_rows']}+1+{res['hem_half_rows']} ({hem_disp:.1f} {u})
        </text>

        <line x1="{x_heel_back + 4:.1f}" y1="{y_rib_top + rib_h / 2:.1f}" x2="{x_heel_back + 22:.1f}" y2="{y_rib_top + rib_h / 2:.1f}" stroke="#94a3b8" stroke-width="1"/>
        <text x="{x_heel_back + 26:.1f}" y="{y_rib_top + rib_h / 2 + 4:.1f}">
          Rib ({rib_setup}): {res['rib_rows']} rds ({rib_disp:.1f} {u})
        </text>

        <line x1="{x_heel_back + 4:.1f}" y1="{y_leg_top + leg_h / 2:.1f}" x2="{x_heel_back + 22:.1f}" y2="{y_leg_top + leg_h / 2:.1f}" stroke="#94a3b8" stroke-width="1"/>
        <text x="{x_heel_back + 26:.1f}" y="{y_leg_top + leg_h / 2 + 4:.1f}">
          Leg: {res['leg_rows']} rds ({leg_disp:.1f} {u}){" · CW" if params["use_colorwork"] else ""}
        </text>

        <line x1="{x_heel_back + 4:.1f}" y1="{y_instep + tube_h / 2:.1f}" x2="{x_heel_back + 22:.1f}" y2="{y_instep + tube_h / 2:.1f}" stroke="#94a3b8" stroke-width="1"/>
        <text x="{x_heel_back + 26:.1f}" y="{y_instep + tube_h / 2 + 4:.1f}" fill="#0369a1">
          Heel: {res['heel_passes']}p ({res['heel_work_needles']}→{res['center_needles']}→{res['heel_work_needles']}){f" · Deep +{res['deep_heel_extra']}/s" if res['deep_heel_extra'] > 0 else ""}
        </text>

        <text x="{(x_toe_tip + x_toe_end) / 2:.1f}" y="{y_instep - 10:.1f}" text-anchor="middle" fill="#0369a1">
          Toe: {res['toe_passes']}p
        </text>
        <text x="{(x_toe_end + x_foot_end) / 2:.1f}" y="{y_instep - 10:.1f}" text-anchor="middle">
          Foot: {res['foot_rows']} rds
        </text>
      </g>
    </svg>'''

    phase_title, phase_desc = PHASE_META[phase]
    caption = f"{phase_title} ({step_info['phase_step']}/{step_info['phase_total']}) — {phase_desc}"
    return svg, caption


def build_cylinder_svg(params, res, step_info, rib_setup):
    """Render the N-slot top-down cylinder needle-bed schematic SVG and caption.

    Angular layout places slots `0 .. half-1` across the upper semicircle
    (Back Half / Heel) and `half .. n-1` across the lower semicircle
    (Front Half / Instep & Toe). Deep heels wrap `deep_heel_extra` needles
    per side from the front instep into the heel working arc.
    """
    n = params["cylinder_needles"]
    half = res["half_needles"]
    extra = res["deep_heel_extra"]
    heel_work = res["heel_work_needles"]
    phase = step_info["phase"]
    p_step = step_info["phase_step"]
    p_total = step_info["phase_total"]
    rib_info = compute_ribber_requirements(n, rib_setup)

    cx, cy = 180.0, 175.0
    r_outer = 122.0
    r_inner = 102.0
    r_rib = 82.0

    # Keep individual needle ticks legible even on high custom cylinder counts (>84)
    tick_scale = 1.0 if n <= 84 else max(0.5, 84.0 / float(n))

    left_lifted = step_info["left_lifted"]
    right_lifted = step_info["right_lifted"]
    in_work = step_info["in_work"]
    held_needles = step_info["held_needles"]
    lifted_total = left_lifted + right_lifted

    needles_svg = []
    ribber_svg = []

    for i in range(n):
        # Step clockwise from -180 deg (9 o'clock) so 0..half-1 forms the upper arc
        angle_deg = -180.0 + (i + 0.5) * (360.0 / n)
        rad = angle_deg * math.pi / 180.0
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)

        x1 = cx + r_inner * cos_a
        y1 = cy + r_inner * sin_a
        x2 = cx + r_outer * cos_a
        y2 = cy + r_outer * sin_a

        stroke_col = "#94a3b8"
        stroke_w = 2.0
        opacity = "1"

        if phase == "toe":
            # Short-row toe works on the Front Half (`half..n-1`); Back Half stays held
            if i >= half:
                local_idx = i - half
                if local_idx < right_lifted or local_idx >= (half - left_lifted):
                    stroke_col = "#d97706"
                    stroke_w = 2.3
                else:
                    stroke_col = "#0284c7"
                    stroke_w = 3.0
            else:
                stroke_col = "#cbd5e1"
                stroke_w = 1.4
                opacity = "0.55"
        elif phase == "heel":
            # Short-row heel works on Back Half + `extra` side needles borrowed from Front Half
            in_heel_arc = (i < half + extra) or (i >= n - extra)
            if in_heel_arc:
                pos = (i - (n - extra)) if i >= (n - extra) else (i + extra)
                if pos < left_lifted or pos >= (heel_work - right_lifted):
                    stroke_col = "#d97706"
                    stroke_w = 2.3
                else:
                    stroke_col = "#0284c7"
                    stroke_w = 3.0
            else:
                stroke_col = "#cbd5e1"
                stroke_w = 1.4
                opacity = "0.55"
        elif phase in ("foot", "leg"):
            stroke_col = "#d97706" if (phase == "leg" and params["use_colorwork"]) else "#0284c7"
            stroke_w = 2.4
        elif phase == "rib":
            # Highlight cylinder needles alongside engaged inner ribber dial needles
            stroke_col = "#0f172a"
            stroke_w = 2.2
            engaged = False
            if rib_setup == "1x1":
                engaged = (i % 2 == 0)
            elif rib_setup == "2x2":
                engaged = (i % 4 in (0, 1))
            elif rib_setup == "3x1":
                engaged = (i % 4 == 0)
            if engaged:
                rx1 = cx + (r_rib - 12) * cos_a
                ry1 = cy + (r_rib - 12) * sin_a
                rx2 = cx + r_rib * cos_a
                ry2 = cy + r_rib * sin_a
                ribber_svg.append(
                    f'<line x1="{rx1:.1f}" y1="{ry1:.1f}" x2="{rx2:.1f}" y2="{ry2:.1f}" '
                    f'stroke="#0284c7" stroke-width="{2.4 * tick_scale:.2f}" stroke-linecap="round"/>'
                )
        elif phase == "hem":
            if step_info["hem_stage"] == "Outer Hem Face":
                stroke_col = "#0284c7"
                stroke_w = 2.4
            elif step_info["hem_stage"] == "Loose Turning Round":
                stroke_col = "#dc2626"
                stroke_w = 2.8
            else:
                stroke_col = "#d97706"
                stroke_w = 2.8

        needles_svg.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke_col}" stroke-width="{stroke_w * tick_scale:.2f}" stroke-opacity="{opacity}" stroke-linecap="round"/>'
        )

    if phase in ("toe", "heel"):
        pass_dir = "Pass →" if p_step % 2 == 1 else "← Pass"
        deep_tag = " (DEEP)" if (phase == "heel" and extra > 0) else ""
        center_title = f"{phase.upper()}{deep_tag} · {step_info['subphase'].upper()}"
        center_sub1 = f"{in_work} knitting · {lifted_total} lifted"
        center_sub2 = f"Pass {p_step}/{p_total} ({pass_dir})"
        held_lbl = "Held Instep" if (phase == "heel" and extra > 0) else "Held Half"
        legend_html = (
            '<circle cx="42" cy="336" r="4" fill="#0284c7"/>'
            '<text x="51" y="340" font-size="10.5" fill="#334155">Active (' + str(in_work) + ')</text>'
            '<circle cx="136" cy="336" r="4" fill="#d97706"/>'
            '<text x="145" y="340" font-size="10.5" fill="#334155">Parked (' + str(lifted_total) + ')</text>'
            '<circle cx="228" cy="336" r="4" fill="#cbd5e1"/>'
            '<text x="237" y="340" font-size="10.5" fill="#64748b">' + held_lbl + ' (' + str(held_needles) + ')</text>'
        )
    elif phase == "rib":
        center_title = f"RIBBED CUFF ({rib_setup.upper()})"
        center_sub1 = f"{n} cyl + {rib_info['short_spec']}"
        center_sub2 = f"Round {p_step}/{p_total} · {rib_info['engaged_needles']} ribber ndls"
        if rib_info["required_slots"] > 0:
            legend_html = (
                '<circle cx="52" cy="336" r="4" fill="#0f172a"/>'
                '<text x="61" y="340" font-size="10.5" fill="#334155">Cylinder (' + str(n) + ')</text>'
                '<circle cx="164" cy="336" r="4" fill="#0284c7"/>'
                f'<text x="173" y="340" font-size="10.5" fill="#334155">Ribber ({rib_info["required_slots"]} slots, {rib_info["engaged_needles"]} ndls)</text>'
            )
        else:
            legend_html = (
                '<circle cx="96" cy="336" r="4" fill="#0f172a"/>'
                f'<text x="105" y="340" font-size="10.5" fill="#334155">Cylinder Only ({n} needles · No Ribber)</text>'
            )
    elif phase == "hem":
        center_title = "HUNG HEM"
        center_sub1 = step_info["hem_stage"]
        center_sub2 = f"Round {p_step}/{p_total} ({res['hem_half_rows']}+1+{res['hem_half_rows']})"
        hem_col = "#0284c7" if step_info["hem_stage"] == "Outer Hem Face" else (
            "#dc2626" if step_info["hem_stage"] == "Loose Turning Round" else "#d97706"
        )
        legend_html = (
            f'<circle cx="68" cy="336" r="4" fill="{hem_col}"/>'
            f'<text x="77" y="340" font-size="10.5" fill="#334155">{step_info["hem_stage"]} — All {n} Needles</text>'
        )
    else:
        center_title = "FOOT TUBE" if phase == "foot" else "LEG TUBE"
        center_sub1 = f"All {n} needles active"
        center_sub2 = f"Round {p_step}/{p_total} (360°)"
        col = "#d97706" if (phase == "leg" and params["use_colorwork"]) else "#0284c7"
        lbl = "2-Strand Colourwork Leg" if (phase == "leg" and params["use_colorwork"]) else f"Circular Plain Knitting ({n} sts/rd)"
        legend_html = (
            f'<circle cx="72" cy="336" r="4" fill="{col}"/>'
            f'<text x="81" y="340" font-size="10.5" fill="#334155">{lbl}</text>'
        )

    svg = f'''<svg viewBox="0 0 360 355" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Cylinder needle bed diagram">
      <circle cx="{cx}" cy="{cy}" r="{r_outer + 8}" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1"/>
      <circle cx="{cx}" cy="{cy}" r="{r_inner - 8}" fill="#ffffff" stroke="#e2e8f0" stroke-width="1"/>

      <line x1="{cx - r_outer - 14}" y1="{cy}" x2="{cx + r_outer + 14}" y2="{cy}"
            stroke="#94a3b8" stroke-width="1" stroke-dasharray="4 3"/>

      <text x="{cx}" y="22" text-anchor="middle" font-family="Inter, sans-serif" font-size="10.5" fill="#475569">
        BACK HALF (HEEL: 1–{half})
      </text>
      <text x="{cx}" y="318" text-anchor="middle" font-family="Inter, sans-serif" font-size="10.5" fill="#475569">
        FRONT HALF (INSTEP / TOE: {half + 1}–{n})
      </text>

      {"".join(needles_svg)}
      {"".join(ribber_svg)}

      <text x="{cx}" y="{cy - 14}" text-anchor="middle" font-family="Noto Serif, serif" font-size="12" font-weight="700" fill="#0f172a">
        {center_title}
      </text>
      <text x="{cx}" y="{cy + 6}" text-anchor="middle" font-family="Inter, sans-serif" font-size="13" font-weight="600" fill="#0284c7">
        {center_sub1}
      </text>
      <text x="{cx}" y="{cy + 24}" text-anchor="middle" font-family="Inter, sans-serif" font-size="11" fill="#475569">
        {center_sub2}
      </text>

      <g font-family="Inter, sans-serif">
        {legend_html}
      </g>
    </svg>'''

    caption = f"{n} slots · {in_work if phase in ('toe', 'heel') else n} active now"
    return svg, caption


# ---------------------------------------------------------------------------
# HTML Table & CSM Operation-Sheet Export Formatters
# ---------------------------------------------------------------------------


def build_instruction_rows(params, res, unit, rib_setup, active_phase):
    """Build <tbody> HTML rows and cumulative round total for the active sock recipe."""
    n = params["cylinder_needles"]
    half = res["half_needles"]
    center = res["center_needles"]
    toe_lift = res["toe_lift_per_side"]
    heel_lift = res["heel_lift_per_side"]
    heel_work = res["heel_work_needles"]
    heel_held = res["heel_held_needles"]
    deep_extra = res["deep_heel_extra"]
    hem_h = res["hem_half_rows"]
    u = unit_label(unit)
    rib_info = compute_ribber_requirements(n, rib_setup)

    if rib_setup == "plain":
        rib_needles_txt = f"{n} cyl only (no ribber)"
        rib_action_txt = "Knit mock rib or plain cuff transition without ribber dial."
    else:
        rib_needles_txt = f"{n} cyl + {rib_info['short_spec']}"
        rib_action_txt = f"Requires {rib_info['headline']}: {rib_info['detail']}"

    heel_split_label = f"deep +{deep_extra}/side" if deep_extra > 0 else "back half"
    heel_action_txt = (
        f"Park front {heel_held} instep needles; lift {heel_lift} needles/side to "
        f"{center} center, then return to {heel_work}."
    )

    rows_data = [
        (
            "toe",
            "1. Cast-On & Short-Row Toe",
            f"{half} → {center} → {half} (front half)",
            f"{res['toe_passes']} passes",
            res["toe_passes"] // 2,
            f"Hang waste yarn & bonnet; lift {toe_lift} needles/side to {center} center, then return to {half}.",
        ),
        (
            "foot",
            "2. Straight Foot Tube",
            f"All {n} cylinder needles",
            f"{res['foot_rows']} rounds",
            res["foot_rows"],
            f"Knit in the round ({from_cm(res['straight_foot_cm'], unit):.1f} {u}) to heel start.",
        ),
        (
            "heel",
            "3. Short-Row Heel" + (" (Deep)" if deep_extra > 0 else ""),
            f"{heel_work} → {center} → {heel_work} ({heel_split_label})",
            f"{res['heel_passes']} passes",
            res["heel_passes"] // 2,
            heel_action_txt,
        ),
        (
            "leg",
            "4. Leg Tube" + (" (Colourwork)" if params["use_colorwork"] else ""),
            f"All {n} cylinder needles",
            f"{res['leg_rows']} rounds",
            res["leg_rows"],
            "Knit leg using stranded colourwork gauge." if params["use_colorwork"] else "Knit plain tube in the round to cuff start.",
        ),
        (
            "rib",
            f"5. Ribbed Cuff ({rib_setup})",
            rib_needles_txt,
            f"{res['rib_rows']} rounds",
            res["rib_rows"],
            rib_action_txt,
        ),
        (
            "hem",
            "6. Hung Hem & Latch Off",
            f"All {n} cylinder needles",
            f"{hem_h} + 1 + {hem_h}",
            hem_h * 2 + 1,
            f"Knit {hem_h} rds, 1 loose turning rd, {hem_h} rds; hang initial hem loops & latch bind off.",
        ),
    ]

    cum = 0
    html_rows = []
    for phase_key, name, needles_txt, count_txt, rds_add, action_txt in rows_data:
        cum += rds_add
        sel_cls = "is-selected" if active_phase == phase_key else ""
        html_rows.append(
            f'<tr data-phase="{phase_key}" class="{sel_cls}">'
            f'<td>{name}</td>'
            f'<td class="mono-cell">{needles_txt}</td>'
            f'<td class="num-col">{count_txt}</td>'
            f'<td class="num-col">{cum}</td>'
            f'<td>{action_txt}</td>'
            f'</tr>'
        )
    return "".join(html_rows), cum


def build_sizing_rows(params, unit):
    """Build <tbody> HTML rows and raw tuple records across all six adult shoe sizes."""
    active_foot_cm = params["foot_length_cm"]
    html_rows = []
    chart_rows = []

    for label, foot_cm in ADULT_SIZES:
        r = calculate_csm_sock(
            cylinder_needles=params["cylinder_needles"],
            swatch_stitches=params["swatch_stitches"],
            swatch_width_cm=params["swatch_width_cm"],
            swatch_rows=params["swatch_rows"],
            swatch_height_cm=params["swatch_height_cm"],
            foot_length_cm=foot_cm,
            colorwork_rows_in_swatch=params["colorwork_rows"],
            leg_height_cm=params["leg_height_cm"],
            rib_cuff_cm=params["rib_cuff_cm"],
            hem_depth_cm=params["hem_depth_cm"],
            negative_ease_pct=params["negative_ease_pct"],
            toe_center_ratio=params["toe_center_ratio"],
            plateau_needles=params.get("plateau_needles"),
            deep_heel_extra=params.get("deep_heel_extra", 0),
        )
        hem_str = f"{r['hem_half_rows']}+1+{r['hem_half_rows']}"
        is_match = abs(foot_cm - active_foot_cm) < 0.26
        sel_cls = "is-selected" if is_match else ""
        disp_foot = from_cm(foot_cm, unit)
        html_rows.append(
            f'<tr data-foot-cm="{foot_cm}" class="{sel_cls}">'
            f'<td class="mono-cell">{label}</td>'
            f'<td class="num-col">{disp_foot:.1f}</td>'
            f'<td class="num-col">{r["toe_passes"]}</td>'
            f'<td class="num-col">{r["foot_rows"]}</td>'
            f'<td class="num-col">{r["heel_passes"]}</td>'
            f'<td class="num-col">{r["leg_rows"]}</td>'
            f'<td class="num-col">{r["rib_rows"]}</td>'
            f'<td class="num-col">{hem_str}</td>'
            f'</tr>'
        )
        chart_rows.append((label, foot_cm, disp_foot, r, hem_str))

    return "".join(html_rows), chart_rows


def build_plaintext_bench_sheet(params, res, chart_rows, unit, rib_setup="1x1"):
    """Format fixed-width monospace CSM operation sheet (uses f-string padding for MicroPython)."""
    u = unit_label(unit)
    sw_w = from_cm(params["swatch_width_cm"], unit)
    sw_h = from_cm(params["swatch_height_cm"], unit)
    rel_c = from_cm(res["relaxed_circ_cm"], unit)
    rec_c = from_cm(res["recommended_foot_circ_cm"], unit)
    rib_info = compute_ribber_requirements(params["cylinder_needles"], rib_setup)

    lines = [
        f"=== CSM OPERATION SHEET: {params['cylinder_needles']}-NEEDLE CYLINDER ===",
        f"Swatch: {params['swatch_stitches']:.1f} sts / {sw_w:.1f} {u} | {params['swatch_rows']:.1f} rows / {sw_h:.1f} {u}",
    ]
    if params["use_colorwork"]:
        lines.append(f"Leg Colourwork Gauge: {params['colorwork_rows']:.1f} rows / {sw_h:.1f} {u}")
    foot_hdr = f"Foot({u})"
    heel_line = (
        f"Short-Row Heel (Deep +{res['deep_heel_extra']}/side): "
        f"{res['heel_work_needles']} -> {res['center_needles']} -> {res['heel_work_needles']} needles "
        f"({res['heel_lift_per_side']} lifted/side = {res['heel_passes']} passes)"
        if res["deep_heel_extra"] > 0
        else f"Short-Row Heel: {res['half_needles']} -> {res['center_needles']} -> {res['half_needles']} needles ({res['heel_lift_per_side']} lifted/side = {res['heel_passes']} passes)"
    )
    lines.extend([
        f"Relaxed Tube Circ: {rel_c:.1f} {u} (Fits ~{rec_c:.1f} {u} ball-of-foot at {params['negative_ease_pct']:.0f}% negative ease)",
        f"Short-Row Toe: {res['half_needles']} -> {res['center_needles']} -> {res['half_needles']} needles ({res['toe_lift_per_side']} lifted/side = {res['toe_passes']} passes, {res['plateau_pct']:.0f}% plateau)",
        heel_line,
        f"Cuff Ribber ({rib_setup}): {rib_info['headline']} — {rib_info['detail']}",
        "",
        f"{'Shoe Size':<36} | {foot_hdr:<8} | {'Toe':<4} | {'Foot':<4} | {'Heel':<4} | {'Leg':<4} | {'Rib':<4} | {'Hem':<9}",
        "-" * 88,
    ])
    for label, _, disp_foot, r, hem_str in chart_rows:
        lines.append(
            f"{label:<36} | {disp_foot:<8.1f} | {r['toe_passes']:<4} | "
            f"{r['foot_rows']:<4} | {r['heel_passes']:<4} | {r['leg_rows']:<4} | "
            f"{r['rib_rows']:<4} | {hem_str:<9}"
        )
    return "\n".join(lines)


def build_csv_bench_sheet(chart_rows, unit):
    """Format the 6-size comparison chart as CSV for spreadsheet import."""
    u = unit_label(unit)
    lines = [
        f"Shoe Size,Foot ({u}),Toe Passes,Foot Rounds,Heel Passes,Leg Rounds,Rib Rounds,Hung Hem"
    ]
    for label, _, disp_foot, r, hem_str in chart_rows:
        lines.append(
            f'"{label}",{disp_foot:.1f},{r["toe_passes"]},{r["foot_rows"]},{r["heel_passes"]},{r["leg_rows"]},{r["rib_rows"]},{hem_str}'
        )
    return "\n".join(lines)


def build_markdown_bench_sheet(params, res, chart_rows, unit, rib_setup="1x1"):
    """Format a Markdown workshop CSM operation sheet with gauge summary and sizing table."""
    u = unit_label(unit)
    rib_info = compute_ribber_requirements(params["cylinder_needles"], rib_setup)
    heel_md = (
        f"- **Short-Row Heel (Deep +{res['deep_heel_extra']}/side)**: "
        f"`{res['heel_work_needles']} -> {res['center_needles']} -> {res['heel_work_needles']}` "
        f"({res['heel_lift_per_side']} lifted/side = {res['heel_passes']} passes)"
        if res["deep_heel_extra"] > 0
        else f"- **Short-Row Heel**: `{res['half_needles']} -> {res['center_needles']} -> {res['half_needles']}` ({res['heel_lift_per_side']} lifted/side = {res['heel_passes']} passes)"
    )
    md = [
        f"# CSM Operation Sheet — {params['cylinder_needles']}-Needle Cylinder",
        "",
        f"- **Swatch**: {params['swatch_stitches']:.1f} sts / {from_cm(params['swatch_width_cm'], unit):.1f} {u} · {params['swatch_rows']:.1f} rows / {from_cm(params['swatch_height_cm'], unit):.1f} {u}",
        f"- **Relaxed Tube Circumference**: {from_cm(res['relaxed_circ_cm'], unit):.1f} {u} (Fits ~{from_cm(res['recommended_foot_circ_cm'], unit):.1f} {u} ball-of-foot at {params['negative_ease_pct']:.0f}% negative ease)",
        f"- **Short-Row Toe**: `{res['half_needles']} -> {res['center_needles']} -> {res['half_needles']}` ({res['toe_lift_per_side']} lifted/side = {res['toe_passes']} passes, {res['plateau_pct']:.0f}% plateau)",
        heel_md,
        f"- **Cuff Ribber ({rib_setup})**: {rib_info['headline']} — {rib_info['detail']}",
        "",
        f"| Shoe Size | Foot ({u}) | Toe | Foot | Heel | Leg | Rib | Hem |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for label, _, disp_foot, r, hem_str in chart_rows:
        md.append(
            f"| {label} | {disp_foot:.1f} | {r['toe_passes']} | {r['foot_rows']} | {r['heel_passes']} | {r['leg_rows']} | {r['rib_rows']} | {hem_str} |"
        )
    return "\n".join(md)


if __name__ == "__main__":
    # Reference example showing how to call the principal functions in sock_math.py.
    # Run directly with: python3 public/sock_math.py
    sample_unit = "metric"
    sample_rib = "1x1"
    sample_params = {
        "cylinder_needles": 60,
        "swatch_stitches": 15.0,
        "swatch_width_cm": 5.0,
        "swatch_rows": 21.0,
        "swatch_height_cm": 5.0,
        "use_colorwork": False,
        "colorwork_rows": None,
        "foot_length_cm": 25.5,
        "leg_height_cm": 14.0,
        "rib_cuff_cm": 4.0,
        "hem_depth_cm": 2.0,
        "negative_ease_pct": 10.0,
        "toe_center_ratio": 0.35,
        "plateau_needles": None,
        "deep_heel_extra": 2,
    }

    # 1. Ribber slot requirements for the cylinder & cuff style
    rib_req = compute_ribber_requirements(sample_params["cylinder_needles"], sample_rib)
    print("=== 1. RIBBER REQUIREMENTS ===")
    print(f"Pattern: {sample_rib} | Required: {rib_req['headline']} | {rib_req['detail']}\n")

    # 2. Core sock pattern calculations (including Deep Heel & Plateau options)
    res = calculate_csm_sock(
        cylinder_needles=sample_params["cylinder_needles"],
        swatch_stitches=sample_params["swatch_stitches"],
        swatch_width_cm=sample_params["swatch_width_cm"],
        swatch_rows=sample_params["swatch_rows"],
        swatch_height_cm=sample_params["swatch_height_cm"],
        foot_length_cm=sample_params["foot_length_cm"],
        colorwork_rows_in_swatch=sample_params["colorwork_rows"],
        leg_height_cm=sample_params["leg_height_cm"],
        rib_cuff_cm=sample_params["rib_cuff_cm"],
        hem_depth_cm=sample_params["hem_depth_cm"],
        negative_ease_pct=sample_params["negative_ease_pct"],
        toe_center_ratio=sample_params["toe_center_ratio"],
        plateau_needles=sample_params["plateau_needles"],
        deep_heel_extra=sample_params["deep_heel_extra"],
    )
    print("=== 2. CALCULATE_CSM_SOCK OUTPUT ===")
    for key in (
        "relaxed_circ_cm",
        "recommended_foot_circ_cm",
        "half_needles",
        "center_needles",
        "plateau_pct",
        "toe_lift_per_side",
        "toe_passes",
        "deep_heel_extra",
        "heel_work_needles",
        "heel_held_needles",
        "heel_lift_per_side",
        "heel_passes",
        "foot_rows",
        "foot_overflow",
        "leg_rows",
        "rib_rows",
        "hem_half_rows",
    ):
        print(f"  {key:<25}: {res[key]}")
    print()

    # 3. Timeline resolution & SVG schematic builders
    mid_heel_step = phase_target_step(res, "heel")
    step_info = resolve_step(res, mid_heel_step)
    sock_svg, sock_caption = build_sock_svg(sample_params, res, step_info, sample_unit, sample_rib)
    cyl_svg, cyl_caption = build_cylinder_svg(sample_params, res, step_info, sample_rib)

    print("=== 3. TIMELINE & SVG SCHEMATICS ===")
    print(f"Heel midpoint step : {step_info['step']} / {step_info['total_steps']} ({step_info['subphase']})")
    print(f"Needle state       : {step_info['in_work']} knitting, {step_info['left_lifted']}L + {step_info['right_lifted']}R lifted, {step_info['held_needles']} held")
    print(f"Sock SVG           : {len(sock_svg)} chars | {sock_caption}")
    print(f"Cylinder SVG       : {len(cyl_svg)} chars | {cyl_caption}\n")

    # 4. Instruction table, adult sizing chart & CSM operation sheet exports
    inst_html, total_rounds = build_instruction_rows(sample_params, res, sample_unit, sample_rib, step_info["phase"])
    sizing_html, chart_rows = build_sizing_rows(sample_params, sample_unit)
    bench_txt = build_plaintext_bench_sheet(sample_params, res, chart_rows, sample_unit, sample_rib)
    bench_csv = build_csv_bench_sheet(chart_rows, sample_unit)
    bench_md = build_markdown_bench_sheet(sample_params, res, chart_rows, sample_unit, sample_rib)

    print("=== 4. TABLES & CSM OPERATION SHEET EXPORTS ===")
    print(f"Recipe cumulative rounds : {total_rounds} rds ({len(inst_html)} HTML chars)")
    print(f"Sizing rows generated    : {len(chart_rows)} sizes ({len(sizing_html)} HTML chars)")
    print(f"CSV / Markdown lengths   : {len(bench_csv)} / {len(bench_md)} chars\n")
    print(bench_txt)


