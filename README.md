# SO-ARM101

本项目用于 SO-ARM101 六轴机械臂的实机初始化、校准、遥操作、数据采集，
以及基于 MuJoCo 的 URDF 仿真。

## 环境要求

- Ubuntu 24.04（当前测试环境）
- Python 3.10 及以上（当前使用 Python 3.12）
- Git
- FFmpeg（LeRobot 录制和读取视频时使用）
- 实机功能需要两只 SO-ARM101、Feetech STS3215 舵机及 USB 摄像头

Ubuntu 上可先安装基础系统工具：

```bash
sudo apt update
sudo apt install -y git python3-venv ffmpeg
```

## Python 库

| 库 | 当前测试版本 | 用途 |
|---|---:|---|
| `lerobot[feetech]` | 0.3.4 | 校准、遥操作、相机、数据采集与训练 |
| `mujoco` | 3.12.0 | 加载 URDF/MJCF 并运行机械臂仿真 |
| `feetech-servo-sdk` | 1.0.0 | 与 STS3215 舵机通信，由 `lerobot[feetech]` 安装 |
| `pyserial` | 3.5 | 串口访问，由 LeRobot 安装 |
| `opencv-python-headless` | 5.0.0.93 | USB 相机采集，由 LeRobot 安装 |
| `torch` | 2.7.1 | 策略训练与推理，由 LeRobot 安装 |

通常只需直接安装 LeRobot 和 MuJoCo，不需要逐项安装表中的传递依赖。
本仓库已包含 `lerobot/` 源码。首次部署时，请先按
[外部仓库](#外部仓库)一节克隆 `mujoco_menagerie/`，再在项目根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e "./lerobot[feetech]"
python -m pip install "mujoco==3.12.0"
```

如果需要 NVIDIA GPU 训练，请先按照
[PyTorch 官方安装说明](https://pytorch.org/get-started/locally/)安装与本机 CUDA
匹配的 PyTorch，再安装 LeRobot。

## 外部仓库

本项目使用以下外部开源项目：

| 本地目录 | 上游项目 | 仓库链接 |
|---|---|---|
| `lerobot/` | Hugging Face LeRobot（源码已纳入本仓库） | [huggingface/lerobot](https://github.com/huggingface/lerobot) |
| `mujoco_menagerie/` | MuJoCo Menagerie 模型库（需单独克隆） | [google-deepmind/mujoco_menagerie](https://github.com/google-deepmind/mujoco_menagerie) |

新环境中，在本项目根目录执行：

```bash
git clone https://github.com/google-deepmind/mujoco_menagerie.git mujoco_menagerie
```

`lerobot/` 中的模型权重、测试数据、媒体文件和训练输出不会上传；
其上游 Git 历史仅作为本地 `.git-upstream` 备份，也已忽略。

其他相关上游链接：

- [Google DeepMind MuJoCo](https://github.com/google-deepmind/mujoco)
- [TheRobotStudio SO-ARM100 / SO-101](https://github.com/TheRobotStudio/SO-ARM100)
- [Feetech Servo Python SDK](https://github.com/Adam-Software/FEETECH-Servo-Python-SDK)
- [LeRobot 官方文档](https://huggingface.co/docs/lerobot/index)

## 快速开始

### MuJoCo 仿真

启动带地面、碰撞体和六个位置执行器的交互仿真：

```bash
source .venv/bin/activate
python scripts_forsim/run_so101_sim.py
```

无图形界面测试：

```bash
python scripts_forsim/run_so101_sim.py --headless --duration 2
python scripts_forsim/run_so101_sim.py --model urdf --headless --duration 2
```

### 实机

检查两只机械臂对应的串口：

```bash
source .venv/bin/activate
python init_setup/check_ports.py
```

校准、遥操作及数据采集命令见
[实机初始化说明](init_setup/initialization.md)。完整的 LeRobot 代码结构和使用说明见
[LeRobot 指南](lerobot_guide.md)。

## 项目结构

```text
soarm101/
├── init_setup/             # 端口检查与实机初始化说明
├── scripts_forreal/        # 实机实验记录和脚本
├── scripts_forsim/         # MuJoCo 启动器、URDF 与仿真说明
├── lerobot/                # 已纳入本仓库的 LeRobot 源码
├── mujoco_menagerie/       # 外部 MuJoCo 模型库（不纳入本仓库）
└── lerobot_guide.md        # LeRobot 项目分析与使用指南
```
