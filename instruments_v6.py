import sys
import time
import serial
import math
import os
import argparse
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QGroupBox, QSizePolicy, QPushButton,
    QSlider, QSpinBox, QGridLayout
)
from PyQt5.QtCore import QTimer, Qt, QPointF
from PyQt5.QtGui import QPainter, QColor, QFont, QPen, QFontMetrics

class CompactAnalogGauge(QWidget):
    def __init__(self, title, min_val, max_val, units, parent=None):
        super().__init__(parent)
        self.title = title
        self.min_val = min_val
        self.max_val = max_val
        self.units = units
        self.value = min_val
        self.setMinimumSize(150, 150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
    def set_value(self, value):
        self.value = max(self.min_val, min(value, self.max_val))
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Compact dimensions
        width = self.width()
        height = self.height()
        size = min(width, height) * 0.65
        x_center = width / 2
        y_center = height * 0.65
        radius = size * 0.4
        
        # Draw gauge background
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(30, 30, 40))
        painter.drawEllipse(QPointF(x_center, y_center), radius, radius)
        
        # Draw gauge rim
        pen = QPen(QColor(100, 100, 150), 2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(x_center, y_center), radius, radius)
        
        # Draw gauge arc
        start_angle = 180
        span_angle = 180
        pen = QPen(QColor(0, 150, 255), 6)
        painter.setPen(pen)
        painter.drawArc(
            int(x_center - radius), 
            int(y_center - radius), 
            int(radius * 2), 
            int(radius * 2), 
            start_angle * 16, 
            span_angle * 16
        )
        
        # Draw ticks
        pen = QPen(Qt.white, 1.5)
        painter.setPen(pen)
        for i in range(0, 7):
            angle = 180 + i * 30
            rad_angle = math.radians(angle)
            
            # Calculate tick positions
            inner_x = x_center + (radius * 0.7) * math.cos(rad_angle)
            inner_y = y_center + (radius * 0.7) * math.sin(rad_angle)
            outer_x = x_center + (radius * 0.9) * math.cos(rad_angle)
            outer_y = y_center + (radius * 0.9) * math.sin(rad_angle)
            
            painter.drawLine(int(inner_x), int(inner_y), int(outer_x), int(outer_y))
            
            # Draw numbers
            if i % 2 == 0:
                value = self.min_val + (i / 6) * (self.max_val - self.min_val)
                # Format values appropriately
                if self.max_val >= 10000:
                    if self.max_val > 30000:
                        text = f"{value/1000:.0f}k" 
                    else:
                        text = f"{value/1000:.1f}k"
                elif self.max_val >= 1000:
                    text = f"{value/1000:.1f}k"
                else:
                    text = f"{value:.0f}"
                    
                text_width = QFontMetrics(painter.font()).width(text)
                text_height = QFontMetrics(painter.font()).height()
                
                num_x = x_center + (radius * 0.75) * math.cos(rad_angle) - text_width / 2
                num_y = y_center + (radius * 0.75) * math.sin(rad_angle) + text_height / 3
                
                painter.drawText(int(num_x), int(num_y), text)
        
        # Draw needle
        value_ratio = (self.value - self.min_val) / (self.max_val - self.min_val)
        needle_angle = 180 + value_ratio * 180
        
        # Draw needle base
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(200, 30, 30))
        painter.drawEllipse(QPointF(x_center, y_center), radius * 0.08, radius * 0.08)
        
        # Draw needle
        rad_angle = math.radians(needle_angle)
        needle_x = x_center + (radius * 0.85) * math.cos(rad_angle)
        needle_y = y_center + (radius * 0.85) * math.sin(rad_angle)
        
        pen = QPen(QColor(220, 30, 30), 2)
        painter.setPen(pen)
        painter.drawLine(int(x_center), int(y_center), int(needle_x), int(needle_y))
        
        # Draw title
        painter.setPen(Qt.white)
        font = QFont("Arial", 9, QFont.Bold)
        painter.setFont(font)
        title_width = QFontMetrics(font).width(self.title)
        painter.drawText(int(x_center - title_width/2), int(height * 0.15), self.title)
        
        # Draw digital value
        if self.max_val >= 10000:
            if self.max_val > 30000:
                value_text = f"{self.value:.0f} {self.units}"
            else:
                value_text = f"{self.value:.1f} {self.units}"
        else:
            value_text = f"{self.value:.1f} {self.units}"
            
        font = QFont("Arial", 10, QFont.Bold)
        painter.setFont(font)
        value_width = QFontMetrics(font).width(value_text)
        
        # Draw value background
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(40, 40, 60))
        rect_width = value_width * 1.2
        rect_height = QFontMetrics(font).height() * 1.3
        painter.drawRect(
            int(x_center - rect_width/2), 
            int(y_center + radius * 0.45),
            int(rect_width), 
            int(rect_height)
        )
        
        # Draw value text
        painter.setPen(QColor(0, 200, 255))
        painter.drawText(
            int(x_center - value_width/2), 
            int(y_center + radius * 0.45 + rect_height * 0.75), 
            value_text
        )

class CompactSerialMonitor(QMainWindow):
    def __init__(self, serial_port=None):
        super().__init__()
        self.setWindowTitle("Instrumentation Monitor")
        self.setGeometry(50, 50, 1400, 650)
        
        # Serial connection variables
        self.ser = None
        self.serial_port = serial_port
        self.log_file = None
        self.log_file_path = ""
        
        # Gauge configuration
        self.gauge_config = [
            {"title": "Thrust", "min": 0, "max": 5000, "units": "g", "key": "thrust"},
            {"title": "Current", "min": 0, "max": 30, "units": "A", "key": "current"},
            {"title": "Voltage", "min": 0, "max": 30, "units": "V", "key": "voltage"},
            {"title": "RPM", "min": 0, "max": 15000, "units": "rpm", "key": "rpm"},
            {"title": "Power", "min": 0, "max": 1000, "units": "W", "key": "power"},
            {"title": "Eff", "min": 0, "max": 30, "units": "g/W", "key": "eff"},
        ]
        
        # Create main widgets
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setSpacing(8)
        self.layout.setContentsMargins(10, 10, 10, 10)
        
        # Create single row for all five gauges
        gauges_layout = QHBoxLayout()
        gauges_layout.setSpacing(5)
        
        # Create gauges from configuration
        self.gauges = {}
        for config in self.gauge_config:
            gauge = CompactAnalogGauge(
                config["title"], 
                config["min"], 
                config["max"], 
                config["units"]
            )
            self.gauges[config["key"]] = gauge
            gauges_layout.addWidget(gauge)
        
        self.layout.addLayout(gauges_layout)
        
        # Create status bar
        status_layout = QHBoxLayout()
        status_layout.setSpacing(8)
        
        # Last update time display
        time_group = QGroupBox("Last Update")
        time_group.setMaximumHeight(65)
        time_layout = QVBoxLayout()
        self.time_label = QLabel("Never")
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #00C8FF;")
        time_layout.addWidget(self.time_label)
        time_group.setLayout(time_layout)
        status_layout.addWidget(time_group)
        
        # Serial status
        status_group = QGroupBox("Serial Status")
        status_group.setMaximumHeight(65)
        status_group_layout = QVBoxLayout()
        self.status_label = QLabel("Disconnected")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 14px;")
        status_group_layout.addWidget(self.status_label)
        status_group.setLayout(status_group_layout)
        status_layout.addWidget(status_group)
        
        # Log file status
        log_status_group = QGroupBox("Log File")
        log_status_group.setMaximumHeight(65)
        log_status_layout = QVBoxLayout()
        self.log_status_label = QLabel("Not logging")
        self.log_status_label.setAlignment(Qt.AlignCenter)
        self.log_status_label.setStyleSheet("font-size: 12px; color: #FFA500;")
        log_status_layout.addWidget(self.log_status_label)
        log_status_group.setLayout(log_status_layout)
        status_layout.addWidget(log_status_group)
        
        self.layout.addLayout(status_layout)
        
        # Create serial log display
        log_group = QGroupBox("Serial Log (Last 10)")
        log_layout = QVBoxLayout()
        
        # Log controls
        log_controls_layout = QHBoxLayout()
        self.log_button = QPushButton("Start Logging")
        self.log_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 4px;
                border-radius: 3px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.log_button.clicked.connect(self.toggle_logging)
        log_controls_layout.addWidget(self.log_button)
        
        self.open_log_button = QPushButton("Open Log")
        self.open_log_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 4px;
                border-radius: 3px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
        """)
        self.open_log_button.clicked.connect(self.open_log_file)
        self.open_log_button.setEnabled(False)
        log_controls_layout.addWidget(self.open_log_button)
        log_controls_layout.addStretch()
        
        log_layout.addLayout(log_controls_layout)
        
        # Log list
        self.log_list = QListWidget()
        self.log_list.setMaximumHeight(90)
        self.log_list.setStyleSheet("""
            QListWidget {
                background-color: #1E1E2E;
                color: #E0E0FF;
                font-family: Consolas, monospace;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 2px;
            }
        """)
        log_layout.addWidget(self.log_list)
        log_group.setLayout(log_layout)
        self.layout.addWidget(log_group)
        
        # Create power control section
        power_group = QGroupBox("Power Control")
        power_layout = QGridLayout()
        power_layout.setVerticalSpacing(4)
        
        # Slider for power level (0-1000)
        self.power_label = QLabel("Power:")
        self.power_label.setStyleSheet("color: #E0E0FF; font-size: 12px;")
        power_layout.addWidget(self.power_label, 0, 0)
        
        self.power_slider = QSlider(Qt.Horizontal)
        self.power_slider.setRange(0, 1000)
        self.power_slider.setValue(500)
        self.power_slider.setTickPosition(QSlider.TicksBelow)
        self.power_slider.setTickInterval(100)
        self.power_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #3A3A4A;
                height: 6px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #00C8FF;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QSlider::sub-page:horizontal {
                background: #00A0C0;
                border-radius: 3px;
            }
        """)
        self.power_slider.valueChanged.connect(self.send_power_value)
        power_layout.addWidget(self.power_slider, 0, 1, 1, 3)
        
        # Delta control
        self.delta_label = QLabel("Δ:")
        self.delta_label.setStyleSheet("color: #E0E0FF; font-size: 12px;")
        power_layout.addWidget(self.delta_label, 1, 0)
        
        self.delta_spin = QSpinBox()
        self.delta_spin.setRange(1, 100)
        self.delta_spin.setValue(10)
        self.delta_spin.setStyleSheet("""
            QSpinBox {
                background-color: #2A2A3A;
                color: white;
                border: 1px solid #444466;
                border-radius: 3px;
                padding: 3px;
                font-size: 11px;
            }
        """)
        self.delta_spin.setMaximumWidth(60)
        power_layout.addWidget(self.delta_spin, 1, 1)
        
        # Increase/Decrease buttons
        self.decrease_button = QPushButton("-")
        self.decrease_button.setStyleSheet("""
            QPushButton {
                background-color: #F44336;
                color: white;
                font-weight: bold;
                font-size: 14px;
                min-width: 30px;
                min-height: 24px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #D32F2F;
            }
        """)
        self.decrease_button.clicked.connect(self.decrease_power)
        power_layout.addWidget(self.decrease_button, 1, 2)
        
        self.increase_button = QPushButton("+")
        self.increase_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                font-size: 14px;
                min-width: 30px;
                min-height: 24px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #388E3C;
            }
        """)
        self.increase_button.clicked.connect(self.increase_power)
        power_layout.addWidget(self.increase_button, 1, 3)
        
        # Current power value display
        self.current_power_label = QLabel("Current: 500")
        self.current_power_label.setStyleSheet("color: #00C8FF; font-size: 14px; font-weight: bold;")
        power_layout.addWidget(self.current_power_label, 2, 0, 1, 4, Qt.AlignCenter)
        
        power_group.setLayout(power_layout)
        self.layout.addWidget(power_group)
        
        # Create command input
        command_layout = QHBoxLayout()
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("Enter command and press Enter to send")
        self.command_input.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                font-size: 12px;
                background-color: #2A2A3A;
                color: #FFFFFF;
                border: 1px solid #444466;
                border-radius: 3px;
            }
        """)
        self.command_input.returnPressed.connect(self.send_command)
        command_layout.addWidget(self.command_input)
        
        self.layout.addLayout(command_layout)
        
        # Setup timers
        self.serial_timer = QTimer()
        self.serial_timer.timeout.connect(self.check_serial)
        self.serial_timer.start(1)
        
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_time_display)
        self.update_timer.start(1000)
        
        # Initialize variables
        self.last_update_time = time.time()
        self.thrust_value = 0
        self.current_value = 0
        self.voltage_value = 0
        self.rpm_value = 0
        self.power_value = 0
        self.eff_value = 0
        self.log_entries = []
        self.is_logging = False
        
        # Connect slider value change to update display
        self.power_slider.valueChanged.connect(self.update_power_display)
        
        # Request serial port
        self.get_serial_port()

    def update_power_display(self, value):
        self.current_power_label.setText(f"Current: {value}")

    def increase_power(self):
        delta = self.delta_spin.value()
        new_value = min(1000, self.power_slider.value() + delta)
        self.power_slider.setValue(new_value)
        self.send_power_value()

    def decrease_power(self):
        delta = self.delta_spin.value()
        new_value = max(0, self.power_slider.value() - delta)
        self.power_slider.setValue(new_value)
        self.send_power_value()

    def send_power_value(self):
        value = 1000 + self.power_slider.value()
        cmd = f"P {value}\n"
        
        if self.ser and self.ser.is_open:
            try:
                self.ser.write(cmd.encode())
                log_entry = f"Sent: {cmd.strip()}"
                self.add_log(log_entry)
                
                # Write to log file if logging is enabled
                if self.is_logging and self.log_file:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    self.log_file.write(f"[{timestamp}] TX: {log_entry}\n")
                    self.log_file.flush()
            except Exception as e:
                self.add_log(f"Power send error: {str(e)}")
        else:
            self.add_log("Not connected to serial port - power command not sent")

    def get_serial_port(self):
        # Determine default port if not specified
        if self.serial_port is None:
            if sys.platform.startswith('win'):
                self.serial_port = "COM3"
            else:
                self.serial_port = "/dev/ttyUSB0"
        
        # Update status before attempting connection
        self.status_label.setText(f"Connecting to {self.serial_port}...")
        self.status_label.setStyleSheet("color: #FFA500; font-weight: bold;")
        QApplication.processEvents()  # Force UI update
            
        try:
            # Use 115200 baud rate
            self.ser = serial.Serial(self.serial_port, 115200, timeout=0.1)
            self.status_label.setText(f"Connected to {self.serial_port} @ 115200")
            self.status_label.setStyleSheet("color: #00FF80; font-weight: bold;")
            self.add_log(f"Connected to {self.serial_port} @ 115200 baud")
        except Exception as e:
            self.status_label.setText(f"Error: {str(e)}")
            self.status_label.setStyleSheet("color: #FF5050; font-weight: bold;")
            self.add_log(f"Error connecting to {self.serial_port}: {str(e)}")
            self.add_log("Please check connection and restart with --port option")
            self.ser = None

    def toggle_logging(self):
        if not self.is_logging:
            # Start logging
            self.start_logging()
        else:
            # Stop logging
            self.stop_logging()

    def start_logging(self):
        # Create logs directory if it doesn't exist
        logs_dir = "logs"
        if not os.path.exists(logs_dir):
            os.makedirs(logs_dir)
        
        # Create log file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file_path = os.path.join(logs_dir, f"instrument_log_{timestamp}.txt")
        
        try:
            self.log_file = open(self.log_file_path, 'a')
            self.is_logging = True
            self.log_button.setText("Stop Logging")
            self.log_button.setStyleSheet("""
                QPushButton {
                    background-color: #f44336;
                    color: white;
                    padding: 4px;
                    border-radius: 3px;
                    font-weight: bold;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #d32f2f;
                }
            """)
            # Show only filename, not full path
            filename = os.path.basename(self.log_file_path)
            self.log_status_label.setText(filename)
            self.log_status_label.setStyleSheet("color: #4CAF50; font-weight: bold; font-size: 11px;")
            self.open_log_button.setEnabled(True)
            self.add_log(f"Started logging to: {filename}")
        except Exception as e:
            self.add_log(f"Failed to open log file: {str(e)}")
            self.log_status_label.setText("Error opening file")
            self.log_status_label.setStyleSheet("color: #FF5050; font-weight: bold; font-size: 11px;")

    def stop_logging(self):
        if self.log_file:
            try:
                self.log_file.close()
                self.is_logging = False
                self.log_button.setText("Start Logging")
                self.log_button.setStyleSheet("""
                    QPushButton {
                        background-color: #4CAF50;
                        color: white;
                        padding: 4px;
                        border-radius: 3px;
                        font-weight: bold;
                        font-size: 12px;
                    }
                    QPushButton:hover {
                        background-color: #45a049;
                    }
                """)
                self.log_status_label.setText("Logging stopped")
                self.log_status_label.setStyleSheet("color: #FFA500; font-weight: bold; font-size: 11px;")
                self.add_log(f"Stopped logging. File saved")
            except Exception as e:
                self.add_log(f"Error closing log file: {str(e)}")

    def open_log_file(self):
        if self.log_file_path and os.path.exists(self.log_file_path):
            try:
                if sys.platform.startswith('win'):
                    os.startfile(self.log_file_path)
                elif sys.platform.startswith('darwin'):
                    os.system(f'open "{self.log_file_path}"')
                else:
                    os.system(f'xdg-open "{self.log_file_path}"')
            except Exception as e:
                self.add_log(f"Failed to open log file: {str(e)}")
        else:
            self.add_log("Log file doesn't exist")

    def check_serial(self):
        if self.ser and self.ser.in_waiting:
            try:
                # Read raw bytes
                raw_data = self.ser.readline()
                
                # Try to decode as ASCII
                try:
                    line = raw_data.decode('ascii').strip()
                except UnicodeDecodeError:
                    # If ASCII fails, try UTF-8 with replacement
                    try:
                        line = raw_data.decode('utf-8', errors='replace').strip()
                    except:
                        # If all else fails, use raw hex representation
                        line = "RAW: " + raw_data.hex()
                
                if line:
                    self.add_log(line)
                    
                    # Only process CSV data
                    if self.is_csv_data(line):
                        self.process_serial_data(line)
                    
                    # Write to log file if logging is enabled
                    if self.is_logging and self.log_file:
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                        self.log_file.write(f"[{timestamp}] RX: {line}\n")
                        self.log_file.flush()
            except Exception as e:
                self.add_log(f"Read error: {str(e)}")

    def is_csv_data(self, data):
        """Check if data appears to be CSV format"""
        # Require at least 4 commas for 5 values
        return data.count(',') >= 4

    def process_serial_data(self, data):
        try:
            # Extract numbers, commas, and decimal points
            cleaned_data = ''.join(c for c in data if c in '0123456789,.- ')
            parts = cleaned_data.split(',')
            
            if len(parts) >= 5:
                # Parse all values
                time_ms = int(parts[0].strip())
                thrust = float(parts[1].strip())
                current = float(parts[2].split()[0].strip())
                voltage = float(parts[3].split()[0].strip())
                rpm = float(parts[4].split()[0].strip())
                
                # Calculate power
                power = 0
                if (current >= 0.001):
                    power = voltage * current

                # Calculate eff
                eff = 0
                if (power >= 0.001):
                    eff = thrust/power;
                
                # Update values
                self.thrust_value = thrust
                self.current_value = current
                self.voltage_value = voltage
                self.rpm_value = rpm
                self.power_value = power
                self.eff_value = eff
                self.last_update_time = time.time()
                
                # Update gauges from configuration
                self.gauges["thrust"].set_value(thrust)
                self.gauges["current"].set_value(current)
                self.gauges["voltage"].set_value(voltage)
                self.gauges["rpm"].set_value(rpm)
                self.gauges["power"].set_value(power)
                self.gauges["eff"].set_value(eff)
                
                # Update time display
                self.time_label.setText(f"{time_ms/1000.0} s")
        except ValueError as e:
            # Don't log non-CSV errors since we're already ignoring them
            pass

    def update_time_display(self):
        # This timer updates the "time since last update" display
        if self.last_update_time:
            seconds_ago = int(time.time() - self.last_update_time)
            if seconds_ago > 5:
                self.time_label.setStyleSheet("color: #FF5050; font-weight: bold;")
            else:
                self.time_label.setStyleSheet("color: #00C8FF; font-weight: bold;")

    def add_log(self, entry):
        self.log_entries.append(entry)
        # Keep only last 10 entries
        if len(self.log_entries) > 10:
            self.log_entries.pop(0)
        
        # Update list widget
        self.log_list.clear()
        self.log_list.addItems(self.log_entries)
        self.log_list.scrollToBottom()

    def send_command(self):
        if self.ser and self.ser.is_open:
            cmd = self.command_input.text() + "\n"
            try:
                self.ser.write(cmd.encode())
                log_entry = f"Sent: {cmd.strip()}"
                self.add_log(log_entry)
                
                # Write to log file if logging is enabled
                if self.is_logging and self.log_file:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    self.log_file.write(f"[{timestamp}] TX: {log_entry}\n")
                    self.log_file.flush()
                
                self.command_input.clear()
            except Exception as e:
                self.add_log(f"Send error: {str(e)}")
        else:
            self.add_log("Not connected to serial port")

    def closeEvent(self, event):
        # Close serial connection
        if self.ser and self.ser.is_open:
            self.ser.close()
        
        # Close log file
        if self.log_file and not self.log_file.closed:
            self.log_file.close()
        
        event.accept()

if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Instrumentation Monitor')
    parser.add_argument('--port', type=str, help='Serial port device')
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    
    # Set dark theme
    app.setStyle("Fusion")
    dark_palette = app.palette()
    dark_palette.setColor(dark_palette.Window, QColor(30, 30, 40))
    dark_palette.setColor(dark_palette.WindowText, Qt.white)
    dark_palette.setColor(dark_palette.Base, QColor(25, 25, 35))
    dark_palette.setColor(dark_palette.AlternateBase, QColor(35, 35, 45))
    dark_palette.setColor(dark_palette.ToolTipBase, Qt.white)
    dark_palette.setColor(dark_palette.ToolTipText, Qt.white)
    dark_palette.setColor(dark_palette.Text, Qt.white)
    dark_palette.setColor(dark_palette.Button, QColor(50, 50, 70))
    dark_palette.setColor(dark_palette.ButtonText, Qt.white)
    dark_palette.setColor(dark_palette.BrightText, Qt.red)
    dark_palette.setColor(dark_palette.Highlight, QColor(0, 120, 215))
    dark_palette.setColor(dark_palette.HighlightedText, Qt.black)
    app.setPalette(dark_palette)
    
    window = CompactSerialMonitor(args.port)
    window.show()
    sys.exit(app.exec_())