#!/usr/bin/env python3
"""Launch the calibrated SO-101 model in MuJoCo.

The default mode uses the simulation-ready MJCF converted from
``so101_new_calib.urdf``.  ``--model urdf`` compiles the URDF itself, which is
useful for checking the source model but does not have MuJoCo actuators or a
ground plane.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys

import mujoco


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
URDF_PATH = SCRIPT_DIR / "so101_new_calib.urdf"
MODEL_DIR = PROJECT_ROOT / "mujoco_menagerie" / "robotstudio_so101"
SCENE_PATH = MODEL_DIR / "scene.xml"
ASSET_DIR = MODEL_DIR / "assets"


def load_urdf() -> mujoco.MjModel:
    """Compile the repository URDF with assets supplied from the menagerie."""
    if not URDF_PATH.is_file():
        raise FileNotFoundError(f"URDF not found: {URDF_PATH}")

    # The URDF uses paths such as assets/base_so101_v2.stl.  Keeping the asset
    # map in memory avoids copying or symlinking the shared mesh files.
    assets = {
        f"assets/{path.name}": path.read_bytes()
        for path in ASSET_DIR.iterdir()
        if path.is_file()
    }
    return mujoco.MjModel.from_xml_string(
        URDF_PATH.read_text(encoding="utf-8"), assets=assets
    )


def load_model(source: str) -> mujoco.MjModel:
    if source == "urdf":
        return load_urdf()
    if not SCENE_PATH.is_file():
        raise FileNotFoundError(f"MuJoCo scene not found: {SCENE_PATH}")
    return mujoco.MjModel.from_xml_path(str(SCENE_PATH))


def model_summary(model: mujoco.MjModel, source: str) -> str:
    joint_names = [
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, index)
        for index in range(model.njnt)
    ]
    return (
        f"Loaded {source}: bodies={model.nbody}, joints={model.njnt}, "
        f"actuators={model.nu}, geoms={model.ngeom}\n"
        f"Joints: {', '.join(name or '<unnamed>' for name in joint_names)}"
    )


def run_headless(model: mujoco.MjModel, duration: float) -> None:
    data = mujoco.MjData(model)
    step_count = max(1, math.ceil(duration / model.opt.timestep))
    for _ in range(step_count):
        mujoco.mj_step(model, data)

    if not all(math.isfinite(value) for value in data.qpos):
        raise RuntimeError("Simulation became unstable: qpos contains NaN or Inf")
    print(
        f"Headless simulation passed: {step_count} steps, "
        f"simulated_time={data.time:.3f}s"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch the calibrated SO-101 in MuJoCo."
    )
    parser.add_argument(
        "--model",
        choices=("scene", "urdf"),
        default="scene",
        help=(
            "scene: controllable MJCF with floor (default); "
            "urdf: compile so101_new_calib.urdf directly"
        ),
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="run a finite smoke test without opening a window",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=2.0,
        help="headless simulation duration in seconds (default: 2)",
    )
    args = parser.parse_args()
    if args.duration <= 0:
        parser.error("--duration must be greater than zero")
    return args


def main() -> int:
    args = parse_args()
    try:
        model = load_model(args.model)
        print(model_summary(model, args.model))
        if args.model == "urdf" and not args.headless:
            print(
                "Note: raw URDF has no MuJoCo actuators; use the default scene "
                "mode for actuator sliders."
            )

        if args.headless:
            run_headless(model, args.duration)
        else:
            data = mujoco.MjData(model)
            from mujoco import viewer

            viewer.launch(model=model, data=data)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
