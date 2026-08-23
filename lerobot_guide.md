# LeRobot 0.3.4 源码完全学习指南

> 面向目标：完全读懂、能够自己复现 LeRobot 的源码结构
> 分析对象：`~/soarm101/lerobot`（huggingface/lerobot，v0.3.4，Apache-2.0）
> 撰写日期：2026-08-24
> 阅读配合：本指南 + 直接打开源码对照阅读效果最好。所有文件路径均相对于仓库根目录。

---

## 目录

1. [项目总览](#一项目总览)
2. [整体架构](#二整体架构)
3. [目录树与模块地图](#三目录树与模块地图)
4. [硬件抽象层：motors / robots / teleoperators](#四硬件抽象层)
5. [感知层：cameras / envs / transport](#五感知层)
6. [数据层：datasets / processor](#六数据层)
7. [模型层：policies / model / optim / configs](#七模型层)
8. [应用层：CLI / scripts / utils](#八应用层)
9. [SO-101 完整代码路径](#九so-101-完整代码路径)
10. [核心数据流](#十核心数据流)
11. [设计模式速查](#十一设计模式速查)
12. [从零复现路线图](#十二从零复现路线图)

---

## 一、项目总览

**LeRobot** 是 HuggingFace 开源的"真实机器人模仿学习"全栈框架（PyTorch）。它把机器人学习的完整闭环做成了一条流水线：

```
采集演示数据 → 组织成数据集 → 训练策略 → 部署推理 → 再采集/评估
```

核心价值主张：
1. **硬件无关**：同一套策略代码可以跑在 SO-100/SO-101、Koch、Aloha、ViperX、移动机器人等任何机器上，也可以跑在仿真里（PushT、Aloha sim、HIL-SERL）
2. **数据格式统一**：所有采集的数据都是同一种 LeRobotDataset 格式（Parquet + MP4 视频），社区共享数据集（HuggingFace Hub 上的 `lerobot/*` 系列）
3. **策略即插即用**：ACT、Diffusion Policy、VQ-BeT、TD-MPC、π0、SmolVLA、SAC 等，用同一套训练/评估脚本
4. **从零门槛低**：400 美元的 SO-ARM100/101 就能跑通整个闭环

**依赖核心**（`pyproject.toml:59-90`）：`torch`、`datasets`（HF）、`diffusers`（扩散策略依赖）、`huggingface-hub`（数据集上传/下载）、`draccus`（配置解析）、`gymnasium`（RL 环境）、`rerun-sdk`（可视化）、`opencv-python-headless` + `av`（相机/视频）、`pyserial`（舵机通信）。

**CLI 入口**（`pyproject.toml:158-167`，共 9 个命令）：

| 命令 | 模块 | 作用 |
|------|------|------|
| `lerobot-calibrate` | `lerobot/calibrate.py` | 校准机器人/主端 |
| `lerobot-setup-motors` | `lerobot/setup_motors.py` | 给舵机写 ID/波特率（一次性） |
| `lerobot-find-port` | `lerobot/find_port.py` | 拔线法识别串口 |
| `lerobot-find-cameras` | `lerobot/find_cameras.py` | 识别相机 |
| `lerobot-record` | `lerobot/record.py` | 采集演示数据 |
| `lerobot-replay` | `lerobot/replay.py` | 回放数据集 |
| `lerobot-teleoperate` | `lerobot/teleoperate.py` | 纯遥操作（不录数据） |
| `lerobot-train` | `lerobot/scripts/train.py` | 训练策略 |
| `lerobot-eval` | `lerobot/scripts/eval.py` | 评估策略 |

## 二、整体架构

LeRobot 的分层结构（自下而上）：

```
┌─────────────────────────────────────────────────────────────┐
│  应用层 scripts/ + 顶层 CLI                                   │
│  train.py / eval.py / record.py / replay.py / teleoperate.py │
│  calibrate.py / setup_motors.py / rl/* / server/*            │
├─────────────────────────────────────────────────────────────┤
│  模型层 policies/  (ACT/Diffusion/VQ-BeT/TD-MPC/π0/...)      │
│  configs/ (train/eval 默认配置)  optim/ (优化器工厂)          │
├─────────────────────────────────────────────────────────────┤
│  数据层 datasets/ (LeRobotDataset 存储与加载)                 │
│  processor/ (数据集特性 → 模型输入张量)                       │
├─────────────────────────────────────────────────────────────┤
│  感知层 cameras/ (OpenCV/RealSense)  envs/ (仿真环境)        │
│  transport/ (gRPC 跨进程服务)                                │
├─────────────────────────────────────────────────────────────┤
│  硬件抽象层 motors/ (舵机总线)  robots/ (机器人)              │
│  teleoperators/ (主端操作器)                                 │
├─────────────────────────────────────────────────────────────┤
│  横切 utils/ (日志/可视化/IO/编码/队列/控制)                  │
│  constants.py / errors.py / __version__.py                   │
└─────────────────────────────────────────────────────────────┘
```

**三条核心数据流**（详见[第十节](#十核心数据流)）：
1. **采集流**：Teleoperator 读数 → record.py 组装成帧 → LeRobotDataset 落盘
2. **训练流**：LeRobotDataset 加载 → processor 处理 → Policy 训练 → 保存 checkpoint
3. **推理流**：Policy 加载 → 观察输入 → 输出动作 → Robot.send_action 执行

**统一抽象**：整个框架围绕 4 个核心接口转——`Robot`、`Teleoperator`、`Camera`、`Policy`，全部采用"基类 + 注册表 + dataclass 配置"模式（详见[第十一节](#十一设计模式速查)）。

## 三、目录树与模块地图

```
lerobot/
├── pyproject.toml            # 打包/依赖/CLI入口/ruff配置
├── Makefile                  # 开发常用命令（lint/format/test）
├── README.md                 # 项目总介绍
├── src/lerobot/              # 全部源码（209 个 .py）
│   ├── __init__.py           # 包版本/顶层导出
│   ├── __version__.py        # 版本号
│   ├── constants.py          # 全局常量（HOME目录、数据目录等）
│   ├── errors.py             # 自定义异常体系
│   ├── calibrate.py          # [CLI] lerobot-calibrate
│   ├── setup_motors.py       # [CLI] lerobot-setup-motors
│   ├── find_port.py          # [CLI] lerobot-find-port
│   ├── find_cameras.py       # [CLI] lerobot-find-cameras
│   ├── record.py             # [CLI] lerobot-record 采集
│   ├── replay.py             # [CLI] lerobot-replay 回放
│   ├── teleoperate.py        # [CLI] lerobot-teleoperate 遥操作
│   │
│   ├── motors/               # 舵机总线抽象（Feetech/Dynamixel）
│   ├── robots/               # 机器人抽象（SO-100/101、Koch、ViperX...）
│   ├── teleoperators/        # 主端操作器（SO-101 leader、手柄、键盘...）
│   ├── cameras/              # 相机抽象（OpenCV/RealSense）
│   ├── envs/                 # 仿真环境封装（PushT/Aloha/xArm）
│   ├── transport/            # gRPC 通信（HIL-SERL 用）
│   ├── datasets/             # LeRobotDataset 存储/加载/转换
│   ├── processor/            # 观察→模型输入的处理器
│   ├── policies/             # 各策略实现（ACT/扩散/VQ-BeT/π0/...）
│   ├── model/                # 模型级组件（运动学）
│   ├── optim/                # 优化器/调度器工厂
│   ├── configs/              # train/eval 默认配置
│   ├── scripts/              # train/eval/可视化/RL/服务端
│   └── utils/                # 横切工具
├── tests/                    # 单元测试（mocks/ 提供硬件模拟）
├── examples/                 # 上手示例（1加载 2评估 3训练）
├── docs/source/              # 官方文档（so101.mdx 等）
├── benchmarks/               # 视频编解码基准
├── media/                    # 演示图/视频
└── docker/                   # Docker 镜像定义
```

---

## 四、硬件抽象层：motors / robots / teleoperators

这一层解决"如何把物理硬件统一成 LeRobot 的训练/遥操作接口"，分三个子层：**motors**（串口舵机总线通信）→ **robots**（从臂，执行者）→ **teleoperators**（主端，操纵者）。

### 4.1 motors/ — 电机总线抽象层

职责：与串口上菊花链舵机通信的底层抽象。不关心机械臂长什么样，只关心"一组电机 + 一个串口"。

#### motors/motors_bus.py（1220 行）— 整个电机层的"心脏"

- `Motor` dataclass（:95）：`(id, model, norm_mode)` —— 声明总线上的电机，如 `Motor(1, "sts3215", MotorNormMode.RANGE_0_100)`
- `MotorCalibration` dataclass（:86）：`(id, drive_mode, homing_offset, range_min, range_max)` —— 单个电机校准数据，motors 与 robots 之间传递的校准单元
- `MotorNormMode` 枚举（:80）：`RANGE_0_100`（[0,100]）/`RANGE_M100_100`（[-100,100]）/`DEGREES`（角度制）
- `MotorsBus` 抽象基类（:212）关键方法：
  - 生命周期：`connect(handshake=True)` / `disconnect(disable_torque=True)` / `torque_disabled()` 上下文管理器（保证退出恢复扭矩）
  - 电机配置：`setup_motor()`（:502，改单个电机 ID/波特率）、`scan_port()`（:477，全波特率扫描）、抽象 `configure_motors()`
  - 校准：`is_calibrated` / `read_calibration` / `write_calibration` / `reset_calibration`（:666）/ `set_half_turn_homings`（:692，把当前位姿变成行程中点）/ `record_ranges_of_motion`（:723，交互式记录 min/max，min==max 抛 ValueError——**你校准时报的错就是这里**）
  - 归一化：`_normalize`（:776）/`_unnormalize`（:805），三种 norm_mode 各自映射，反向安装电机靠 `drive_mode` 处理
  - 读写：`read`（:916，有应答慢但可靠）/`write`（:990）/`sync_read`（:1053）/`sync_write`（:1148，无应答快、可丢包，遥操作主循环用）
- 类变量注入模式：子类用类变量赋值控制表/波特率表/编码表/分辨率表，基类模板方法完成公共流程

#### motors/dynamixel/dynamixel.py（265 行）+ tables.py（200 行）

`DynamixelMotorsBus`（协议 2.0）：`apply_drive_mode=False`；有符号编码用**补码**；half-turn 公式 `Present=Actual+Offset → offset=res/2-pos`；X 系列控制表（Homing_Offset(20,4)、Goal_Position(116,4)…）。供 Koch/ViperX/WidowX 使用。

#### motors/feetech/feetech.py（456 行）+ tables.py（253 行）

`FeetechMotorsBus`（协议 0/1）：**你的 SO-101 用的就是这个**。
- `apply_drive_mode=True`（反向安装的 drive_mode 参与归一化）
- 有符号编码用**符号幅值**（sign-magnitude）；half-turn 公式与 Dynamixel **相反**：`Present=Actual-Offset → offset=pos-res/2`
- `disable_torque` 除了 `Torque_Enable` 还写 `Lock=0`（Feetech 特有，防掉电后写 EEPROM）
- `_broadcast_ping`（:335-404）：**手写协议解析**（scservo_sdk 没有广播 ping）
- `patch_setPacketTimeout`（:86）：HACK monkeypatch 修复官方 SDK 的包超时 bug
- 型号表：sts3215=777、分辨率 4096；scs 系列协议 1 且分辨率 1024、**无 sync_read**

#### motors/calibration_gui.py（401 行）

pygame 滑块校准 GUI（`RangeSlider`/`RangeFinderGUI`），只有 Hope-Jr 用它；SO-100/101 用终端交互式 `record_ranges_of_motion`。

#### 两个总线实现的差异对照表（学习重点）

| 维度 | Dynamixel | Feetech |
|------|-----------|---------|
| apply_drive_mode | False | **True** |
| 有符号编码 | 补码 | 符号幅值 |
| half-turn 公式 | offset=res/2-pos | **offset=pos-res/2** |
| 协议 | 2.0 | 0/1，p1 无 sync_read/广播 ping |
| 分辨率 | 全 4096 | sts 4096 / scs 1024 |

### 4.2 robots/ — 机器人（从臂）抽象层

每个机器人子包 = `robot_xxx.py`（实现）+ `config_xxx.py`（配置）+ `__init__.py`（导出）。

#### robots/robot.py（185 行）— Robot 抽象基类

抽象接口：`observation_features`（:62）/`action_features`（:76）/`connect(calibrate=True)`（:98）/`calibrate()`（:115）/`configure()`（:147）/`get_observation()`（:155）/`send_action()`（:167）/`disconnect()`（:182）。
校准存取：`_load_calibration`/`_save_calibration`（:125/:136），**校准文件按 `{calibration_dir}/{id}.json` 存放**（draccus JSON 序列化 `dict[str, MotorCalibration]`）。

#### robots/config.py（40 行）— RobotConfig 基类

`@dataclass(kw_only=True) class RobotConfig(draccus.ChoiceRegistry, abc.ABC)`：字段 `id`、`calibration_dir`；子类用 `@RobotConfig.register_subclass("so101_follower")` 注册。

#### robots/utils.py（111 行）— 工厂与安全限幅

- `make_robot_from_config(config)`（:23）：按 `config.type` 字符串分发的工厂（延迟 import 各子包）
- `ensure_safe_goal_position`（:76）：把每个关节目标相对当前位置的增量钳到 ±`max_relative_target`

#### 机器人清单

| 机器人 | 文件 | 总线 | 状态/特点 |
|--------|------|------|-----------|
| `SO101Follower` | so101_follower/so101_follower.py:37 | Feetech sts3215×6 | **你的从臂**（详见第九节） |
| `SO100Follower` | so100_follower/so100_follower.py:37 | Feetech sts3215×6 | 与 SO-101 几乎同构，唯一差异：wrist_roll 整圈关节固定 0/4095 |
| `SO100FollowerEndEffector` | so100_follower_end_effector.py:35 | 继承 SO100Follower | **末端空间控制**：action 变成 `{delta_x,delta_y,delta_z,gripper}`，用 `RobotKinematics` 正逆运动学翻译成关节空间 |
| `KochFollower` | koch_follower/koch_follower.py:37 | Dynamixel xl430/xl330 | 低成本臂；肘部单独调 PID；gripper 用电流限位模式 |
| `LeKiwi` | lekiwi/lekiwi.py:40 | Feetech sts3215×9 | 轮式移动机器人：6 关节 + 3 全向轮；轮子速度模式 + 三轮运动学（`_body_to_wheel_raw`） |
| `LeKiwiClient`/`LeKiwiHost` | lekiwi/ | ZMQ | 远端笔记本/板载端拆分，JPEG base64 传输 |
| `HopeJrArm`/`HopeJrHand` | hope_jr/ | Feetech（sts3250/sm8512bl/scs0009） | 机械手用 GUI 校准；scs0009 协议 1 无 sync_read 所以逐电机 read |
| `ViperX` | viperx.py:36 | Dynamixel xm430/xm540 | ⚠️ 未完成（`__init__` raise）；`Secondary_ID` 双电机联动值得参考 |
| `Stretch3Robot` | stretch3/robot_stretch3.py:47 | 官方 SDK（不走 MotorsBus） | ⚠️ 未完成（raise） |
| `BiSO101Follower`/`BiSO100Follower` | bi_so101_follower/、bi_so100_follower/ | 组合两个单臂 | 双臂：键加 `left_`/`right_` 前缀，按前缀拆分派发 |

**组合模式**：双臂机器人不继承单臂，而是持有两个单臂实例做键前缀/拆分派发。

### 4.3 teleoperators/ — 主端操作器抽象层

#### 与 Robot 的镜像关系（核心契约）

| | Robot（从臂） | Teleoperator（主端） |
|---|---|---|
| 特征声明 | `observation_features`/`action_features` | `action_features`/`feedback_features` |
| 数据流 | `get_observation()`/`send_action()` | `get_action()`/`send_feedback()` |

**拼接点**在 `teleoperate.py` 的 `teleop_loop()`（:104-131）：
```python
action = teleop.get_action()     # 主端读数
robot.send_action(action)        # 直接按"键名"喂给从臂
```
→ **主端输出 dict 的键名必须与从臂 action_features 键名逐一对齐**（SO-101 主从臂电机命名、归一化范围完全同构，所以 `gripper.pos` 天然 1:1 传递）。

#### teleoperator.py（181 行）— 基类

`Teleoperator`：`config_class`/`name` 类属性；校准目录 `HF_LEROBOT_CALIBRATION/teleoperators/{name}/{id}.json`；抽象接口与 Robot 对称。

#### utils.py（:19）— 工厂

`make_teleoperator_from_config`：14 个分支（keyboard/keyboard_ee/koch_leader/so100_leader/**so101_leader**/gamepad/homunculus_glove/homunculus_arm/bi_so100_leader/bi_so101_leader/widowx/stretch3/mock_teleop）。

#### SO101Leader（so101_leader/so101_leader.py:156）— 你的主臂

- 与 follower 同构：6 个 sts3215，身体关节 `RANGE_M100_100`（或 DEGREES），gripper `RANGE_0_100`
- `get_action()`（:139-145）：`bus.sync_read("Present_Position")` 群读 → 归一化 → 键改名 `{motor}.pos`
- **扳机→夹爪链路**：主臂扳机是反驱电机 → 手指捏扳机=电机转动 → 读数 `gripper.pos` 变化 → teleop_loop 原样传给 follower → follower 按名匹配执行。全程无比例/方向换算
- `configure()`（:127-131）：**全程无扭矩**（可被手自由拖动），与从臂相反
- ⚠️ 已知 bug：`disconnect()` 里 `DeviceNotConnectedError(...)` 漏写 `raise`（so100_leader/koch_leader/widowx/homunculus 也有同样复制出来的错误）

#### 其他主端操作器

| 主端 | 特点 |
|------|------|
| `SO100Leader` | SO-101 前身；wrist_roll 整圈固定 0/4095 |
| `KochLeader` | 夹爪用电流限位位置模式当**物理扳机**（松手自动弹回） |
| `GamepadTeleop` | 手柄输出末端增量 `delta_x/y/z` + 三态夹爪命令（RB 夹/LT 开） |
| `KeyboardTeleop`/`KeyboardEndEffectorTeleop` | 键盘控制（方向键/Shift/Ctrl），兼作 RL 干预标记输入 |
| `HomunculusArm`/`HomunculusGlove` | HF 自研 7 关节主臂/16 关节数据手套，串口+后台线程+EMA 平滑 |
| `BiSO101Leader` | 聚合两个 SO101Leader，键加 `left_`/`right_` 前缀 |
| `WidowX`/`Stretch3GamePad` | ⚠️ 脚手架占位（`__init__` raise NotImplementedError） |

**"夹爪即扳机"三种实现谱系**：SO-101 靠反驱位置直读；Koch 靠电流限位+目标位置回弹；Gamepad/Keyboard 靠离散三态命令。

## 五、感知层：cameras / envs / transport

### 5.1 cameras/ — 相机抽象层

**职责**：为不同相机后端提供统一接口（连接/断连、同步/异步读帧、设备发现、色彩与旋转后处理）。核心设计：抽象基类 + 配置注册表 + 延迟导入工厂。

**文件逐个说明**（路径相对 `src/lerobot/`）：

| 文件 | 功能 | 关键点 |
|------|------|--------|
| `cameras/camera.py` | 抽象基类 `Camera`（`camera.py:25`） | 6 个抽象成员：`is_connected`、`find_cameras()`、`connect()`、`read()`、`async_read()`、`disconnect()`；从 `CameraConfig` 读 fps/width/height |
| `cameras/configs.py` | 配置基类 `CameraConfig`（`configs.py:36`） | 继承 `draccus.ChoiceRegistry`（注册机制）；`ColorMode`(RGB/BGR)、`Cv2Rotation` 枚举；`type` 属性反查注册名 |
| `cameras/utils.py` | 工厂 `make_cameras_from_configs`（`utils.py:27`） | 按 `type` 分发并**延迟导入**实现类（避免未装 pyrealsense2 时整个包挂掉）；`get_cv2_rotation`、`get_cv2_backend` 辅助 |
| `cameras/opencv/configuration_opencv.py` | `OpenCVCameraConfig`（注册名 `"opencv"`） | `index_or_path: int\|Path`（设备号/路径/视频文件）、`color_mode`、`rotation`、`warmup_s` |
| `cameras/opencv/camera_opencv.py` | `OpenCVCamera` 实现（485 行） | `cv2.VideoCapture` 封装；`find_cameras()` 在 Linux 扫 `/dev/video*`、其他平台暴力扫 0–60 号（`camera_opencv.py:246`）；**异步读帧**=后台 daemon 线程 + `Event` 新帧信号 + `Lock` 保护最新帧（`_read_loop` `camera_opencv.py:375`）；BGR→RGB、旋转后处理 |
| `cameras/realsense/configuration_realsense.py` | `RealSenseCameraConfig`（注册名 `"intelrealsense"`） | 按序列号/名称寻址、可选深度流；要求 fps/宽高**全设或全不设** |
| `cameras/realsense/camera_realsense.py` | `RealSenseCamera` 实现（555 行） | 原生 RGB；`read_depth()` 返回毫米级 uint16 深度图；异步只支持 color；断连用 `rs_pipeline.stop()` |

**设计要点**：
1. **配置即注册**：`@CameraConfig.register_subclass("opencv")` 后，CLI 写 `type=opencv` 即路由到对应实现
2. **线程模型**：两种相机的异步读帧结构完全相同（daemon 线程 + Event + Lock），值得对比学习
3. 旋转 90/270° 时宽高互换；Windows 下强制关闭硬件变换（`camera_opencv.py:29`）

### 5.2 envs/ — Gymnasium 环境配置与工厂

**职责**：envs 本身**不含模拟器**——它是对外部 Gym 包（`gym_aloha`/`gym_pusht`/`gym_xarm`/HIL）的"配置描述 + 实例化工厂 + 观测预处理"薄层，把环境的 gym 观测映射成 LeRobot 统一的 `observation.image/state` 格式。

| 文件 | 功能 | 关键点 |
|------|------|--------|
| `envs/configs.py` | 环境配置（273 行） | `EnvConfig` 基类（注册名 `aloha`/`pusht`/`xarm`/`hil`/`gym_manipulator`）；每个配置声明 `features`（策略消费的特征规格）和 `features_map`（gym 键→LeRobot 键映射） |
| `envs/factory.py` | `make_env(cfg, n_envs)`（`factory.py:36`） | 动态 `importlib` 导入 `gym_{cfg.type}` 包（未装提示 `pip install lerobot[pusht]`）；返回 `AsyncVectorEnv`/`SyncVectorEnv` 向量环境 |
| `envs/utils.py` | 观测预处理（136 行） | `preprocess_observation`（`utils.py:30`）：图从 channel-last 转 `b c h w`、除以 255、自动补 batch 维；`env_to_policy_features` 按 `features_map` 重命名 |

### 5.3 transport/ — 跨进程 gRPC 数据通道

**职责**：Actor（采集/推理进程）↔ Learner（训练进程）、机器人客户端 ↔ 远程策略服务器之间的数据传输。核心问题：gRPC 默认 4MB 消息上限，而模型参数/观测远超此值 → **必须分块传输**。

| 文件 | 功能 | 关键点 |
|------|------|--------|
| `transport/services.proto` | proto3 契约源文件 | 两个服务：`LearnerService`（`StreamParameters` 下发参数、`SendTransitions` 上传回放数据、`SendInteractions`）与 `AsyncInference`（`SendObservations` 上传观测、`GetActions` 拉取动作）；`TransferState` 枚举 `BEGIN/MIDDLE/END` 标记分块边界 |
| `transport/services_pb2.py` / `services_pb2_grpc.py` | protoc 生成的消息类与 gRPC 桩 | 自动生成，勿手改；grpcio ≥1.73.1 |
| `transport/utils.py` | 序列化与分块工具（186 行） | `CHUNK_SIZE=2MB`；`send_bytes_in_chunks`（**生成器**逐块 yield 消息）、`receive_bytes_in_chunks`（按 BEGIN/MIDDLE/END 重组）；模型参数用 `torch.save`、任意对象用 pickle；`grpc_channel_options` 配置 4MB 上限 + 自动重试（指数退避） |

**进程拓扑**：
```
actor.py (gRPC client) ──上传 transition──▶ learner_service.py (内嵌 server)
actor.py ◀──下发模型参数── learner.py
robot_client.py ──上传观测/拉动作──▶ policy_server.py
```

**学习提示**：对照 `scripts/rl/learner_service.py` + `actor.py` 读 transport，能看到完整的收发循环；本目录的三个组件都采用"基类/注册表 + 工厂 + 延迟导入"模式——这是 LeRobot 0.3.4 的通用设计语言。

## 六、数据层：datasets / processor

### 6.1 数据集存储格式（v2.1）

**一个 episode = 一个 parquet + N 个 mp4**（N=相机数），chunk 分桶（每桶 1000 集）。标准目录树（`lerobot_dataset.py:376-408`）：

```
root/
├── data/chunk-000/episode_000000.parquet      # 标量/向量特征（状态、动作、时间戳）
├── meta/
│   ├── info.json                              # 版本、fps、features schema、计数
│   ├── episodes.jsonl                         # 每集 {episode_index, tasks, length}
│   ├── episodes_stats.jsonl                   # v2.1: 逐 episode 统计
│   ├── stats.json                             # v2.0 旧全局统计
│   └── tasks.jsonl                            # {task_index, task} 任务文本表
└── videos/chunk-000/observation.images.laptop/episode_000000.mp4
```

**关键设计**：
- 按 episode 分文件 → 可只下载/加载部分集；`info.json` 小文件先行查看
- **video 键不进 parquet**（`utils.py:365` 直接跳过），读取时按时间戳实时解码（`_query_videos`）
- `DEFAULT_FEATURES`（`utils.py:68`）：每集自动加 `timestamp`、`frame_index`、`episode_index`、`index`、`task_index`
- **delta timestamps**：单帧样本扩展为时间窗口（如 `{"observation.state": [-0.04, 0], "action": [-0.02, 0, 0.02]}`），越界帧用 `{key}_is_pad` 掩码标记
- **版本兼容硬约束**：v1.x→必须转换（报错）、v2.0→v2.1（stats 从全局改逐集）

### 6.2 核心类：LeRobotDataset（`lerobot_dataset.py:330`，1236 行）

分两层：
- **`LeRobotDatasetMetadata`（:79）**：负责 meta/ 读写、版本检查、属性访问（`fps`/`features`/`camera_keys`/`total_episodes`…）
- **`LeRobotDataset`**：三种用法——本地离线加载、从 Hub 按 episode 粒度下载加载、`LeRobotDataset.create()` 录制新数据集

**`__getitem__`（:705-732）流程**：parquet 取当前帧 → delta 采样前后帧（`_get_query_indices` :646 换算 `round(d*fps)` 帧索引 + `_is_pad` 掩码）→ 按时间戳从 mp4 解码视频帧 → `image_transforms` 增强 → `task_index` 映射回任务文本。

**录制路径**：`add_frame`（:769）写内存 → `save_episode`（:813）写 parquet + 算 stats + 异步 PNG→mp4 编码（`AsyncImageWriter` 先落 PNG，ffmpeg 编码后清理）。

**`MultiLeRobotDataset`（:1054）**：多数据集拼接（保留公共 feature，附 `dataset_index`），当前在 `factory.py` 中被禁用。

### 6.3 datasets/ 逐文件清单

| 文件 | 功能 | 关键点 |
|------|------|--------|
| `lerobot_dataset.py` | **核心**：Metadata/Dataset/MultiDataset 三件套 | 见上 |
| `utils.py`（849 行） | 格式约定与工具 | 路径模板（:54-56）、`hw_to_dataset_features`（硬件观测→features schema，:395）、`build_dataset_frame`（:427）、`get_episode_data_index`（:497，episode 起止索引，delta 采样/采样器公共基础）、`check_timestamps_sync`（:511，帧率同步校验）、`get_hf_features_from_features`（:362）、`dataset_to_policy_features`（:442） |
| `backward_compatibility.py` | 版本报错信息与异常 | `BackwardCompatibilityError`/`ForwardCompatibilityError`/`CompatibilityError` |
| `compute_stats.py` | 归一化统计量 | `compute_episode_stats`（图像按通道约减、除 255）、`aggregate_stats`（按 count 加权并行方差）、图像统计采样降采样 |
| `image_writer.py` | 录制期异步图像落盘 | `AsyncImageWriter`：线程池/多进程+线程池 |
| `online_buffer.py` | 在线 RL 的 FIFO 缓冲 | `OnlineBuffer`：**numpy memmap 环形缓冲**（比 HF Datasets 快、支持切片）、delta 采样逻辑与 Dataset 相同 |
| `sampler.py` | 训练采样器 | `EpisodeAwareSampler`：按 episode 边界生成索引、丢弃每集首尾帧、shuffle |
| `transforms.py` | 图像增强 | `ImageTransforms`（ColorJitter + 自定义 `SharpnessJitter`）、`RandomSubsetApply` |
| `video_utils.py` | 视频编解码 | `decode_video_frames`（torchcodec 优先，回退 torchvision/pyav）、`encode_video_frames`（PyAV→mp4）、`VideoEncodingManager`（录制中断兜底） |
| `factory.py` | 训练数据集组装 | `make_dataset`（解析 delta_timestamps、拼 ImageTransforms）、`resolve_delta_timestamps`（策略的 delta_indices 帧→秒） |
| `push_dataset_to_hub/utils.py` | 推送 Hub 辅助 | 拼集、并发存图、repo_id 校验 |
| `v2/` | v1.x→v2.0 转换 | `convert_dataset_v1_to_v2.py`（parquet 按 episode 拆分、LFS 迁移）+ 批量版 |
| `v21/` | v2.0→v2.1 转换 | 全局 stats.json → 逐集 episodes_stats.jsonl |

### 6.4 processor/ — 新一代数据后处理管线（2025 新增，尚未被训练脚本引用）

**为什么需要**：`__getitem__` 返回原始数据，策略消费的是模型输入，两者间有可复用的转换（观测格式化、归一化、设备搬移、重命名）。processor 把这些抽象成**可组合、可序列化、可调试的步骤流水线**。

核心数据结构 `EnvTransition`（`pipeline.py:49`）：`{observation, action, reward, done, truncated, info, complementary_data}` 七个槽位的统一中间表示。

| 文件 | 功能 | 关键点 |
|------|------|--------|
| `pipeline.py`（1264 行） | **核心框架** | `ProcessorStep`（Protocol：`__call__` + `feature_contract`）；`ProcessorStepRegistry`（按名注册，序列化加载依赖）；`RobotProcessor`（:251，`ModelHubMixin`，`save_pretrained`/`from_pretrained`，JSON+safetensors）；`step_through`（:375）逐步 yield 中间结果调试；7 个单槽位基类（Observation/Action/Reward/Done/Truncated/Info/ComplementaryData Processor，模板方法模式）；`_default_batch_to_transition`（:180）batch↔EnvTransition 互转 |
| `normalize_processor.py` | 归一化/反归一化 | `NormalizerProcessor`（有 mean/std 用 z-score，否则 min/max 缩放到 [-1,1]）、`UnnormalizerProcessor`（推理时反变换）、`from_lerobot_dataset`（:67）直接吃 dataset stats |
| `observation_processor.py` | 环境观测→LeRobot 格式 | `pixels`→`observation.images.*`、`agent_pos`→`observation.state`；图像 HWC·uint8→CHW·float32[0,1] |
| `device_processor.py` | 设备搬移 | 所有 tensor → GPU（non_blocking） |
| `rename_processor.py` | 键重命名 | 按 `rename_map` 重命名并同步 schema |

**流水线示例**：
```python
proc = RobotProcessor([
    VanillaObservationProcessor(),                    # 环境观测 → LeRobot 键
    NormalizerProcessor.from_lerobot_dataset(dataset), # 数据驱动归一化
    RenameProcessor(rename_map={...}),                 # 键名对齐模型
    DeviceProcessor(device="cuda:0"),
])
batch = proc(dataset_batch)
proc.save_pretrained("my_proc")   # 可复用、可分享
```

## 七、模型层：policies / model / optim / configs

### 7.1 总体架构与设计哲学

```
configs/
├── types.py         # FeatureType / NormalizationMode / PolicyFeature（数据契约原子单位）
├── policies.py      # PreTrainedConfig（所有策略配置基类）
├── default.py       # DatasetConfig / WandBConfig / EvalConfig
├── train.py         # TrainPipelineConfig（训练主配置）
├── eval.py          # EvalPipelineConfig
└── parser.py        # draccus.wrap 定制版（--policy.path 处理、插件加载）

policies/
├── pretrained.py    # PreTrainedPolicy（模型基类，HubMixin）
├── factory.py       # make_policy / get_policy_class
├── normalize.py     # Normalize / Unnormalize（数据集 stats 归一化）
├── utils.py         # 队列、设备/dtype/shape 工具
└── <策略名>/        # 每个策略 = configuration_*.py（配置）+ modeling_*.py（模型）
```

**核心设计**：每个策略是一个目录，拆成"配置类"（draccus dataclass：超参数、特征声明、训练预设）和"模型类"（nn.Module）。配置类注册到 `PreTrainedConfig`，模型类绑定 `config_class`/`name`。

> ⚠️ 版本事实：v0.3.4 中**没有** `base_policy.py`/`registry.py`（更新版才有）；本版基类是 `policies/pretrained.py` 的 `PreTrainedPolicy`，注册靠 draccus `ChoiceRegistry`。**Pi0 模型定义也不在 model/ 目录**，而在 `policies/pi0/` 内。

### 7.2 基类与归一化

**`PreTrainedPolicy`（pretrained.py:253）**：
- `__init_subclass__` 强制子类声明 `config_class` 与 `name`
- 保存/加载：`config.json`（draccus dump）+ `model.safetensors`；`from_pretrained` 自动 `to(device)` 且默认 `eval()`（要训练需手动 `train()`）
- **5 个抽象方法 = 策略接口**：`get_optim_params()`（参数分组，每组独立 lr）、`reset()`（清缓存队列）、`forward(batch)→(loss, loss_dict)`、`predict_action_chunk(batch)`、`select_action(batch)`（内部处理观测历史缓存与动作块队列消费）

**`PreTrainedConfig`（configs/policies.py）**：
- 公共字段：`n_obs_steps`、`normalization_mapping`、`input_features`/`output_features`（make_policy 填充）、`device`/`use_amp`/`push_to_hub`…
- **3 个抽象 delta 属性**：`observation_delta_indices`/`action_delta_indices`/`reward_delta_indices`——声明该策略需要数据集取哪些相对帧（数据集端据此拼时间窗口）
- **2 个训练预设**：`get_optimizer_preset()`/`get_scheduler_preset()`——"每个策略自带训练配方"，train.py 在 `use_policy_training_preset=True` 时直接调用
- `from_pretrained` classmethod：读 config.json 并保留 CLI 覆盖

**归一化（normalize.py:420）**：每个策略三段式——
```python
self.normalize_inputs    = Normalize(config.input_features,  mapping, dataset_stats)
self.normalize_targets   = Normalize(config.output_features, mapping, dataset_stats)
self.unnormalize_outputs = Unnormalize(config.output_features, mapping, dataset_stats)
```
- stats 两种来源：**首次训练**由 `make_policy(ds_meta=dataset.meta)` 传入；**微调/评估**随 state_dict 存进模型自动恢复
- 初始值全是 inf，forward 里发现 inf 直接断言报错（防止静默用错统计量）
- MIN_MAX 映射到 [-1,1]；图像 stats shape 缩成 (c,1,1)

### 7.3 八种策略 + 奖励分类器速查

| 策略 | 类型 | 动作生成方式 | 关键类 |
|------|------|-------------|--------|
| **act** | 行为克隆 | CVAE Transformer + 动作块（chunk=100） | `ACTPolicy`/`ACT`/`ACTTemporalEnsembler` |
| **diffusion** | 行为克隆 | 条件扩散 1D U-Net（DDPM/DDIM） | `DiffusionPolicy`/`DiffusionModel`/`DiffusionConditionalUnet1d` |
| **pi0** | VLA | PaliGemma + 流匹配 expert（10 步 Euler） | `PI0Policy`/`PI0FlowMatching`/`PaliGemmaWithExpertModel` |
| **pi0fast** | VLA | FAST 动作 tokenizer + 自回归生成 | `PI0FASTPolicy`/`PI0FAST` |
| **vqbet** | 行为克隆 | Residual VQ-VAE + minGPT（code+offset） | `VQBeTPolicy`/`VQBeTModel`/`VqVae` |
| **sac** | RL | tanh 高斯随机策略 + 熵正则 | `SACPolicy`/`CriticEnsemble`/`DiscreteCritic` |
| **tdmpc** | RL+MPC | 潜世界模型 + MPPI/CEM 规划 | `TDMPCPolicy`/`TDMPCTOLD` |
| **smolvla** | VLA | SmolVLM + 流匹配 expert | `SmolVLAPolicy`/`VLAFlowMatching`/`SmolVLMWithExpertModel` |
| reward_classifier | 奖励模型 | 预训练视觉编码器分类成功/失败 | `Classifier`/`SpatialLearnedEmbeddings` |

**逐个要点**：
- **ACT**：VAE encoder（[cls, 状态, 动作序列]→潜变量）+ ResNet 视觉 + Transformer encoder + DETR 风格 decoder；L1 重建损失 + KL；时间集成 `ACTTemporalEnsembler`（指数加权在线递推）。注意 `n_decoder_layers=1` 是忠实复刻原版 bug
- **Diffusion**：`horizon=16`/`n_action_steps=8`/`n_obs_steps=2`、`drop_n_last_frames=7`（训练丢尾部帧避免过度 padding）；U-Net 残差块用 **FiLM 调制**注入观测与时间步；`SpatialSoftmax` 把特征图压成关键点坐标（源自 Finn 的 Deep Spatial Autoencoders）
- **π0**：图像 resize 224 保持宽高比加 padding；state/action pad 到 32 维；训练时 t~Beta(1.5,1) 插值构造速度场 MSE；推理前缀 KV cache + 10 步 Euler；`_transform_state_dict_keys` 正则映射 JAX 权重键名；`flex_attention.py` 块稀疏注意力加速
- **VQ-BeT**：两阶段（先训 RVQ 2 万步再训 GPT）；token 序列按"每步观测 + action query"交错；推理 code 采样温度 `bet_softmax_temperature=0.1`
- **TD-MPC**：五合一损失（consistency/reward/Q/V/π）；5 个 Q 集成；CEM：π 采样 + 高斯采样 → `estimate_value`（FOWM eqn 4，奖励 + 不确定性正则）→ elite softmax 更新
- **SAC**：`MultiAdamConfig` 三组独立优化器（actor/critic/temperature）；`TanhMultivariateNormalDiag`；共享编码器缓存图像特征；自带默认 ImageNet stats
- **SmolVLA**：与 π0 同构（同一套流匹配范式），expert 更小（宽度 ×0.75）、支持交叉注意力接 VLM 的 KV

### 7.4 model/ 目录

只有 `model/kinematics.py` 一个文件：`RobotKinematics` —— placo 库的正/逆运动学封装（`forward_kinematics` 返回 4×4 位姿；`inverse_kinematics` 迭代求解），给末端空间控制/仿真用。

### 7.5 optim/ — 优化器/调度器工厂

- `optimizers.py`：`OptimizerConfig` 基类（`build(params)` 抽象）→ `AdamConfig`/`AdamWConfig`/`SGDConfig`/`MultiAdamConfig`（SAC 专用，按参数分组名建多个优化器）；`save/load_optimizer_state`（safetensors + json）
- `schedulers.py`：`DiffuserSchedulerConfig`（diffusers get_scheduler）/`VQBeTSchedulerConfig`（两阶段：先恒 lr 训 VQ-VAE 再 warmup+cosine）/`CosineDecayWithWarmupSchedulerConfig`（PI 训 π0 用）
- `factory.py`：`make_optimizer_and_scheduler(cfg, policy)` —— 开预设时用 `policy.get_optim_params()` 分组，否则全参数

### 7.6 一次训练调用的完整数据流

```
train.py → cfg.validate()（填充策略预设优化器）
→ make_policy(cfg.policy, ds_meta=dataset.meta)   # features 填充 + stats 注入
→ ACTPolicy.__init__：validate_features → Normalize(stats 覆盖 inf 缓冲) → ACT 模型 → reset()
→ 训练循环：forward（normalize→模型→L1+KL 损失含 padding mask）→ backward → 梯度裁剪 → step
→ 推理：select_action → 队列空时 predict_action_chunk → 逐帧 pop → unnormalize → 环境
```

**学习顺序建议**：`configs/types.py` → `configs/policies.py` → `policies/pretrained.py` → `policies/normalize.py` → `policies/factory.py`（建立骨架）→ act → diffusion → vqbet → tdmpc（复杂度递增）→ 最后攻 pi0/smolvla/pi0fast（共享流匹配范式，对照读）。

## 八、应用层：CLI / scripts / utils

### 8.1 顶层 CLI 模块（用户视角流程 → 代码调用链）

所有 CLI 统一模式：`@draccus.wrap()` 解析 dataclass 配置 → `main()` → 主函数。

| CLI | 文件 | 工作流程 |
|-----|------|----------|
| `lerobot-calibrate` | `calibrate.py`（92 行） | robot/teleop **二选一**（`__post_init__` 强制校验）→ `make_*_from_config` 构造 → `connect(calibrate=False)` → `calibrate()` → `disconnect()` |
| `lerobot-record` | `record.py`（403 行） | `hw_to_dataset_features` 构造 schema → `LeRobotDataset.create` 新建（含多线程 image_writer）→ `robot/teleop.connect` → 键盘监听 → 外层循环：`record_loop`（录 `episode_time_s` 秒：`teleop.get_action()`→`robot.send_action`→`dataset.add_frame`）+ 不录制的复位时段 → `save_episode` → `push_to_hub`。键盘：右箭头提前结束、左箭头重录上一集、Esc 停止 |
| `lerobot-replay` | `replay.py`（121 行） | 只加载指定 episode 的 action 列 → 逐帧 `robot.send_action`，`busy_wait` 保持 fps |
| `lerobot-teleoperate` | `teleoperate.py`（163 行） | 纯遥操不录数据：`teleop_loop`（:104-131）循环 `get_action`→`send_action` |
| `lerobot-setup-motors` | `setup_motors.py`（88 行） | 校验设备类型（`COMPATIBLE_DEVICES` 白名单）→ `device.setup_motors()`（实现在各 robot/teleop 类里） |
| `lerobot-find-port` | `find_port.py`（69 行） | 拔线法：拔线前/后扫 `/dev/tty*` 差集，必须恰好差 1 个端口 |
| `lerobot-find-cameras` | `find_cameras.py`（319 行） | `OpenCVCamera.find_cameras()`/`RealSenseCamera.find_cameras()` 枚举 + `ThreadPoolExecutor` 并行抓图存 png |

### 8.2 scripts/ 顶层脚本

| 文件 | 功能 | 关键点 |
|------|------|--------|
| `train.py`（295 行） | **离线模仿学习训练主脚本** | 流程（`train()` L108-286）：验证配置→WandB/本地日志→`set_seed`→`make_dataset`→（可选）`make_env` 仿真评测→`make_policy`→优化器/调度器→DataLoader（需要 `drop_n_last_frames` 时用 `EpisodeAwareSampler`）→`cycle(dataloader)` 无限采样→训练循环（`update_policy`：forward→AMP→scale(loss).backward→unscale→clip_grad→step→scheduler→可选 EMA `policy.update()`）→按频率日志/存 checkpoint（`save_checkpoint`+`update_last_checkpoint` 维护 `last` 软链）/仿真评测渲染视频 |
| `eval.py`（510 行） | 策略评测 | `rollout()`（:84-217）：`policy.reset()`→循环 `select_action`→`env.step` 直到全部 done；`eval_policy()`：按 batch 跑、`argmax(done)` 截断、线程写 mp4、聚合 `avg_sum_reward/pc_success` |
| `visualize_dataset.py` | Rerun 可视化单集 | 逐帧 `rr.log` 图像/标量 |
| `visualize_dataset_html.py` | Flask 网页可视化 | 标量转 CSV 给 Dygraph 画图；本地模式符号链接 videos 目录 |
| `visualize_image_transforms.py` | 可视化数据增强 | 组合变换/单变换/边界值各出一张图 |
| `display_sys_info.py` | 系统诊断 | try-import 探测各依赖版本，输出可粘贴到 issue |
| `find_joint_limits.py` | 遥操测量关节/EE 边界 | `RobotKinematics` 正运动学 + 30s 遥操记录 min/max |

### 8.3 scripts/rl/（HIL-SerL 分布式强化学习，gRPC Actor/Learner）

| 文件 | 功能 | 关键点 |
|------|------|--------|
| `rl/learner.py`（1216 行） | **Learner 训练进程** | 3 个 Queue（transition/interaction/参数）+ gRPC 服务子进程；主循环：transitions 入 `ReplayBuffer`（跳过 NaN）→ 等样本够 → SAC 风格更新（`utd_ratio` 次 critic + 定期 actor/temperature）→ 推参数给 actor → 存 checkpoint（buffer 转存 LeRobotDataset） |
| `rl/learner_service.py`（118 行） | Learner 的 gRPC servicer | `StreamParameters`（只发最新参数）/`SendTransitions`/`SendInteractions` |
| `rl/actor.py`（703 行） | **Actor 执行进程**（真机交互） | 连接 learner（重试 30 次）→ 3 个并发进程（收参数/发 transition/发交互）→ `act_with_policy`：`policy.select_action`→`env.step`，**人为干预时用人的动作覆盖** |
| `rl/gym_manipulator.py`（2264 行） | **真机 Gym 环境工厂** | `RobotEnv` 包装真实机器人（EE delta 动作驱动）；wrapper 体系：`AddJointVelocityToObservation`/`RewardWrapper`（reward classifier 判成功）/`ImageCropResizeWrapper`/`ResetWrapper`；**干预机制**：`BaseLeaderControlWrapper` 及子类（主从机干预、空格切换、跟踪误差自动触发、手柄、键盘）；`make_robot_env` 按 `control_mode` 叠 wrapper |
| `rl/crop_dataset_roi.py` | 交互式裁剪数据集 ROI | OpenCV 画矩形→逐帧 crop+resize 生成新数据集 |
| `rl/eval_policy.py` | HIL-SerL 真机评测 | 跑 10 集统计 success rate |

### 8.4 scripts/server/（远程策略推理："服务器跑模型，边缘跑机器人"）

| 文件 | 功能 | 关键点 |
|------|------|--------|
| `server/policy_server.py`（404 行） | gRPC 策略服务器 | `SendObservations` 收观测（**过滤：已推理过的 / 与上次太相似的直接丢弃**）→ `GetActions` 取最新观测 `predict_action_chunk` → 时间戳标注 `TimedAction` 序列返回 |
| `server/robot_client.py`（508 行） | 机器人侧客户端 | `control_loop`：队列有动作就执行；水位低于阈值就发观测（`must_go` 标志保证动作耗尽时观测必然被推理）；`_aggregate_action_queues` 按 timestep 聚合 |
| `server/configs.py` / `constants.py` / `helpers.py` | 配置/常量/辅助 | `SUPPORTED_POLICIES`（act/smolvla/diffusion/pi0/tdmpc/vqbet）、`TimedData`/`FPSTracker`/`RemotePolicyConfig` |

### 8.5 constants.py / errors.py / __init__.py

- **`constants.py`（55 行）**：数据键名约定 `OBS_STATE="observation.state"`、`OBS_IMAGES="observation.images"`、`ACTION="action"`、`REWARD="next.reward"`；checkpoint 文件约定（`checkpoints/{step}/pretrained_model/` + `training_state/`，`last` 软链）；缓存目录 `HF_LEROBOT_HOME=~/.cache/huggingface/lerobot`、`HF_LEROBOT_CALIBRATION`（旧环境变量 `LEROBOT_HOME` 会直接报错）
- **`errors.py`（43 行）**：只有 3 个异常——`DeviceNotConnectedError`、`DeviceAlreadyConnectedError`、`InvalidActionError`
- **`__init__.py`（213 行）**：不 import 重量级依赖，只导出资源清单（`available_datasets`/`available_policies`/`available_robots`…）

### 8.6 utils/ 逐文件清单（17 个）

| 文件 | 功能 | 关键函数 |
|------|------|----------|
| `utils.py`（385 行） | 通用工具（含 torch 设备选择） | `auto_select_torch_device`/`get_safe_torch_device`、`init_logging`（自定义格式含行号）、`TimerManager`（fps 统计）、`enter_pressed`/`move_cursor_up`（交互终端） |
| `logging_utils.py` | 训练指标跟踪 | `AverageMeter`、`MetricsTracker`（自动派生 samples/episodes/epochs，`__setattr__` 自动写 meter） |
| `visualization_utils.py` | Rerun 可视化 | `_init_rerun`、`log_rerun_data` |
| `control_utils.py` | 控制循环辅助 | `predict_action`（numpy 观测→torch→策略→CPU 张量）、`init_keyboard_listener`（左右箭头/Esc 事件）、`sanity_check_dataset_robot_compatibility`（DeepDiff 校验 resume 兼容性）、`log_control_info`（fps 不足标黄） |
| `train_utils.py` | checkpoint 存取 | `save_checkpoint`/`load_training_state`/`update_last_checkpoint`（`last` 软链） |
| `io_utils.py` | IO | `write_video`（imageio）、`deserialize_json_into_object`（严格 JSON→dataclass，`from_pretrained` 用） |
| `buffer.py`（842 行） | **RL ReplayBuffer** | 预分配环形存储、DRQ 图像增强（所有图拼一起增强再切回）、`from/to_lerobot_dataset`（buffer↔数据集互转）、异步预取迭代器 |
| `random_utils.py` | 种子管理 | 三套 RNG（python/numpy/torch）serialize 到 safetensors、`set_seed`、`seeded_context` |
| `hub.py` | 轻量 HubMixin | `save_pretrained`/`from_pretrained`/`push_to_hub`（比 HF 版更轻） |
| `transition.py` | RL transition 类型 | `Transition` TypedDict、`move_transition_to_device` |
| `wandb_utils.py` | WandB | `WandBLogger`（resume="must"）、policy checkpoint 存 artifact |
| `encoding_utils.py` | 有符号整数编码 | 符号-幅值/补码编解码（电机指令用） |
| `import_utils.py` | 轻量包探测 | `is_package_available`（不真 import） |
| `robot_utils.py` | 机器人循环辅助 | `busy_wait`（Mac/Win 忙等、Linux sleep）、`safe_disconnect` 装饰器 |
| `process.py` | 优雅停机 | `ProcessSignalHandler`（首次信号设 shutdown_event，第二次强制退出） |
| `queue.py` | 跨进程队列 | `get_last_item_from_queue`（只取最新一条并清空） |
| `benchmark.py` | 耗时基准 | `TimeBenchmark`（上下文管理器/装饰器） |

**跨模块学习要点**：
1. **两条训练链路**：`train.py`（离线模仿学习：固定数据集+DataLoader 采样）vs `rl/learner.py+actor.py`（在线 HIL-SerL：gRPC 通信+ReplayBuffer+SAC 更新+人类干预）
2. **checkpoint 约定**：`checkpoints/{6位步号}/pretrained_model/`（可 `from_pretrained`）+ `training_state/`（恢复训练），`last` 软链指向最新
3. **数据键约定**：`observation.state`、`observation.images.<cam>`、`action`、`next.reward/done/success`——全库统一

## 九、SO-101 完整代码路径

你手上有 SO-101 主从臂，以下是"一次遥操作"涉及的全部代码路径（这是理解全库最好的切入视角）：

### 9.1 启动（teleoperate.py）

```
lerobot-teleoperate
  └─ teleoperate.py:main → teleoperate() (:134)
       ├─ make_teleoperator_from_config(cfg.teleop)   # teleoperators/utils.py:19
       │    └─ SO101Leader(cfg)                        # so101_leader.py:37
       │         └─ FeetechMotorsBus(port, motors={6×sts3215}, calibration)  # feetech.py:99
       ├─ make_robot_from_config(cfg.robot)            # robots/utils.py:23
       │    └─ SO101Follower(cfg)                      # so101_follower.py:37
       ├─ teleop.connect(calibrate=True)  → bus.connect() 握手（型号+固件校验）
       │    └─ 未校准则自动 calibrate()（或从 {id}.json 载入写回电机）
       ├─ robot.connect()  → 同样校验 + configure()
       │    └─ configure(): torque_disabled 上下文内
       │         configure_motors(return_delay=0, accel=254)
       │         + P=16/I=0/D=32 减震 PID + gripper 防烧参数
       └─ teleop_loop() (:104-131)  主循环
            action = teleop.get_action()   # sync_read 6 电机 → _normalize → {motor}.pos
            robot.send_action(action)      # ensure_safe_goal_position → sync_write Goal_Position
            busy_wait(1/fps)
```

### 9.2 校准（calibrate.py → so101_follower.py:110）

```
lerobot-calibrate --robot.type=so101_follower
  └─ device.calibrate()  (so101_follower.py:110-147)
       1. 有校准文件 → 提示回车直接用 / 输 c 重校准
       2. disable_torque + 全部 POSITION 模式
       3. "移到行程中点按回车" → bus.set_half_turn_homings() (motors_bus.py:692)
             reset_calibration → sync_read(原值) → 按 Feetech 公式 offset=pos-res/2 写回
       4. "转动所有关节走完全程" → bus.record_ranges_of_motion() (motors_bus.py:723)
             实时表格 MIN|POS|MAX，min==max 抛错
       5. MotorCalibration(id, drive_mode, homing_offset, range_min, range_max)
          → write_calibration（EEPROM+缓存）→ _save_calibration() → {id}.json
```

### 9.3 扳机→夹爪（你遥操作验证过的链路）

```
手指捏主臂扳机
  → 主臂 gripper 电机（1/147 可反驱）被物理转动
  → SO101Leader.get_action(): sync_read 读到新编码器值 → 归一化 gripper.pos∈[0,100]
  → teleop_loop 原样传 dict
  → SO101Follower.send_action: key.removesuffix(".pos") 还原电机名 → 匹配 gripper
  → bus.sync_write("Goal_Position") → 从臂夹爪合拢
```

关键点：**主从臂电机命名与归一化范围完全同构 → 位置天然 1:1 按名传递**。

### 9.4 采集数据（record.py）

```
lerobot-record
  → record() (record.py:289)
      hw_to_dataset_features (datasets/utils.py:395)  # 关节→observation.state/action schema
      LeRobotDataset.create (lerobot_dataset.py:1005)
      record_loop: teleop.get_action → robot.send_action → dataset.add_frame
        相机帧 → AsyncImageWriter 异步存 PNG → save_episode 时 ffmpeg 编码 mp4
      → 落盘 parquet+mp4+v2.1 meta，可 push_to_hub
```

### 9.5 双相机（你的 9005/9221）

`cameras/opencv/` 的 `OpenCVCameraConfig.index_or_path` 直接吃 `/dev/v4l/by-id/...` 稳定路径；`record.py` 的 `--robot.cameras='{cam_follower: {...}, cam_third: {...}}'` 经 `make_cameras_from_configs` 延迟导入实例化。

## 十、核心数据流

### 流 1：采集（硬件 → 磁盘）

```
Teleoperator.get_action() ─┐
Robot.get_observation() ───┼→ record_loop 每帧组装:
Camera.async_read() ───────┘    {observation.state, action, observation.images.cam_*,
                                  timestamp, frame_index, episode_index, task_index}
   → dataset.add_frame（内存缓冲 + 异步 PNG）
   → save_episode: parquet 落盘 + stats 计算 + PNG→mp4 编码 + meta 更新
```

### 流 2：训练（磁盘 → 模型）

```
LeRobotDataset.__getitem__:
  parquet 取帧 → delta_timestamps 拼时间窗口（+_is_pad 掩码）
  → mp4 按时间戳解码视频帧 → image_transforms 增强
→ make_policy(ds_meta) 注入 dataset stats
→ forward: normalize_inputs → 模型 → 损失（掩码 padding）→ 反向 → 优化器
→ save_checkpoint: pretrained_model/config.json+model.safetensors + training_state/
```

### 流 3：推理（模型 → 硬件）

```
离线: eval.py → policy.select_action → unnormalize → env.step
真机: record/replay 或 scripts/server/:
      robot_client 收观测 → gRPC 发 policy_server
      → predict_action_chunk → TimedAction 序列返回 → 客户端按 timestep 执行
      或本机: teleoperate/replay 直接 select_action → robot.send_action
```

## 十一、设计模式速查

| 模式 | 出现位置 | 说明 |
|------|---------|------|
| **ChoiceRegistry 注册**（draccus） | Robot/Teleoperator/Camera/Policy/Env/Optimizer/Scheduler Config | `@XxxConfig.register_subclass("name")` 装饰器注册字符串名，`cfg.type` 反查；CLI `--xxx.type=name` 多态实例化 |
| **工厂 + 延迟导入** | `make_robot_from_config`、`make_teleoperator_from_config`、`make_cameras_from_configs`、`make_policy` | 按 `type` 字符串 if/elif 分发，函数内部才 import 实现类，可选依赖缺失不拖垮整个包 |
| **类变量配置表注入** | MotorsBus 子类 | 控制表/波特率表/编码表/分辨率表以类变量赋值，基类模板方法完成公共流程 |
| **配置即模型**（dataclass+保存） | PreTrainedPolicy/RobotProcessor | `config.json` + `safetensors` 成对保存，`from_pretrained` 完整还原，支持 CLI 覆盖 |
| **组合优于继承** | BiSO101Follower/BiSO101Leader | 双臂=持有两个单臂实例，键加前缀/拆分派发 |
| **模板方法** | MotorsBus 的 read/write/sync_read/sync_write、各 Robot 的 calibrate | 公共流程在基类，细节钩子在子类（`_encode_sign`、`_get_half_turn_homings` 等） |
| **副作用导入注册** | `record.py:79` 等 `from lerobot.robots import (...)` | 靠 import 触发 `register_subclass` 装饰器 |
| **上下文管理器保证清理** | `torque_disabled()`、`VideoEncodingManager`、`safe_stop_image_writer` | 异常路径也保证扭矩恢复/视频兜底编码 |
| **镜像接口契约** | Robot vs Teleoperator | 键名对齐的隐式约定：主端输出 == 从臂 action 键 |

## 十二、从零复现路线图

**目标：不看 LeRobot，自己写出一个能跑的最小 LeRobot。**

### 阶段 1：核心抽象（第 1-2 周）

1. 写 `Motor`/`MotorCalibration`/`MotorsBus`：串口连接、ping、read/write、sync_read/sync_write、归一化三种模式（抄 motors_bus.py 的结构，Feetech 协议表抄 tables.py）
2. 写 `Robot`/`Teleoperator` 基类 + 配置注册（用 draccus 或自己写个 50 行的注册表）
3. 用你的 SO-101 验证：能读主臂位置、能让从臂动起来 = 通关

### 阶段 2：采集与数据（第 3 周）

4. 写 LeRobotDataset 最小版：parquet 存标量、mp4 存视频、info.json、`add_frame`/`save_episode`/`__getitem__` + delta_timestamps
5. 写 record.py 流程：teleop loop + 键盘监听 + 异步图像写入
6. 采 10 集数据，用 visualize_dataset 检查

### 阶段 3：训练策略（第 4-5 周）

7. 写 `PreTrainedPolicy` + `Normalize`/`Unnormalize` + stats 注入
8. 复现 ACT 最小版（或先最简单的 MLP 策略）：配置→模型→训练循环→checkpoint
9. 训练 → 用你采的数据跑起来 → 到这一步你已经有了一个可工作的 LeRobot 子集

### 阶段 4：进阶（第 6 周+）

10. Diffusion Policy（1D U-Net + FiLM + SpatialSoftmax）
11. 远端推理（transport + server/client）或 HIL-SerL 的 Actor/Learner
12. 相机异步读帧线程模型、processor 流水线

**每个阶段的验收标准都是"在你的 SO-101 实机上跑通"**——这也正是这个项目的初衷：代码必须最终服务于真实硬件。

---

*完。祝学习顺利！遇到具体代码问题随时来问。*
