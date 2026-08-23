# SO-ARM101 实机初始化记录

> 记录日期：2026-08-23
> 主机：Ubuntu 24.04（Noble），x86_64

## 一、环境信息

| 项目 | 内容 |
|------|------|
| ROS 2 | Jazzy（`/opt/ros/jazzy`） |
| Python 虚拟环境 | `/home/yanwq/soarm101/.venv`（Python 3.12） |
| LeRobot | 0.3.4（editable 安装，源码在 `~/soarm101/lerobot`） |
| 舵机 SDK | `scservo_sdk`（feetech-servo-sdk 1.0.0，**注意模块名是 `scservo_sdk`**） |
| MuJoCo | 3.12.0（venv 内，模型库在 `~/soarm101/mujoco_menagerie`） |

### 端口映射（重要！）

| 设备 | 串口 | 识别特征 |
|------|------|----------|
| **follower（从臂）** | `/dev/ttyACM1` | 末端是**夹爪**（两个手指） |
| **leader（主臂）** | `/dev/ttyACM0` | 末端是**手柄 + 扳机** |

> 舵机：两只臂各 6 个 STS3215，ID 1–6，波特率 1M，出厂已配置好（无需重配）。
> 判断端口小工具：`cd ~/soarm101 && .venv/bin/python init_setup/check_ports.py`（实时显示两端口各关节读数，掰哪只臂哪列变）。

### 相机（两台 USB，重启后路径不变）

| 相机 | 位置 | 稳定路径（一直用这个） |
|------|------|------------------------|
| `cam_follower` | 装在从臂上（eye-in-hand） | `/dev/v4l/by-id/usb-icSpring_icspring_camera-video-index0`（icSpring 9005） |
| `cam_third` | 第三人称（放三脚架/支架） | `/dev/v4l/by-id/usb-icSpring_icspring_camera_202404160005-video-index0`（icSpring 9221） |

> 笔记本内置摄像头（Syntek）不用管。相机都支持 640x480@30fps。
> 注意：从臂相机的线要留足余量、固定牢，避免臂运动时拉扯。

## 二、校准

> 校准数据保存在 `~/.cache/huggingface/lerobot/calibration/` 下，只在换舵机/重装系统时需要重做。
> 本机已完成（2026-08-23）：follower 与 leader 均已校准并通过遥操作验证。

### 校准命令

**follower（从臂）**：
```bash
cd ~/soarm101 && source .venv/bin/activate
lerobot-calibrate \
    --robot.type=so101_follower \
    --robot.port=/dev/ttyACM1 \
    --robot.id=follower
```

**leader（主臂）**：
```bash
lerobot-calibrate \
    --teleop.type=so101_leader \
    --teleop.port=/dev/ttyACM0 \
    --teleop.id=leader
```

### 校准操作步骤（两个提示段）

**第一段**（提示 `Move ... to the middle`）：把该臂 6 处可动部位掰到行程中间 → 回车：
1. 整个手臂左右转 → 正中间
2. 底座上面那根粗杆子前后摆 → 竖直站直
3. 中间拐弯处往上那根细杆子前后折 → 与粗杆子约垂直
4. 手腕上下翘 → 水平指向前方
5. 末端整体旋转 → 转半圈
6. 末端执行器：从臂=夹爪半开；主臂=扳机按到一半

**第二段**（屏幕滚动表格，记录行程范围）：逐个关节慢慢掰到两头，来回 2 遍：
1. 左右转：扶粗杆子，向左转到转不动 → 向右转到转不动
2. 粗杆子：向前趴到趴不动 → 向后仰到仰不动
3. 细杆子：向粗杆子折拢到折不动 → 完全展开
4. 手腕：向上翘到头 → 向下垂到头
5. 末端旋转：顺时针到头 → 逆时针到头
6. 末端执行器：从臂=夹爪最大张开→完全合拢；主臂=扳机按到底→完全松开

**判定标准**：表格 6 行每行 MIN < 2000 且 MAX > 2000（最好差 1000+），全部拉开后再回车。
（全行程 0–4095，中点 2047。某关节 MIN==MAX 会报错，说明该关节没掰动。）

> 技巧：抓着**连杆**（不是舵机）当杠杆，从臂减速比 1:345 很硬属正常；主臂 1:147/1:191 较轻松。

### 参考校准结果（本机）

| 关节 | follower MIN–MAX | leader MIN–MAX |
|------|------------------|----------------|
| shoulder_pan | 728–3302 | 741–3303 |
| shoulder_lift | 871–3259 | 725–3106 |
| elbow_flex | 854–3055 | 931–3132 |
| wrist_flex | 825–3162 | 848–3181 |
| wrist_roll | 177–3995 | 204–4005 |
| gripper | 1685–3169 | 1562–2798 |

## 三、遥操作验证

```bash
lerobot-teleoperate \
    --robot.type=so101_follower --robot.port=/dev/ttyACM1 --robot.id=follower \
    --teleop.type=so101_leader --teleop.port=/dev/ttyACM0 --teleop.id=leader
```

- 启动前两臂摆自然休息位；启动后从臂通电并跳到主臂姿势（正常现象）
- 握主臂手柄动 → 从臂实时跟随；扣主臂扳机 → 从臂夹爪合拢

## 四、串口权限固化

重新插拔后 `/dev/ttyACM*` 权限会变回 660（root:dialout），导致 `Permission denied`。永久修复：

```bash
echo 'KERNEL=="ttyACM*", MODE="0666"' | sudo tee /etc/udev/rules.d/99-tty-acm.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

临时应急：`sudo chmod 666 /dev/ttyACM0 /dev/ttyACM1`

## 五、常见问题

| 现象 | 原因 / 解决 |
|------|-------------|
| `Permission denied: '/dev/ttyACM0'` | 端口权限重置，见上节 |
| `Some motors have the same min and max values` | 校准第二段有关节没掰动，重跑并逐个掰到位 |
| 表格数字不动 | 掰错臂（端口对错）/ 电源未接 / 接线松脱 |
| 校准想重做 | 重跑校准命令，提示时输入 `c` 强制重新校准 |

## 六、常用命令备忘

```bash
source .venv/bin/activate        # 激活 venv
.venv/bin/python init_setup/check_ports.py  # 实时看两个端口读数，识别臂
lerobot-find-port                # 拔线法识别端口（交互式）

# 采集演示数据（模仿学习第一步）
lerobot-record \
    --robot.type=so101_follower --robot.port=/dev/ttyACM1 --robot.id=follower \
    --robot.cameras='{
      cam_follower: {type: opencv, index_or_path: /dev/v4l/by-id/usb-icSpring_icspring_camera-video-index0, width: 640, height: 480, fps: 30},
      cam_third: {type: opencv, index_or_path: /dev/v4l/by-id/usb-icSpring_icspring_camera_202404160005-video-index0, width: 640, height: 480, fps: 30}
    }' \
    --teleop.type=so101_leader --teleop.port=/dev/ttyACM0 --teleop.id=leader \
    --dataset.repo_id=yanwq/so101_demo \
    --dataset.single_task="Pick up the cube" \
    --dataset.num_episodes=2 \
    --dataset.episode_time_s=15 \
    --dataset.reset_time_s=15 \
    --dataset.push_to_hub=false
```

## 七、网络备忘

GitHub 直连不稳定，克隆仓库用镜像：
```bash
git clone --depth 1 https://gh-proxy.com/https://github.com/xxx/yyy.git
```
