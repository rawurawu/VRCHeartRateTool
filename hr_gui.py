import sys
import time
import asyncio
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QLabel, QFrame, QTextEdit, QPushButton, QLineEdit, QHBoxLayout)
from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtGui import QFont, QTextCursor

from bleak import BleakScanner, BleakClient
from pythonosc.udp_client import SimpleUDPClient

# ==================== 固定配置常量 ====================
HR_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HR_CHAR_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
OSC_ADDR = "127.0.0.1"
OSC_PORT = 9000
MAX_HEART_RATE = 200
TIMEOUT_SEC = 10
SCAN_INTERVAL = 2
DEVICE_NAME_KEY = "Xiaomi Smart Band"

osc_client = SimpleUDPClient(OSC_ADDR, OSC_PORT)

# ==================== 蓝牙后台线程 ====================
class BleWorker(QThread):
    sig_hr_update = Signal(int, float)
    sig_connected = Signal(bool)
    sig_msg = Signal(str)

    def __init__(self, osc_bool_param, osc_float_param):
        super().__init__()
        self._running = True
        self._scan_enable = False
        self.last_recv = 0.0
        self.flag_conn = False
        self.client = None
        self.osc_bool_name = osc_bool_param
        self.osc_float_name = osc_float_param

    def set_osc_params(self, bool_name, float_name):
        self.osc_bool_name = bool_name
        self.osc_float_name = float_name

    def start_scan(self):
        self._scan_enable = True

    def stop_all(self):
        self._scan_enable = False
        self.flag_conn = False
        if self.client and self.client.is_connected:
            asyncio.create_task(self.client.disconnect())

    def parse_data(self, sender, data):
        self.last_recv = time.time()
        self.flag_conn = True
        flag = data[0]
        if flag & 0x01 == 0:
            bpm = data[1]
        else:
            bpm = int.from_bytes(data[1:3], byteorder="little")
        pct = min(bpm / MAX_HEART_RATE, 1.0)
        self.sig_hr_update.emit(bpm, pct)
        self.sig_connected.emit(True)
        osc_client.send_message(f"/avatar/parameters/{self.osc_bool_name}", True)
        osc_client.send_message(f"/avatar/parameters/{self.osc_float_name}", pct)

    async def scan_connect_loop(self):
        while self._running:
            if not self._scan_enable:
                await asyncio.sleep(0.5)
                continue

            self.sig_msg.emit("正在扫描手环...（未打开广播则等待）")
            dev = await BleakScanner.find_device_by_filter(
                lambda d, adv: DEVICE_NAME_KEY in str(d.name),
                timeout=6
            )
            if not dev:
                self.sig_msg.emit(f"未检测到手环，{SCAN_INTERVAL}秒后重新扫描")
                self.sig_connected.emit(False)
                osc_client.send_message(f"/avatar/parameters/{self.osc_bool_name}", False)
                await asyncio.sleep(SCAN_INTERVAL)
                continue

            display_name = dev.name if dev.name is not None else "心率穿戴设备(无名称广播)"
            self.sig_msg.emit(f"已找到手环：{display_name} | MAC地址：{dev.address}")

            try:
                async with BleakClient(dev, timeout=8) as self.client:
                    await self.client.start_notify(HR_CHAR_UUID, self.parse_data)
                    self.sig_msg.emit("蓝牙连接成功，接收心率中")
                    while self._running and self.client.is_connected and self._scan_enable:
                        await asyncio.sleep(0.5)
                        now = time.time()
                        if self.flag_conn and (now - self.last_recv > TIMEOUT_SEC):
                            self.flag_conn = False
                            self.sig_msg.emit(f"{TIMEOUT_SEC}秒无心率数据，断开连接，持续自动重连中")
                            self.sig_hr_update.emit(0, 0.0)
                            self.sig_connected.emit(False)
                            osc_client.send_message(f"/avatar/parameters/{self.osc_bool_name}", False)
                            break
            except Exception as e:
                self.sig_msg.emit(f"连接失败/断开：{str(e)}，持续自动重连中")
                self.sig_connected.emit(False)
                osc_client.send_message(f"/avatar/parameters/{self.osc_bool_name}", False)
                self.client = None
                await asyncio.sleep(1)

    def run(self):
        asyncio.run(self.scan_connect_loop())

    def stop(self):
        self._running = False
        self.stop_all()

# ==================== GUI主窗口 ====================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("手环心率 OSC 转发器")
        self.setFixedSize(420, 420)
        self.setStyleSheet("background-color:#000000; color:#ffffff;")
        self.state_idle = 0
        self.state_connected = 1
        self.state_reconnect = 2
        self.current_state = self.state_idle

        center = QWidget()
        self.setCentralWidget(center)
        lay = QVBoxLayout(center)
        lay.setSpacing(12)
        lay.setContentsMargins(25,25,25,25)

        # OSC参数输入区
        param_layout = QHBoxLayout()
        lay_bool = QVBoxLayout()
        lay_bool.setSpacing(4)
        self.label_bool = QLabel("连接成功参数")
        self.edit_bool = QLineEdit("hr_connected")
        self.edit_bool.setStyleSheet("background:#222; color:white; padding:4px; border-radius:4px; border:1px solid #444;")
        lay_bool.addWidget(self.label_bool)
        lay_bool.addWidget(self.edit_bool)
        param_layout.addLayout(lay_bool)

        lay_float = QVBoxLayout()
        lay_float.setSpacing(4)
        self.label_float = QLabel("心率参数")
        self.edit_float = QLineEdit("hr_percent")
        self.edit_float.setStyleSheet("background:#222; color:white; padding:4px; border-radius:4px; border:1px solid #444;")
        lay_float.addWidget(self.label_float)
        lay_float.addWidget(self.edit_float)
        param_layout.addLayout(lay_float)
        lay.addLayout(param_layout)

        # 功能按钮
        self.action_btn = QPushButton("点击启动蓝牙扫描")
        self.action_btn.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        self.action_btn.setStyleSheet("background:#0066cc; color:white; padding:8px; border-radius:6px;")
        self.action_btn.clicked.connect(self.on_btn_click)
        lay.addWidget(self.action_btn)

        # 状态指示灯
        self.light_label = QLabel("● 未连接")
        self.light_label.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        self.light_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.light_label)

        # 心率大字
        self.hr_label = QLabel("-- BPM")
        self.hr_label.setFont(QFont("Microsoft YaHei", 42, QFont.Bold))
        self.hr_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.hr_label)

        # 百分比文字
        self.pct_label = QLabel("心率占比：0.00 / 1.00")
        self.pct_label.setFont(QFont("Microsoft YaHei", 12))
        self.pct_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.pct_label)

        # 滚动日志框
        self.log_text = QTextEdit()
        self.log_text.setStyleSheet("""
            QTextEdit{
                background:#222222;
                color:#ffffff;
                border-radius:6px;
                padding:8px;
                border:none;
            }
            QScrollBar:vertical {
                background:#333333;
                width:8px;
                border-radius:4px;
            }
            QScrollBar::handle:vertical {
                background:#666666;
                border-radius:4px;
            }
        """)
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Microsoft YaHei", 9))
        lay.addWidget(self.log_text)

        # 初始化蓝牙线程
        self.worker = BleWorker(self.edit_bool.text(), self.edit_float.text())
        self.worker.sig_hr_update.connect(self.on_hr)
        self.worker.sig_connected.connect(self.on_conn_status_change)
        self.worker.sig_msg.connect(self.append_log)
        self.worker.start()

        self.append_log("程序已就绪，请自定义OSC参数后点击【启动蓝牙扫描】")

    # 切换至空闲状态纯UI逻辑
    def set_ui_idle(self):
        self.current_state = self.state_idle
        self.action_btn.setText("点击启动蓝牙扫描")
        self.action_btn.setStyleSheet("background:#0066cc; color:white; padding:8px; border-radius:6px;")
        self.light_label.setText("● 未连接")
        self.light_label.setStyleSheet("color:#e74c3c;")
        self.hr_label.setText("-- BPM")
        self.pct_label.setText("心率占比：0.00 / 1.00")
        # 强制重绘控件
        self.action_btn.update()
        self.light_label.update()
        QApplication.processEvents()

    # 按钮点击事件
    def on_btn_click(self):
        if self.current_state == self.state_idle:
            # 启动扫描
            bool_name = self.edit_bool.text().strip()
            float_name = self.edit_float.text().strip()
            if not bool_name or not float_name:
                self.append_log("错误：OSC参数名不能为空！")
                return
            self.worker.set_osc_params(bool_name, float_name)
            self.worker.start_scan()
            self.append_log(f"已设置OSC参数：连接成功={bool_name} 心率={float_name}，开始扫描手环")

        elif self.current_state == self.state_connected:
            # 手动断开：0延迟异步刷新UI，主线程立刻释放按钮渲染
            osc_client.send_message(f"/avatar/parameters/{self.worker.osc_bool_name}", False)
            self.append_log("手动断开连接，停止扫描")
            # 关键：用QTimer把UI更新丢到下一轮事件循环，点击瞬间按钮先刷新
            QTimer.singleShot(0, self.set_ui_idle)
            # 后台断开逻辑异步执行，不阻塞界面
            QTimer.singleShot(10, self.worker.stop_all)

        elif self.current_state == self.state_reconnect:
            # 停止自动重连
            osc_client.send_message(f"/avatar/parameters/{self.worker.osc_bool_name}", False)
            self.append_log("已停止自动重连扫描，如需连接请重新点击启动")
            QTimer.singleShot(0, self.set_ui_idle)
            QTimer.singleShot(10, self.worker.stop_all)

    # 蓝牙底层自动断线回调（仅意外掉线自动重连）
    def on_conn_status_change(self, is_conn):
        if is_conn:
            self.current_state = self.state_connected
            self.action_btn.setText("断开连接")
            self.action_btn.setStyleSheet("background:#cc2222; color:white; padding:8px; border-radius:6px;")
            self.light_label.setText("● 已连接")
            self.light_label.setStyleSheet("color:#2db34a;")
        else:
            if self.worker._scan_enable:
                self.current_state = self.state_reconnect
                self.action_btn.setText("停止自动连接")
                self.action_btn.setStyleSheet("background:#e67700; color:white; padding:8px; border-radius:6px;")
                self.light_label.setText("● 断开(自动重连中)")
                self.light_label.setStyleSheet("color:#ff9900;")
            else:
                self.set_ui_idle()
            self.hr_label.setText("-- BPM")
            self.pct_label.setText("心率占比：0.00 / 1.00")
            osc_client.send_message(f"/avatar/parameters/{self.worker.osc_bool_name}", False)

    # 日志追加
    def append_log(self, text):
        self.log_text.append(text)
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)

    # 更新心率数值
    def on_hr(self, bpm, pct):
        self.hr_label.setText(f"{bpm} BPM")
        self.pct_label.setText(f"心率占比：{pct:.2f} / 1.00")

    # 窗口关闭释放线程
    def closeEvent(self, event):
        self.worker.stop()
        self.worker.wait()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())