# SO-101 MuJoCo simulation

`so101_new_calib.urdf` is available through a single launcher. The default
mode opens the simulation-ready MuJoCo conversion in
`mujoco_menagerie/robotstudio_so101`: it has the calibrated kinematic chain,
collision geometry, a floor, and position actuators for all six joints.

From the project root, start the interactive simulation with:

```bash
.venv/bin/python scripts_forsim/run_so101_sim.py
```

The actuator controls are in MuJoCo's right-hand **Control** panel. The six
sliders are `shoulder_pan`, `shoulder_lift`, `elbow_flex`, `wrist_flex`,
`wrist_roll`, and `gripper`.

To compile and view the original URDF itself, use:

```bash
.venv/bin/python scripts_forsim/run_so101_sim.py --model urdf
```

Raw URDF has no MuJoCo actuators or world objects, so this mode is intended for
checking its geometry and kinematics. Meshes are resolved in memory from the
matching Menagerie asset directory; no extra `assets` copy or symlink is
needed.

For a display-free installation/model check:

```bash
.venv/bin/python scripts_forsim/run_so101_sim.py --headless --duration 2
.venv/bin/python scripts_forsim/run_so101_sim.py --model urdf --headless --duration 2
```
