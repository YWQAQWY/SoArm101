"""实时显示两个串口上 6 个舵机的位置，用于识别哪只臂接在哪个端口。

用法: .venv/bin/python check_ports.py
掰动某只臂的关节，看哪一列数字在变，就能确定端口对应关系。
Ctrl+C 退出。
"""
import sys
import time

import scservo_sdk as scs

PORTS = ["/dev/ttyACM0", "/dev/ttyACM1"]
ADDR_PRESENT_POSITION = 56

handlers, packets = [], []
for p in PORTS:
    ph = scs.PortHandler(p)
    if not ph.openPort():
        print(f"{p} 打开失败，请检查接线和权限")
        sys.exit(1)
    ph.setBaudRate(1_000_000)
    handlers.append(ph)
    packets.append(scs.PacketHandler(0.0))

print("正在实时读取... 掰动一只臂的关节，看哪个端口的数据在变化。Ctrl+C 退出。")
try:
    while True:
        cols = []
        for p, ph, pkt in zip(PORTS, handlers, packets):
            vals = []
            for motor_id in range(1, 7):
                val, comm, _ = pkt.read2ByteTxRx(ph, motor_id, ADDR_PRESENT_POSITION)
                vals.append(val if comm == scs.COMM_SUCCESS else -1)
            cols.append(f"{p}: {vals}")
        print("\r" + "   |   ".join(cols), end="", flush=True)
        time.sleep(0.2)
except KeyboardInterrupt:
    print("\n已退出")
