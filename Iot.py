import sys, json, hashlib, serial, serial.tools.list_ports
import os, hashlib
from dotenv import load_dotenv
from collections import deque
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QRect, QPoint
from PyQt6.QtGui import QAction, QPainter, QColor, QPen, QShortcut, QKeySequence, QFont, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QComboBox, QLineEdit, QTextEdit, QGroupBox, QCheckBox,
    QRadioButton, QButtonGroup, QSpinBox, QMessageBox, QFileDialog, QDialog,
    QFormLayout, QTabWidget, QSlider, QFrame, QToolButton
)
from dotenv import load_dotenv
import os


# ====== CONFIG ======
DEFAULT_BAUD = 115200
AUTO_STATUS_MS = 1000


load_dotenv()
USERNAME = os.getenv("IOT_USER", "").strip()
PASSWORD_PLAIN = os.getenv("IOT_PASSWORD", "").strip()
if not USERNAME or not PASSWORD_PLAIN:
    raise ValueError("Missing USERNAME or PASSWORD in .env file!")
PASSWORD_HASH = hashlib.sha256(PASSWORD_PLAIN.encode()).hexdigest()



# Mặc định khi an toàn (gas < THR LOW) → reset thiết bị về trạng thái này
DEFAULT_LED = 0        # 0..1
DEFAULT_FAN = 0        # 0/1
DEFAULT_SERVO = 0      # độ (đóng cửa)

# Khi gas >= THR LOW → bật (fan + mở cửa)
ALARM_FAN = 1
ALARM_SERVO = 90       # mở cửa

# ---------- Login ----------
# ---------- Login ----------

class LoginDialog(QDialog):
    def __init__(self, username_env, password_hash_env):
        super().__init__()
        self.env_user = username_env
        self.env_hash = password_hash_env

        self.setWindowTitle("Login IoT Dashboard")
        self.setModal(True)
        self.setFixedWidth(360)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.edUser = QLineEdit()
        self.edPass = QLineEdit()
        self.edPass.setEchoMode(QLineEdit.EchoMode.Password)
        self.cbShow = QCheckBox("Show password")
        self.cbShow.toggled.connect(self._toggle)

        form.addRow("Username:", self.edUser)
        form.addRow("Password:", self.edPass)
        form.addRow("", self.cbShow)
        layout.addLayout(form)

        row = QHBoxLayout()
        self.btnLogin = QPushButton("Login")
        self.btnCancel = QPushButton("Quit")
        row.addStretch()
        row.addWidget(self.btnCancel)
        row.addWidget(self.btnLogin)
        layout.addLayout(row)

        self.btnLogin.clicked.connect(self.try_login)
        self.btnCancel.clicked.connect(self.reject)
        self.edUser.returnPressed.connect(self.edPass.setFocus)
        self.edPass.returnPressed.connect(self.try_login)

        self._tries = 0
        self._max = 5

        self.setStyleSheet("""
            QLineEdit { padding:6px; }
            QPushButton {
                padding:6px 12px;
                border-radius:8px;
                background:#0ea5e9;
                color:#fff;
            }
            QPushButton:hover { background:#38bdf8; }
        """)

    def _toggle(self, checked: bool):
        self.edPass.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def try_login(self):
        u, p = self.edUser.text().strip(), self.edPass.text()
        hash_input = hashlib.sha256(p.encode()).hexdigest()
        ok = (u == self.env_user) and (hash_input == self.env_hash)

        if ok:
            QMessageBox.information(self, "Success", "Login successful!")
            self.accept()
            return

        self._tries += 1
        QMessageBox.warning(
            self,
            "Login failed",
            f"Invalid username or password.\nAttempts left: {self._max - self._tries}",
        )
        if self._tries >= self._max:
            QMessageBox.critical(self, "Locked", "Too many failed attempts.")
            self.reject()


# ---------- Serial đọc nền ----------
class SerialReader(QThread):
    lineReceived = pyqtSignal(str)
    statusParsed = pyqtSignal(dict)
    def __init__(self, ser):
        super().__init__()
        self.ser = ser; self._run=True; self._buf=""
    def run(self):
        try:
            while self._run and self.ser and self.ser.is_open:
                data = self.ser.read(128)
                if not data: self.msleep(20); continue
                try: self._buf += data.decode(errors="ignore")
                except: continue
                while "\n" in self._buf:
                    line, self._buf = self._buf.split("\n",1); line=line.strip()
                    if not line: continue
                    self.lineReceived.emit(line)
                    import re

                    # ...
                    if "{" in line and "}" in line:
                        match = re.search(r'\{.*\}', line)
                        if match:
                            json_str = match.group()
                            try:
                                data = json.loads(json_str)
                                self.statusParsed.emit(data)
                            except Exception as e:
                                print("⚠ JSON error:", e, "->", json_str[:80])
                        # bỏ qua phần ký tự rác còn lại

        except: pass
    def stop(self): self._run=False

# ---------- Canvas vẽ đồ thị GAS ----------
class GasCanvas(QWidget):
    def __init__(self, parent=None, max_points=300):
        super().__init__(parent); self.history=deque(maxlen=max_points)
        self.thr_lo, self.thr_hi = 380, 450; self.setMinimumHeight(120)
    def set_thresholds(self, lo, hi): self.thr_lo, self.thr_hi = lo, hi; self.update()
    def push(self, gas):
        if gas is not None: self.history.append(int(gas)); self.update()
    def paintEvent(self, ev):
        p = QPainter(self); r = self.rect()
        p.fillRect(r, QColor("#0b1220"))
        p.setPen(QPen(QColor("#334155"), 1)); p.drawRect(r.adjusted(0,0,-1,-1))
        def y(v): return r.bottom()-int((v/1023.0)*r.height())
        p.setPen(QPen(QColor("#fbbf24"), 1, Qt.PenStyle.DashLine)); p.drawLine(r.left(), y(self.thr_lo), r.right(), y(self.thr_lo))
        p.setPen(QPen(QColor("#ef4444"), 1, Qt.PenStyle.DashLine)); p.drawLine(r.left(), y(self.thr_hi), r.right(), y(self.thr_hi))
        if len(self.history)>=2:
            step = r.width()/max(1,len(self.history)-1)
            p.setPen(QPen(QColor("#22d3ee"), 2))
            for i in range(len(self.history)-1):
                p.drawLine(int(r.left()+i*step), y(self.history[i]),
                           int(r.left()+(i+1)*step), y(self.history[i+1]))
        p.setPen(QColor("#94a3b8")); p.drawText(QRect(r.left()+6,r.top()+6,200,18), Qt.AlignmentFlag.AlignLeft, "GAS history")

# ---------- Kawaii Home View ----------
class nhapromax(QFrame):
    """Isometric house + overlay icon (LED/FAN/SERVO) + status panel + optional background image."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Nha pRo mAx")
        self.setStyleSheet("""
            /* === ComboBox (Port chọn COMx, đẹp và bo tròn) === */
    QComboBox {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                                    stop:0 #0f172a, stop:1 #1e293b);
        color: #e2e8f0;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 6px 28px 6px 12px;
        min-width: 100px;
    }
    QComboBox:hover {
        border: 1px solid #3b82f6;
    }
    QComboBox::drop-down {
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 26px;
        border-left: 1px solid #334155;
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                                    stop:0 #06b6d4, stop:1 #3b82f6);
        border-top-right-radius: 12px;
        border-bottom-right-radius: 12px;
    }
    QComboBox::down-arrow {
        image: none;
        border-left: 6px solid transparent;
        border-right: 6px solid transparent;
        border-top: 7px solid white;
        margin-right: 8px;
    }
    
    /* === SpinBox (THR LOW / HIGH) === */
    QSpinBox {
        background: #0f172a;
        color: #e2e8f0;
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 6px 10px;
        min-width: 80px;
    }
    QSpinBox::up-button,
    QSpinBox::down-button {
        width: 0;
        height: 0;
        border: none;
        background: transparent;
    }

    QFrame#KawaiiHome {
        background: #fff7ed;
        border: 1px solid #facc15;
        border-radius: 12px;
    }
    QToolButton {
        background: rgba(255,255,255,0.85);
        border: 1px solid #f59e0b;
        border-radius: 12px;
        padding: 6px 10px;
    }
    QToolButton:hover {
        background: #fde68a;
    }
    QLabel { color: #1f2937; }

        """)
        # states
        self.gas = 320
        self.led_on = False
        self.fan_on = False
        self.servo = 0
        self.temp = None
        self.thr_lo, self.thr_hi = 380, 450
        self.bg_pix: QPixmap|None = None
        self.buzzer_on = False  # 🔊 thêm biến trạng thái loa
        self.humid = None  # 💧 nếu bạn hiển thị độ ẩm

        # title
        self.lblTitle = QLabel("Nha pRo mAx", self)
        title_font = QFont(); title_font.setPointSize(22); title_font.setBold(True)
        self.lblTitle.setFont(title_font); self.lblTitle.move(20, 12)

        # status panel
        self.lblThermo = QLabel(self._thermo_text(), self)
        self.lblState = QLabel(self._state_text(), self)
        panelCss = "background:#fde68a; border:1px solid #f59e0b; border-radius:8px; padding:6px;"
        self.lblThermo.setStyleSheet(panelCss); self.lblState.setStyleSheet(panelCss)

        # overlay icons
        self.btnLed  = QToolButton(self); self.btnLed.setText("💡");  self.btnLed.setToolTip("LED 12V ON/OFF")
        self.btnFan  = QToolButton(self); self.btnFan.setText("🌀");  self.btnFan.setToolTip("Fan ON/OFF")
        self.btnDoor = QToolButton(self); self.btnDoor.setText("🚪 CLOSE");  self.btnDoor.setToolTip("Door (SERVO 90° = Open, 0° = Close)")
        self.btnBuzz = QToolButton(self)
        self.btnBuzz.setText("🔊")
        self.btnBuzz.setToolTip("Buzzer")
        self.btnBuzz.setEnabled(False)  # chỉ để hiển thị, không bấm
        self.btnLed.clicked.connect(self.toggle_led)
        self.btnFan.clicked.connect(self.toggle_fan)
        self.btnDoor.clicked.connect(self.bump_servo)

        self._send = None  # set_sender() sẽ gán
        self._sync_buttons()

    # API
    def set_sender(self, send_callable): self._send = send_callable
    def update_from_status(self, st:dict):
        if st.get("gas") is not None: self.gas = float(st["gas"])
        if st.get("temperature") is not None: self.temp = float(st["temperature"])
        if st.get("humidity") is not None: self.humid = float(st["humidity"])
        if st.get("led") is not None:
            self.led_on = bool(int(st["led"]))
        if st.get("fan") is not None: self.fan_on = bool(int(st["fan"]))
        if st.get("servo") is not None: self.servo = int(st["servo"])
        if st.get("alarm") is not None:
            try:
                self.buzzer_on = int(st["alarm"]) == 1
            except ValueError:
                self.buzzer_on = False

        self.lblThermo.setText(self._thermo_text()); self.lblState.setText(self._state_text())
        self._sync_buttons()
        self.repaint()

    def set_thresholds(self, lo:int, hi:int): self.thr_lo, self.thr_hi = lo, hi; self.update()
    def load_background(self, path:str):
        pix = QPixmap(path)
        if not pix.isNull(): self.bg_pix = pix; self.update()

    # interactions
    def toggle_led(self):
        self.led_on = not self.led_on
        if self._send: self._send(f"LED {1 if self.led_on else 0}")
        self.update()
    def toggle_fan(self):
        self.fan_on = not self.fan_on
        if self._send: self._send(f"FAN {1 if self.fan_on else 0}")
        self.update()
    def bump_servo(self):
        self.servo = 0 if self.servo >= 90 else 90
        if self._send: self._send(f"SERVO {self.servo}")
        self._sync_buttons()
        self.update()

    def _sync_buttons(self):
        door_open = (self.servo >= 90)
        self.btnDoor.setText("🚪" if door_open else "🚪")
        self.btnDoor.setToolTip("Door (SERVO 90° = Open, 0° = Close)")
        self._color_button(self.btnBuzz, self.buzzer_on)
        self.repaint()

    # drawing
    def paintEvent(self, e):
        p = QPainter(self); r = self.rect()
        p.fillRect(r, QColor("#fff7ed"))
        if self.bg_pix:
            scaled = self.bg_pix.scaled(r.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            p.setOpacity(0.08); p.drawPixmap(0, 0, scaled); p.setOpacity(1.0)

        house = r.adjusted(12, 48, -12, -72)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        pen = QPen(QColor("#f59e0b")); pen.setWidth(2); pen.setStyle(Qt.PenStyle.DotLine); p.setPen(pen)

        cx, cy = house.center().x(), house.center().y()+10
        w, h, z = 320, 150, 90
        A = QPoint(cx - w//2, cy)
        B = QPoint(cx + w//2, cy)
        C = QPoint(cx + w//2 + z, cy - z)
        D = QPoint(cx - w//2 + z, cy - z)
        A2 = QPoint(A.x(), A.y()-h); B2 = QPoint(B.x(), B.y()-h); C2 = QPoint(C.x(), C.y()-h); D2 = QPoint(D.x(), D.y()-h)

        # khung
        p.drawPolygon(A, B, C, D); p.drawLine(A, A2); p.drawLine(B, B2); p.drawLine(C, C2); p.drawLine(D, D2); p.drawPolygon(A2, B2, C2, D2)

        # vách ngăn
        def mid(P, Q): return QPoint((P.x()+Q.x())//2, (P.y()+Q.y())//2)
        pen2 = QPen(QColor("#94a3b8")); pen2.setStyle(Qt.PenStyle.DotLine); p.setPen(pen2)
        p.drawLine(mid(A,B),  mid(A2,B2))
        p.drawLine(mid(B,C),  mid(B2,C2))
        p.drawLine(mid(A,D),  mid(A2,D2))

        # đặt icon (tọa độ mới + raise_ để luôn click được)
        self.btnLed.move(A.x()+40, A.y()-80)                 # trái
        self.btnFan.move((A.x()+B.x())//2 - 20, A.y()-60)    # giữa
        self.btnDoor.move(C.x()-36, C.y()-110)               # phải (cửa)
        self.btnBuzz.move(D.x() + 60, D.y() - 130)
        for b in (self.btnLed, self.btnFan, self.btnDoor, self.btnBuzz):
            b.raise_(); b.show()

        # GAS badge
        gx, gy = D.x()+20, D.y()-18
        col = QColor("#10b981") if self.gas < self.thr_lo else (QColor("#f59e0b") if self.gas < self.thr_hi else QColor("#ef4444"))
        p.setBrush(col); p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(QPoint(gx, gy), 22, 22)
        p.setPen(QColor("#083344")); p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.drawText(QRect(gx-18, gy-12, 36, 24), Qt.AlignmentFlag.AlignCenter, str(int(self.gas)))

        # cập nhật style nút (cửa xanh khi MỞ)
        self._color_button(self.btnLed,  self.led_on)
        self._color_button(self.btnFan,  self.fan_on)
        self._color_button(self.btnDoor, self.servo >= 90)
        self._color_button(self.btnBuzz, self.buzzer_on)

        # status panel
        self.lblThermo.setText(self._thermo_text()); self.lblState.setText(self._state_text())
        self.lblThermo.adjustSize(); self.lblState.adjustSize()
        self.lblThermo.move(16, r.height()-self.lblThermo.height()-16)
        self.lblState.move(self.lblThermo.x()+self.lblThermo.width()+10, self.lblThermo.y())

    def _color_button(self, btn:QToolButton, on:bool):
        btn.setStyleSheet("background:{}; border:1px solid #f59e0b; border-radius:12px; padding:6px 10px;"
                          .format("#16a34a" if on else "rgba(255,255,255,0.85)"))

    def _thermo_text(self):
        t = f"{self.temp:.1f}" if self.temp is not None else "--"
        h = f"{self.humid:.0f}" if hasattr(self, "humid") and self.humid is not None else "--"
        return f"Temperature: {t} °C | Humidity: {h} %"

    def _state_text(self):
        if self.gas < self.thr_lo: return "Status: Safe"
        if self.gas < self.thr_hi: return "Status: Warning"
        return "Status: DANGER!"

# ---------- Main Window ----------
class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IoT Gas Dashboard (PyQt6) – Nha pRo mAx")
        self.ser=None; self.reader=None
        self._reset_done = False      # chống spam reset
        self._alarm_applied = False   # chống spam bật khi >= THR LOW

        # Menus
        menu = self.menuBar()
        mFile = menu.addMenu("&File")
        actConnect = QAction("Connect", self); actDisconnect = QAction("Disconnect", self)
        actSaveLog = QAction("Save Log...", self); actQuit = QAction("Quit", self)
        mFile.addActions([actConnect, actDisconnect, actSaveLog]); mFile.addSeparator(); mFile.addAction(actQuit)
        mView = menu.addMenu("&View")
        actLoadMap = QAction("Load Background Image…", self); mView.addAction(actLoadMap)
        mHelp = menu.addMenu("&Help"); actAbout = QAction("About", self); mHelp.addAction(actAbout)

        tabs = QTabWidget(); self.setCentralWidget(tabs)

        # ---- Tab 1: Dashboard ----
        dash = QWidget(); tabs.addTab(dash, "Dashboard")
        root = QVBoxLayout(dash)

        top = QHBoxLayout()
        self.cbPort = QComboBox(); self.btnScan = QPushButton("Scan")
        self.lblBaud = QLabel(f"Baud {DEFAULT_BAUD}")
        self.btnConn = QPushButton("Connect"); self.btnDisc = QPushButton("Disconnect")
        self.lblStat = QLabel("Disconnected"); self._stat("red")
        top.addWidget(QLabel("Port:")); top.addWidget(self.cbPort,1); top.addWidget(self.btnScan)
        top.addStretch(); top.addWidget(self.lblBaud); top.addStretch()
        top.addWidget(self.btnConn); top.addWidget(self.btnDisc); top.addWidget(self.lblStat)
        root.addLayout(top)

        grid = QGridLayout()

        # --- Gas & Distance ---
        self.lblGas = QLabel("---");
        self._big(self.lblGas)
        self.lblDist = QLabel("--")
        grid.addWidget(QLabel("Gas (0..1023):"), 0, 0)
        grid.addWidget(self.lblGas, 0, 1)
        grid.addWidget(QLabel("Distance (cm):"), 0, 2)
        grid.addWidget(self.lblDist, 0, 3)

        # --- Temperature & Humidity ---
        self.lblTemp = QLabel("-- °C");
        self._big(self.lblTemp)
        self.lblHumid = QLabel("-- %");
        self._big(self.lblHumid)
        self.lblTemp.setStyleSheet("color:#38bdf8; font-weight:600;")
        self.lblHumid.setStyleSheet("color:#10b981; font-weight:600;")
        grid.addWidget(QLabel("Temperature:"), 1, 0)
        grid.addWidget(self.lblTemp, 1, 1)
        grid.addWidget(QLabel("Humidity:"), 1, 2)
        grid.addWidget(self.lblHumid, 1, 3)

        # --- Thresholds ---
        self.spLo = QSpinBox();
        self.spLo.setRange(0, 1023);
        self.spLo.setValue(380)
        self.spHi = QSpinBox();
        self.spHi.setRange(0, 1023);
        self.spHi.setValue(450)
        self.btnApplyThr = QPushButton("Apply Thr")
        grid.addWidget(QLabel("THR LOW:"), 2, 0)
        grid.addWidget(self.spLo, 2, 1)
        grid.addWidget(QLabel("THR HIGH:"), 2, 2)
        grid.addWidget(self.spHi, 2, 3)
        grid.addWidget(self.btnApplyThr, 2, 4)

        root.addLayout(grid)
        root.addSpacing(8)  # thêm khoảng trống giữa các phần

        act = QGridLayout()
        self.cbLed = QCheckBox("LED Strip ON")
        act.addWidget(QLabel("LED 12V:"), 0, 0)
        act.addWidget(self.cbLed, 0, 1)

        self.cbFan = QCheckBox("Fan ON")
        act.addWidget(QLabel("Fan (Relay):"), 1, 0)
        act.addWidget(self.cbFan, 1, 1)

        # --- Servo cửa: vẫn 0–90 độ ---
        self.sServo = None
        self.vServo = QLabel("")
        root.addLayout(act)

        self.canvas = GasCanvas(); root.addWidget(self.canvas)
        self.banner = QLabel("STATUS: NORMAL")
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.banner.setStyleSheet("padding:10px; border-radius:12px; font-weight:bold; background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #0ea5e9, stop:1 #22d3ee); color:#081018;")
        root.addWidget(self.banner)
        row = QHBoxLayout()
        self.edCmd = QLineEdit(); self.edCmd.setPlaceholderText("Command: STATUS / LED 1 / FAN 1 / SERVO 90 ...")
        self.btnSend = QPushButton("Send"); row.addWidget(self.edCmd,1); row.addWidget(self.btnSend)
        root.addLayout(row)
        self.log = QTextEdit(); self.log.setReadOnly(True); self.log.setPlaceholderText("Serial log…")
        root.addWidget(self.log,1)


        tab = QWidget(); self.tab = nhapromax()
        tabs.addTab(tab, "Nha pRo mAx")
        kv = QVBoxLayout(tab); kv.addWidget(self.tab, 1)

        bar = QHBoxLayout()
        self.btnMapFan = QPushButton("Fan")
        self.btnMapLed = QPushButton("LED 12V")
        self.btnMapServo = QPushButton("Servo 0↔90")
        self.btnLoadBg = QPushButton("Chọn ảnh nền…")
        for b in (self.btnMapFan, self.btnMapLed, self.btnMapServo):
            b.setStyleSheet("padding:8px 12px; border-radius:10px; background:#334155; color:#e2e8f0;")
        bar.addWidget(self.btnMapFan); bar.addWidget(self.btnMapLed); bar.addWidget(self.btnMapServo)
        bar.addStretch(); bar.addWidget(self.btnLoadBg)
        kv.addLayout(bar)

        # Timer + shortcuts
        self.timer = QTimer(self); self.timer.setInterval(AUTO_STATUS_MS); self.timer.timeout.connect(self.tick)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=lambda: self.send("ALARM RESET"))
        QShortcut(QKeySequence("F5"), self, activated=lambda: self.send("STATUS"))

        # Wiring
        self.btnScan.clicked.connect(self.scan_ports)
        self.btnConn.clicked.connect(self.connect_serial)
        self.btnDisc.clicked.connect(self.disconnect_serial)
        self.btnSend.clicked.connect(self.send_line); self.edCmd.returnPressed.connect(self.send_line)

        self.btnApplyThr.clicked.connect(self.apply_thr)
        self.cbLed.toggled.connect(lambda b: self.send(f"LED {1 if b else 0}"))
        self.cbFan.toggled.connect(lambda b: self.send(f"FAN {1 if b else 0}"))

        actConnect.triggered.connect(self.connect_serial)
        actDisconnect.triggered.connect(self.disconnect_serial)
        actSaveLog.triggered.connect(self.save_log)
        actQuit.triggered.connect(self.close)
        actLoadMap.triggered.connect(self.choose_bg)
        self.btnLoadBg.clicked.connect(self.choose_bg)
        self.btnMapFan.clicked.connect(lambda: self.send(f"FAN {0 if self.tab.fan_on else 1}"))
        self.btnMapLed.clicked.connect(lambda: self.send(f"LED {0 if self.tab.led_on else 1}"))
        self.btnMapServo.clicked.connect(lambda: self.send(f"SERVO {0 if self.tab.servo >= 90 else 90}"))
        actAbout.triggered.connect(self.show_about)

        self.tab.set_sender(self.send)  # bridge

        self.scan_ports()

        # Theme
        self.setStyleSheet("""
        QMainWindow{background:#0b1220;}
        QLabel{color:#cbd5e1;}
        QMenuBar{background:#0f172a; color:#e2e8f0;}
        QMenuBar::item:selected{background:#1f2937;}
        QGroupBox{border:1px solid #334155; border-radius:12px; margin-top:10px;}
        QGroupBox::title{subcontrol-origin: margin; left:12px; padding:0 6px; color:#7dd3fc; font-weight:bold;}
        QComboBox, QSpinBox, QLineEdit{background:#111827; color:#e2e8f0; border:1px solid #334155; border-radius:8px; padding:6px;}
        QPushButton{padding:8px 14px; border-radius:10px; background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #06b6d4, stop:1 #3b82f6); color:white;}
        QPushButton:hover{opacity:0.9;}
        QCheckBox{color:#e2e8f0;}
        QTextEdit{background:#0b1325; color:#e5e7eb; border:1px solid #334155; border-radius:8px; padding:6px;}
        QTabBar::tab{padding:8px 16px;}
        """)

    # helpers
    def _big(self, w): w.setStyleSheet("font-size:20px; font-weight:800; color:#e2e8f0;")
    def _stat(self, color): self.lblStat.setStyleSheet(f"color:{color}; font-weight:bold;")
    def _append(self, t): self.log.append(t); self.log.moveCursor(self.log.textCursor().MoveOperation.End)

    # serial
    def scan_ports(self):
        self.cbPort.clear()
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.cbPort.addItems(ports); self._append(f"Found ports: {ports or 'None'}")
    def connect_serial(self):
        if hasattr(self,"ser") and self.ser and self.ser.is_open: return
        port = self.cbPort.currentText()
        if not port: QMessageBox.warning(self,"Port","Did not choose COM port yet!"); return
        try:
            self.ser = serial.Serial(port, DEFAULT_BAUD, timeout=0.1)
            self.reader = SerialReader(self.ser)
            self.reader.lineReceived.connect(self.on_line)
            self.reader.statusParsed.connect(self.on_status)
            self.reader.start()
            self._append(f"Connected {port} @ {DEFAULT_BAUD}")
            self.lblStat.setText("Connected"); self._stat("lime")
            self.timer.start()
            self.apply_thr(); self.send("STATUS")

        except Exception as e:
            QMessageBox.critical(self, "Serial", f"Không mở được {port}:\n{e}")
    def disconnect_serial(self):
        self.timer.stop()
        if hasattr(self,"reader") and self.reader:
            try: self.reader.stop(); self.reader.wait(200)
            except: pass
            self.reader=None
        if hasattr(self,"ser") and self.ser:
            try: self.ser.close()
            except: pass
            self.ser=None
        self.lblStat.setText("Disconnected"); self._stat("red"); self._append("Disconnected.")
    def send(self, cmd:str):
        # Ép SERVO về 0 hoặc 90 để tránh giá trị trung gian
        if cmd.upper().startswith("SERVO"):
            try:
                v = int(cmd.split()[1])
                cmd = f"SERVO {v}"
                if self.sServo:  # tránh NoneType
                    self.sServo.blockSignals(True)
                    self.sServo.setValue(v)
                    self.sServo.blockSignals(False)
                self.vServo.setText(f"{v}°")

            except:
                pass
        if hasattr(self,"ser") and self.ser and self.ser.is_open:
            try: self.ser.write((cmd+"\n").encode("utf-8"))
            except Exception as e: self._append(f"Send error: {e}")
        else:
            self._append(f"(not connected) {cmd}")

    # slots
    def on_line(self, line:str): self._append(line)

    def on_status(self, st: dict):
        gas = st.get("gas")
        self.lblGas.setText("" if gas is None else str(gas))
        dist = st.get("distance")
        self.lblDist.setText("" if dist is None else str(dist))
        if gas is not None:
            self.canvas.push(gas)
        temp = st.get("temperature")
        humid = st.get("humidity")
        if temp is not None:
            self.lblTemp.setText(f"{float(temp):.1f} °C")
        if humid is not None:
            self.lblHumid.setText(f"{float(humid):.0f} %")
        self.canvas.set_thresholds(self.spLo.value(), self.spHi.value())

        # update LED/FAN/SERVO
        if st.get("led") is not None:
            self.cbLed.blockSignals(True)
            self.cbLed.setChecked(bool(int(st["led"])))
            self.cbLed.blockSignals(False)
        if st.get("fan") is not None:
            self.cbFan.blockSignals(True)
            self.cbFan.setChecked(bool(int(st["fan"])))
            self.cbFan.blockSignals(False)
        if st.get("servo") is not None:
            v = int(st["servo"])
            if self.sServo:
                self.sServo.blockSignals(True)
                self.sServo.setValue(v)
                self.sServo.blockSignals(False)
            self.vServo.setText(f"{v}°")


        alarm = bool(st.get("alarm", 0))  # nhận từ Arduino (gas >= thrHigh)
        self.set_banner(alarm)
        self.tab.update_from_status(st)
        self.tab.set_thresholds(self.spLo.value(), self.spHi.value())

        # chỉ gửi lệnh nếu có thay đổi trạng thái
        if not hasattr(self, "_prev_alarm") or self._prev_alarm != alarm:
            self._prev_alarm = alarm
            self.send(f"ALARM {1 if alarm else 0}")

        # ======= AUTO bán phần =======
        try:
            if gas is None:
                return
            g = int(gas)
            lo = int(self.spLo.value())
            if g >= lo:
                # phát hiện khói => AUTO tạm thời
                self._apply_alarm_low_only()
                self._auto_override = True
            else:
                # hết khói => trả quyền manual
                if getattr(self, "_auto_override", False):
                    self._ensure_defaults()
                    self._auto_override = False
        except Exception as e:
            print("Auto logic error:", e)


    def _ensure_defaults(self):
        """Khi gas an toàn lại thì trả về mặc định."""
        self.send(f"FAN {DEFAULT_FAN}")
        self.send(f"SERVO {DEFAULT_SERVO}")
        self.set_banner(False)
        self._auto_applied = False

    def _apply_alarm_low_only(self):
        """Tự động bật fan + mở cửa, nhưng vẫn cho phép người dùng thao tác khác."""
        if getattr(self, "_auto_applied", False):
            return
        self.send(f"FAN {ALARM_FAN}")
        self.send(f"SERVO {ALARM_SERVO}")
        self._auto_applied = True
        self.set_banner(True)

    def set_banner(self, alarm_on:bool):
        if alarm_on:
            self.banner.setText("STATUS: ALARM")
            self.banner.setStyleSheet("padding:10px; border-radius:12px; font-weight:bold; background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #f43f5e, stop:1 #ef4444); color:white;")
        else:
            self.banner.setText("STATUS: NORMAL")
            self.banner.setStyleSheet("padding:10px; border-radius:12px; font-weight:bold; background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #0ea5e9, stop:1 #22d3ee); color:#081018;")
    def choose_bg(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn ảnh nền", "", "Images (*.png *.jpg *.jpeg)")
        if path: self.tab.load_background(path)
    def tick(self):
        # luôn hỏi STATUS
        self.send("STATUS")
    def send_line(self):
        cmd = self.edCmd.text().strip()
        if cmd: self.send(cmd); self.edCmd.clear()
    def apply_thr(self):
        self.send(f"THRLO {int(self.spLo.value())}"); self.send(f"THRHI {int(self.spHi.value())}")
        self.canvas.set_thresholds(self.spLo.value(), self.spHi.value()); self.tab.set_thresholds(self.spLo.value(), self.spHi.value())
    def save_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Log", "serial_log.txt", "Text (*.txt)")
        if path:
            with open(path,"w",encoding="utf-8") as f: f.write(self.log.toPlainText())
            QMessageBox.information(self,"Saved","Đã lưu log.")
    def show_about(self):
        QMessageBox.information(self, "About",
            "IoT Gas Dashboard + Kawaii Home (PyQt6)\n"
            "• Login demo: iot / mk123\n"
            "• LED 12V / Fan / Servo • GAS badge\n"
            "• Lệnh: STATUS / LED / FAN / SERVO / THRHI / THRLO")

def main():
    app = QApplication(sys.argv)

    # Pass env credentials into dialog
    if LoginDialog(USERNAME, PASSWORD_HASH).exec() != QDialog.DialogCode.Accepted:
        sys.exit(0)

    # Launch dashboard
    w = Main()
    w.resize(1120, 740)
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
