# PyScript MicroPython DOM controller for the CSM Sock Planner web app.

"""Architecture & Responsibilities:
- Loaded by `index.html` via `<script type="mpy" src="sock_planner.py" config="pyscript.toml">`.
- `pyscript.toml` mounts `sock_math.py` so all pure math, timeline resolution,
  SVG generation, and CSM operation-sheet formatting stay decoupled from DOM calls.
- All UI-to-DOM updates flow through `render_all()`, which reads the current
  HTML inputs (`get_params()`), runs `calculate_csm_sock()`, and updates KPIs,
  the step scrubber, dual SVGs, recipe/sizing tables, and export previews.

MicroPython / PyScript Maintenance Notes:
- Avoid stacked `@when` decorators on a single function; bind each DOM selector
  with its own thin handler wrapper.
- Guard `event.target.closest(...)` with `hasattr(target, "closest")` in case a
  click originates on a non-Element DOM node.
- During live `input` events, never overwrite the element the user is currently
  typing into—defer parity/range snapping to `change` (blur/Enter) or chip clicks.
"""

from pyscript import document, when, window
from sock_math import (
    CM_PER_INCH,
    build_csv_bench_sheet,
    build_cylinder_svg,
    build_instruction_rows,
    build_markdown_bench_sheet,
    build_plaintext_bench_sheet,
    build_sizing_rows,
    build_sock_svg,
    calculate_csm_sock,
    compute_plateau_needles,
    compute_ribber_requirements,
    from_cm,
    phase_target_step,
    plateau_bounds,
    resolve_step,
    title,
    to_cm,
    unit_label,
)

# ---------------------------------------------------------------------------
# UI State & Safe Input Parsing
# ---------------------------------------------------------------------------

# In-memory UI state not stored directly in an <input> value:
# - unit: "metric" (cm) or "imperial" (in); all math converts inputs to cm first.
# - rib_setup: "1x1", "2x2", "3x1", or "plain" (Mock).
# - active_phase / current_step: synchronized with the step-scrubber timeline.
# - plateau_mode: "pct" or "needles" — tracks which Toe/Heel Plateau input was
#   edited last so cylinder count changes preserve that anchor field.
state = {
    "unit": "metric",
    "rib_setup": "1x1",
    "active_phase": "toe",
    "current_step": 20,
    "plateau_mode": "pct",
}


def _read_float(selector, fallback, min_val=0.0):
    """Read a numeric float input safely without mutating the DOM mid-typing."""
    el = document.querySelector(selector)
    if not el:
        return fallback
    raw = str(el.value).strip()
    if not raw:
        return fallback
    try:
        val = float(raw)
        if val < min_val:
            return min_val
        return val
    except ValueError:
        return fallback


def _read_int(selector, fallback, min_val=24, max_val=120):
    """Read and clamp an integer input safely (tolerates decimal strings like '60.0')."""
    el = document.querySelector(selector)
    if not el:
        return fallback
    raw = str(el.value).strip()
    if not raw:
        return fallback
    try:
        val = int(float(raw))
        if val < min_val:
            return min_val
        if val > max_val:
            return max_val
        return val
    except ValueError:
        return fallback


# ---------------------------------------------------------------------------
# DOM Parameter Collection & Calculation Bridge
# ---------------------------------------------------------------------------


def get_params():
    """Collect, validate, and normalize all form inputs into metric (`cm`) params."""
    unit = state["unit"]
    cyl = _read_int("#cylinder-needles", 60, 12, 200)
    warning_el = document.querySelector("#cylinder-warning")
    # CSM toe/heel short rows require an even cylinder count for a 50/50 split
    if cyl % 2 != 0:
        adj = cyl + 1 if cyl < 200 else cyl - 1
        warning_el.innerText = f"Odd count ({cyl}) adjusted to {adj} for 50/50 instep & heel split."
        warning_el.classList.remove("is-hidden")
        cyl = adj
    else:
        warning_el.classList.add("is-hidden")

    swatch_stitches = _read_float("#swatch-stitches", 15.0, 1.0)
    swatch_width_cm = max(0.2, to_cm(_read_float("#swatch-width", 5.0, 0.2), unit))
    swatch_rows = _read_float("#swatch-rows", 21.0, 1.0)
    swatch_height_cm = max(0.2, to_cm(_read_float("#swatch-height", 5.0, 0.2), unit))

    use_cw_el = document.querySelector("#use-colorwork")
    use_cw = bool(use_cw_el and use_cw_el.checked)
    cw_rows = _read_float("#colorwork-rows", 25.0, 1.0) if use_cw else None

    foot_length_cm = max(5.0, to_cm(_read_float("#foot-length", 25.5, 4.0), unit))
    leg_height_cm = max(0.5, to_cm(_read_float("#leg-height", 14.0, 0.5), unit))
    rib_cuff_cm = max(0.0, to_cm(_read_float("#rib-cuff", 4.0, 0.0), unit))
    hem_depth_cm = max(0.2, to_cm(_read_float("#hem-depth", 2.0, 0.2), unit))
    neg_ease = min(30.0, max(0.0, _read_float("#negative-ease", 10.0, 0.0)))
    deep_heel_extra = _read_int("#deep-heel-extra", 0, 0, 40)
    min_n, max_n, min_pct, max_pct = plateau_bounds(cyl // 2)
    plateau_pct = min(max_pct, max(min_pct, _read_float("#toe-plateau-pct", 35.0, 0.1)))
    toe_ratio = plateau_pct / 100.0
    plateau_needles = (
        _read_int("#toe-plateau-needles", min_n, min_n, max_n)
        if state["plateau_mode"] == "needles"
        else None
    )

    target_ball_raw = _read_float("#target-ball-circ", 0.0, 0.0)
    target_ball_cm = to_cm(target_ball_raw, unit) if target_ball_raw > 0 else None

    return {
        "cylinder_needles": cyl,
        "swatch_stitches": swatch_stitches,
        "swatch_width_cm": swatch_width_cm,
        "swatch_rows": swatch_rows,
        "swatch_height_cm": swatch_height_cm,
        "use_colorwork": use_cw,
        "colorwork_rows": cw_rows,
        "foot_length_cm": foot_length_cm,
        "leg_height_cm": leg_height_cm,
        "rib_cuff_cm": rib_cuff_cm,
        "hem_depth_cm": hem_depth_cm,
        "negative_ease_pct": neg_ease,
        "toe_center_ratio": toe_ratio,
        "plateau_needles": plateau_needles,
        "deep_heel_extra": deep_heel_extra,
        "target_ball_cm": target_ball_cm,
    }


def _compute_current(params):
    """Run `calculate_csm_sock` from a normalized parameter dictionary."""
    return calculate_csm_sock(
        cylinder_needles=params["cylinder_needles"],
        swatch_stitches=params["swatch_stitches"],
        swatch_width_cm=params["swatch_width_cm"],
        swatch_rows=params["swatch_rows"],
        swatch_height_cm=params["swatch_height_cm"],
        foot_length_cm=params["foot_length_cm"],
        colorwork_rows_in_swatch=params["colorwork_rows"],
        leg_height_cm=params["leg_height_cm"],
        rib_cuff_cm=params["rib_cuff_cm"],
        hem_depth_cm=params["hem_depth_cm"],
        negative_ease_pct=params["negative_ease_pct"],
        toe_center_ratio=params["toe_center_ratio"],
        plateau_needles=params.get("plateau_needles"),
        deep_heel_extra=params.get("deep_heel_extra", 0),
    )


# ---------------------------------------------------------------------------
# Full Stage Render Pipeline
# ---------------------------------------------------------------------------


def render_all():
    """Recompute the full pattern and refresh every KPI, chart, SVG, and export preview."""
    unit = state["unit"]
    u = unit_label(unit)
    params = get_params()
    res = _compute_current(params)

    st_rate = res["st_per_cm"] * CM_PER_INCH if unit == "imperial" else res["st_per_cm"]
    plain_rate = res["plain_rows_per_cm"] * CM_PER_INCH if unit == "imperial" else res["plain_rows_per_cm"]
    leg_rate = res["leg_rows_per_cm"] * CM_PER_INCH if unit == "imperial" else res["leg_rows_per_cm"]

    document.querySelector("#metric-circ").innerText = f"{from_cm(res['relaxed_circ_cm'], unit):.1f} {u}"
    document.querySelector("#metric-circ-sub").innerText = (
        f"{params['cylinder_needles']} needles · {st_rate:.2f} sts/{u}"
    )

    rec_foot_disp = from_cm(res["recommended_foot_circ_cm"], unit)
    document.querySelector("#metric-fit-circ").innerText = f"{rec_foot_disp:.1f} {u}"
    fit_el = document.querySelector("#metric-fit-status")
    fit_el.className = "kpi-sub"

    if params["target_ball_cm"] is not None:
        diff_cm = params["target_ball_cm"] - res["recommended_foot_circ_cm"]
        if abs(diff_cm) <= 1.2:
            fit_el.innerText = f"Nominal fit ({params['negative_ease_pct']:.0f}% ease)"
            fit_el.classList.add("fit-nominal")
        elif diff_cm > 1.2:
            fit_el.innerText = f"Tight by {from_cm(diff_cm, unit):.1f} {u} — size up cylinder"
            fit_el.classList.add("fit-tight")
        else:
            fit_el.innerText = f"Loose by {from_cm(-diff_cm, unit):.1f} {u} — size down cylinder"
            fit_el.classList.add("fit-loose")
    else:
        fit_el.innerText = f"Nominal {params['negative_ease_pct']:.0f}% ease target"
        fit_el.classList.add("fit-nominal")

    document.querySelector("#metric-gauge").innerText = f"{plain_rate:.2f} / {leg_rate:.2f}"
    document.querySelector("#metric-gauge-sub").innerText = (
        f"rows/{u} · {'colourwork leg' if params['use_colorwork'] else 'plain leg'}"
    )

    step_info = resolve_step(res, state["current_step"])
    state["current_step"] = step_info["step"]
    state["active_phase"] = step_info["phase"]

    slider = document.querySelector("#step-slider")
    if slider:
        slider.min = "1"
        slider.max = str(step_info["total_steps"])
        slider.value = str(step_info["step"])

    readout = document.querySelector("#scrub-readout")
    if readout:
        p = step_info["phase"]
        ps = step_info["phase_step"]
        pt = step_info["phase_total"]
        if p in ("toe", "heel"):
            readout.innerText = (
                f"Step {step_info['step']} / {step_info['total_steps']} · "
                f"{title(p)} Pass {ps}/{pt} ({step_info['subphase']}) · "
                f"{step_info['in_work']} in work, {step_info['left_lifted'] + step_info['right_lifted']} lifted"
            )
        elif p == "hem":
            readout.innerText = (
                f"Step {step_info['step']} / {step_info['total_steps']} · "
                f"Hung Hem Round {ps}/{pt} ({step_info['hem_stage']})"
            )
        elif p == "rib":
            readout.innerText = (
                f"Step {step_info['step']} / {step_info['total_steps']} · "
                f"Ribbed Cuff ({state['rib_setup']}) Round {ps}/{pt} · All {params['cylinder_needles']} cyl + ribber"
            )
        else:
            readout.innerText = (
                f"Step {step_info['step']} / {step_info['total_steps']} · "
                f"{title(p)} Round {ps}/{pt} · All {params['cylinder_needles']} needles in work"
            )

    rib_info = compute_ribber_requirements(params["cylinder_needles"], state["rib_setup"])
    rib_hl = document.querySelector("#ribber-slots-headline")
    if rib_hl:
        rib_hl.innerText = rib_info["headline"]
    rib_det = document.querySelector("#ribber-slots-detail")
    if rib_det:
        rib_det.innerText = rib_info["detail"]
    rib_warn = document.querySelector("#ribber-warning")
    if rib_warn:
        if rib_info["repeat_note"]:
            rib_warn.innerText = rib_info["repeat_note"]
            rib_warn.classList.remove("is-hidden")
        else:
            rib_warn.classList.add("is-hidden")

    inst_html, total_rounds = build_instruction_rows(params, res, unit, state["rib_setup"], state["active_phase"])
    document.querySelector("#instruction-tbody").innerHTML = inst_html
    document.querySelector("#metric-total-rounds").innerText = f"{total_rounds} rds"
    if res["deep_heel_extra"] > 0:
        document.querySelector("#metric-short-row-sub").innerText = (
            f"Toe {res['half_needles']}→{res['center_needles']} · "
            f"Heel {res['heel_work_needles']}→{res['center_needles']} (+{res['deep_heel_extra']}/s)"
        )
    else:
        document.querySelector("#metric-short-row-sub").innerText = (
            f"{res['half_needles']} → {res['center_needles']} → {res['half_needles']} short-row split"
        )

    deep_summary = f" · Deep Heel +{res['deep_heel_extra']}/s" if res["deep_heel_extra"] > 0 else ""
    document.querySelector("#instruction-summary-line").innerText = (
        f"{params['cylinder_needles']}-Needle Cylinder · "
        f"{rib_info['short_spec']} ({state['rib_setup']}) · "
        f"{from_cm(params['swatch_width_cm'], unit):.1f} × {from_cm(params['swatch_height_cm'], unit):.1f} {u} Swatch · "
        f"{params['negative_ease_pct']:.0f}% Ease{deep_summary}"
    )

    deep_el = document.querySelector("#deep-heel-extra")
    if deep_el:
        deep_el.max = str(res["max_deep_heel_extra"])

    min_n, max_n, min_pct, max_pct = plateau_bounds(res["half_needles"])
    ndls_el = document.querySelector("#toe-plateau-needles")
    if ndls_el:
        ndls_el.min = str(min_n)
        ndls_el.max = str(max_n)
        ndls_el.step = "2"
    pct_el = document.querySelector("#toe-plateau-pct")
    if pct_el:
        pct_el.min = f"{min_pct:.1f}"
        pct_el.max = f"{max_pct:.1f}"
        pct_el.step = "0.1"
    pct_readout = document.querySelector("#toe-plateau-pct-readout")
    if pct_readout:
        pct_readout.innerText = _format_pct(res["plateau_pct"])

    heel_warn = document.querySelector("#heel-warning")
    if heel_warn:
        notes = []
        if params.get("deep_heel_extra", 0) > res["max_deep_heel_extra"]:
            notes.append(
                f"Deep Heel capped at +{res['max_deep_heel_extra']}/side to keep at least 4 instep needles held."
            )
        if res["foot_overflow"]:
            notes.append(
                "Toe + Deep Heel length exceeds eased foot length; straight Foot rounds reduced to 0."
            )
        if notes:
            heel_warn.innerText = " ".join(notes)
            heel_warn.classList.remove("is-hidden")
        else:
            heel_warn.classList.add("is-hidden")

    document.querySelector("#foot-length-readout").innerText = f"{_read_float('#foot-length', 25.5):.1f}"
    document.querySelector("#leg-height-readout").innerText = f"{_read_float('#leg-height', 14.0):.1f}"
    document.querySelector("#cw-height-mirror").innerText = f"{_read_float('#swatch-height', 5.0):.1f}"

    matched_preset = False
    for btn in document.querySelectorAll(".cyl-btn"):
        val = int(btn.getAttribute("data-cyl"))
        if val == params["cylinder_needles"]:
            btn.classList.add("is-active")
            matched_preset = True
        else:
            btn.classList.remove("is-active")
    custom_btn = document.querySelector("#cyl-custom-btn")
    if custom_btn:
        if matched_preset:
            custom_btn.classList.remove("is-active")
        else:
            custom_btn.classList.add("is-active")

    for btn in document.querySelectorAll(".phase-btn"):
        if btn.getAttribute("data-phase") == state["active_phase"]:
            btn.classList.add("is-active")
        else:
            btn.classList.remove("is-active")

    sock_svg, sock_cap = build_sock_svg(params, res, step_info, unit, state["rib_setup"])
    document.querySelector("#sock-svg-stage").innerHTML = sock_svg
    document.querySelector("#sock-zone-caption").innerText = sock_cap

    cyl_svg, cyl_cap = build_cylinder_svg(params, res, step_info, state["rib_setup"])
    document.querySelector("#cylinder-svg-stage").innerHTML = cyl_svg
    document.querySelector("#cylinder-zone-caption").innerText = cyl_cap

    sizing_html, chart_rows = build_sizing_rows(params, unit)
    document.querySelector("#sizing-tbody").innerHTML = sizing_html
    document.querySelector("#bench-preview").innerText = build_plaintext_bench_sheet(
        params, res, chart_rows, unit, state["rib_setup"]
    )


# ---------------------------------------------------------------------------
# Unit Conversion & Bidirectional Plateau Sync
# ---------------------------------------------------------------------------


def _update_unit_labels():
    """Sync unit suffix labels ('cm'/'in') and Metric/Imperial toggle buttons."""
    u = unit_label(state["unit"])
    for el in document.querySelectorAll(".unit-len"):
        el.innerText = u
    for btn in document.querySelectorAll(".unit-btn"):
        if btn.getAttribute("data-unit") == state["unit"]:
            btn.classList.add("is-active")
        else:
            btn.classList.remove("is-active")


def _convert_all_dimension_inputs(to_unit):
    """Convert all length inputs and slider bounds when switching between cm and inches."""
    if state["unit"] == to_unit:
        return
    factor = (1.0 / CM_PER_INCH) if to_unit == "imperial" else CM_PER_INCH
    ids = [
        "#swatch-width",
        "#swatch-height",
        "#foot-length",
        "#leg-height",
        "#rib-cuff",
        "#hem-depth",
        "#target-ball-circ",
    ]
    for sel in ids:
        el = document.querySelector(sel)
        if el and str(el.value).strip():
            val = float(el.value) * factor
            el.value = f"{val:.1f}"

    foot_rng = document.querySelector("#foot-length-range")
    leg_rng = document.querySelector("#leg-height-range")
    if to_unit == "imperial":
        foot_rng.min, foot_rng.max, foot_rng.step = "7.0", "13.0", "0.2"
        leg_rng.min, leg_rng.max, leg_rng.step = "1.0", "14.0", "0.2"
    else:
        foot_rng.min, foot_rng.max, foot_rng.step = "18.0", "33.0", "0.5"
        leg_rng.min, leg_rng.max, leg_rng.step = "2.0", "35.0", "0.5"

    foot_rng.value = document.querySelector("#foot-length").value
    leg_rng.value = document.querySelector("#leg-height").value
    state["unit"] = to_unit
    _update_unit_labels()


def _format_pct(pct_val):
    """Format plateau percentages cleanly without trailing '.0' on whole numbers."""
    rounded = round(pct_val, 1)
    if abs(rounded - round(rounded)) < 0.05:
        return str(int(round(rounded)))
    return f"{rounded:.1f}"


def _sync_plateau_pair(source, snap_active=False):
    """Keep Toe/Heel Plateau % slider and min-needle count synchronized.

    Updates the legal `min`/`max`/`step` attributes for the active cylinder
    first. During live dragging/typing (`snap_active=False`), updates only the
    sibling control and readout; on release/commit (`snap_active=True`), also
    snaps the active slider or needle input to the exact legal parity value.
    """
    cyl = _read_int("#cylinder-needles", 60, 12, 200)
    if cyl % 2 != 0:
        cyl = cyl + 1 if cyl < 200 else cyl - 1
    half = cyl // 2
    min_n, max_n, min_pct, max_pct = plateau_bounds(half)
    pct_el = document.querySelector("#toe-plateau-pct")
    ndl_el = document.querySelector("#toe-plateau-needles")
    readout_el = document.querySelector("#toe-plateau-pct-readout")
    if not pct_el or not ndl_el:
        return

    ndl_el.min = str(min_n)
    ndl_el.max = str(max_n)
    ndl_el.step = "2"
    pct_el.min = f"{min_pct:.1f}"
    pct_el.max = f"{max_pct:.1f}"
    pct_el.step = "0.1"

    if source == "needles":
        raw_n = _read_int("#toe-plateau-needles", min_n, min_n, max_n)
        center_n, actual_pct = compute_plateau_needles(half, plateau_needles=raw_n)
        pct_el.value = f"{actual_pct:.1f}"
        if snap_active:
            ndl_el.value = str(center_n)
    else:
        pct_val = min(max_pct, max(min_pct, _read_float("#toe-plateau-pct", 35.0, 0.1)))
        center_n, actual_pct = compute_plateau_needles(half, plateau_pct=pct_val)
        ndl_el.value = str(center_n)
        if snap_active:
            pct_el.value = f"{actual_pct:.1f}"

    if readout_el:
        readout_el.innerText = _format_pct(actual_pct)


# ---------------------------------------------------------------------------
# Interactive Event Bindings (@when)
# ---------------------------------------------------------------------------


def _handle_param_event(event):
    """Central dispatcher for `.param-input` `input` and `change` events."""
    target = event.target
    # Mirror paired range sliders and number boxes linked via `data-sync`
    sync_id = target.getAttribute("data-sync")
    if sync_id:
        partner = document.querySelector(f"#{sync_id}")
        if partner:
            partner.value = target.value

    if target.id == "use-colorwork":
        cw_input = document.querySelector("#colorwork-rows")
        cw_group = document.querySelector("#colorwork-group")
        if target.checked:
            cw_input.disabled = False
            cw_group.classList.remove("is-disabled")
        else:
            cw_input.disabled = True
            cw_group.classList.add("is-disabled")
    elif target.id == "toe-plateau-pct":
        state["plateau_mode"] = "pct"
        _sync_plateau_pair("pct", snap_active=(getattr(event, "type", "") == "change"))
    elif target.id == "toe-plateau-needles":
        state["plateau_mode"] = "needles"
        _sync_plateau_pair("needles", snap_active=(getattr(event, "type", "") == "change"))
    elif target.id == "cylinder-needles":
        _sync_plateau_pair(state["plateau_mode"], snap_active=True)

    render_all()


@when("input", ".param-input")
def on_param_input(event):
    _handle_param_event(event)


@when("change", ".param-input")
def on_param_change(event):
    _handle_param_event(event)


@when("click", ".unit-btn")
def on_unit_click(event):
    target = event.target
    btn = target.closest(".unit-btn") if hasattr(target, "closest") else None
    if not btn:
        return
    _convert_all_dimension_inputs(btn.getAttribute("data-unit"))
    render_all()


@when("click", ".cyl-btn")
def on_cyl_click(event):
    target = event.target
    btn = target.closest(".cyl-btn") if hasattr(target, "closest") else None
    if not btn:
        return
    document.querySelector("#cylinder-needles").value = btn.getAttribute("data-cyl")
    _sync_plateau_pair(state["plateau_mode"], snap_active=True)
    render_all()


@when("click", "#cyl-custom-btn")
def on_cyl_custom_click(event):
    for btn in document.querySelectorAll(".cyl-btn"):
        btn.classList.remove("is-active")
    custom_btn = document.querySelector("#cyl-custom-btn")
    if custom_btn:
        custom_btn.classList.add("is-active")
    cyl_input = document.querySelector("#cylinder-needles")
    if cyl_input:
        cyl_input.focus()
        if hasattr(cyl_input, "select"):
            cyl_input.select()


@when("click", ".rib-btn")
def on_rib_click(event):
    target = event.target
    btn = target.closest(".rib-btn") if hasattr(target, "closest") else None
    if not btn:
        return
    state["rib_setup"] = btn.getAttribute("data-rib")
    for el in document.querySelectorAll(".rib-btn"):
        if el.getAttribute("data-rib") == state["rib_setup"]:
            el.classList.add("is-active")
        else:
            el.classList.remove("is-active")
    render_all()


def _jump_to_phase(phase_name):
    """Move the step scrubber to the midpoint of `phase_name` and re-render."""
    res = _compute_current(get_params())
    state["active_phase"] = phase_name
    state["current_step"] = phase_target_step(res, phase_name)
    render_all()


@when("click", ".phase-btn")
def on_phase_btn_click(event):
    target = event.target
    btn = target.closest(".phase-btn") if hasattr(target, "closest") else None
    if not btn:
        return
    _jump_to_phase(btn.getAttribute("data-phase"))


def _select_phase_from_target(target):
    """Delegate click events inside SVG zones or recipe rows carrying `data-phase`."""
    hit = target.closest("[data-phase]") if hasattr(target, "closest") else None
    if not hit:
        return
    _jump_to_phase(hit.getAttribute("data-phase"))


@when("click", "#sock-svg-stage")
def on_svg_phase_click(event):
    _select_phase_from_target(event.target)


@when("click", "#instruction-tbody")
def on_table_phase_click(event):
    _select_phase_from_target(event.target)


@when("input", "#step-slider")
def on_step_slider_input(event):
    state["current_step"] = int(float(event.target.value))
    render_all()


@when("change", "#step-slider")
def on_step_slider_change(event):
    state["current_step"] = int(float(event.target.value))
    render_all()


@when("click", "#btn-step-prev")
def on_step_prev(event):
    state["current_step"] = max(1, state["current_step"] - 1)
    render_all()


@when("click", "#btn-step-next")
def on_step_next(event):
    state["current_step"] = state["current_step"] + 1
    render_all()


@when("click", "#sizing-tbody")
def on_sizing_row_click(event):
    """Snap Foot Length when the user clicks a row in the Adult Sizing Chart."""
    target = event.target
    row = target.closest("[data-foot-cm]") if hasattr(target, "closest") else None
    if not row:
        return
    foot_cm = float(row.getAttribute("data-foot-cm"))
    disp = from_cm(foot_cm, state["unit"])
    document.querySelector("#foot-length").value = f"{disp:.1f}"
    document.querySelector("#foot-length-range").value = f"{disp:.1f}"
    render_all()


# ---------------------------------------------------------------------------
# Presets, Exports, Print & Tooltip Popovers
# ---------------------------------------------------------------------------


def _apply_preset(cyl, sts, sw_w, rows, sw_h, use_cw, cw_rows):
    """Load a metric cylinder/swatch preset and reset dimensions to baseline defaults."""
    if state["unit"] != "metric":
        _convert_all_dimension_inputs("metric")
    document.querySelector("#cylinder-needles").value = str(cyl)
    document.querySelector("#swatch-stitches").value = str(sts)
    document.querySelector("#swatch-width").value = str(sw_w)
    document.querySelector("#swatch-rows").value = str(rows)
    document.querySelector("#swatch-height").value = str(sw_h)

    cw_chk = document.querySelector("#use-colorwork")
    cw_chk.checked = use_cw
    cw_input = document.querySelector("#colorwork-rows")
    cw_group = document.querySelector("#colorwork-group")
    cw_input.value = str(cw_rows)
    cw_input.disabled = not use_cw
    if use_cw:
        cw_group.classList.remove("is-disabled")
    else:
        cw_group.classList.add("is-disabled")

    document.querySelector("#foot-length").value = "25.5"
    document.querySelector("#foot-length-range").value = "25.5"
    document.querySelector("#leg-height").value = "14.0"
    document.querySelector("#leg-height-range").value = "14.0"
    document.querySelector("#rib-cuff").value = "4.0"
    document.querySelector("#hem-depth").value = "2.0"
    document.querySelector("#negative-ease").value = "10.0"
    document.querySelector("#deep-heel-extra").value = "0"
    state["plateau_mode"] = "pct"
    pct_el = document.querySelector("#toe-plateau-pct")
    if pct_el:
        pct_el.min = "2.0"
        pct_el.max = "98.0"
        pct_el.value = "35.0"
    _sync_plateau_pair("pct", snap_active=True)
    document.querySelector("#target-ball-circ").value = ""
    render_all()


@when("click", "#preset-60")
def on_preset_60(event):
    _apply_preset(60, 15.0, 5.0, 21.0, 5.0, False, 25.0)


@when("click", "#btn-reset")
def on_reset_click(event):
    _apply_preset(60, 15.0, 5.0, 21.0, 5.0, False, 25.0)


@when("click", "#preset-72")
def on_preset_72(event):
    _apply_preset(72, 18.0, 5.0, 23.0, 5.0, True, 25.0)


def _download_text(filename, mime_type, content):
    """Trigger a client-side file download via an inline `data:` URI."""
    link = document.createElement("a")
    encoded = window.encodeURIComponent(content)
    link.setAttribute("href", f"data:{mime_type};charset=utf-8,{encoded}")
    link.setAttribute("download", filename)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)


@when("click", "#btn-export-csv")
def on_export_csv(event):
    params = get_params()
    unit = state["unit"]
    _, chart_rows = build_sizing_rows(params, unit)
    csv_text = build_csv_bench_sheet(chart_rows, unit)
    fname = f"csm_{params['cylinder_needles']}_sock_chart.csv"
    _download_text(fname, "text/csv", csv_text)
    document.querySelector("#export-feedback").innerText = f"Downloaded {fname}"


@when("click", "#btn-export-md")
def on_export_md(event):
    params = get_params()
    unit = state["unit"]
    res = _compute_current(params)
    _, chart_rows = build_sizing_rows(params, unit)
    md_text = build_markdown_bench_sheet(params, res, chart_rows, unit, state["rib_setup"])
    fname = f"csm_{params['cylinder_needles']}_operation_sheet.md"
    _download_text(fname, "text/markdown", md_text)
    document.querySelector("#export-feedback").innerText = f"Downloaded {fname}"


@when("click", "#btn-copy-md")
def on_copy_text(event):
    txt = document.querySelector("#bench-preview").innerText
    window.navigator.clipboard.writeText(txt)
    document.querySelector("#export-feedback").innerText = "Copied CSM operation sheet to clipboard."


@when("click", "#btn-print")
def on_print_click(event):
    window.print()


def _close_all_tooltips():
    """Collapse any open `?` parameter explanation popovers."""
    for anchor in document.querySelectorAll(".tip-anchor.is-open"):
        anchor.classList.remove("is-open")
        btn = anchor.querySelector(".tip-trigger")
        if btn:
            btn.setAttribute("aria-expanded", "false")


@when("click", ".tip-trigger")
def on_tip_trigger_click(event):
    """Toggle the clicked `?` popover while closing any other open popovers."""
    event.stopPropagation()
    target = event.target
    anchor = target.closest(".tip-anchor") if hasattr(target, "closest") else None
    if not anchor:
        return
    was_open = anchor.classList.contains("is-open")
    _close_all_tooltips()
    if not was_open:
        anchor.classList.add("is-open")
        target.setAttribute("aria-expanded", "true")


@when("click", "body")
def on_body_click_close_tips(event):
    target = event.target
    if hasattr(target, "closest") and target.closest(".tip-anchor"):
        return
    _close_all_tooltips()


@when("keydown", "body")
def on_keydown_close_tips(event):
    if getattr(event, "key", "") == "Escape":
        _close_all_tooltips()


# ---------------------------------------------------------------------------
# Initial Boot Render
# ---------------------------------------------------------------------------

loading_banner = document.querySelector("#mpy-loading")
if loading_banner:
    loading_banner.classList.add("is-hidden")
_sync_plateau_pair("pct", snap_active=True)
render_all()

