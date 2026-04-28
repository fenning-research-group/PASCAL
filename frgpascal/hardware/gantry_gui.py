from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout,
    QDoubleSpinBox, QGroupBox
)
from PyQt5.QtCore import Qt
import math


class AxisControlWidget(QGroupBox):
    def __init__(self, axis_name, gantry):
        super().__init__(f"{axis_name.upper()} Axis")

        self.axis = axis_name.lower()
        self.gantry = gantry

        self._build_ui()
        self.update_position()

    # -------------------------
    # UI
    # -------------------------

    def _build_ui(self):
        layout = QVBoxLayout()

        # Position display
        self.position_label = QLabel("0.00 mm")
        self.position_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.position_label)

        # Jog buttons
        jog_layout = QHBoxLayout()

        self.minus_btn = QPushButton("−")
        self.plus_btn = QPushButton("+")

        self.minus_btn.clicked.connect(lambda: self.jog(-1))
        self.plus_btn.clicked.connect(lambda: self.jog(1))

        jog_layout.addWidget(self.minus_btn)
        jog_layout.addWidget(self.plus_btn)

        layout.addLayout(jog_layout)

        # Step size selector (hardware aware)
        min_step = self.gantry.min_step[f"{self.axis}_min"]

        self.step_spin = QDoubleSpinBox()
        self.step_spin.setMinimum(min_step)
        self.step_spin.setMaximum(1000)
        self.step_spin.setSingleStep(min_step)
        self.step_spin.setValue(max(1.0, min_step))
        self.step_spin.setSuffix(" mm")

        # automatically determine decimal precision
        decimals = max(0, -int(math.floor(math.log10(min_step)))) if min_step < 1 else 3
        self.step_spin.setDecimals(decimals + 1)

        layout.addWidget(self.step_spin)

        self.setLayout(layout)

    # -------------------------
    # Logic
    # -------------------------

    def jog(self, direction):
        step = self.step_spin.value()
        delta = direction * step

        dx = dy = dz = 0.0

        if self.axis == "x":
            dx = delta
        elif self.axis == "y":
            dy = delta
        elif self.axis == "z":
            dz = delta

        # self.gantry.moverel(dx, dy, dz)
        x, y, z = tuple(self.gantry.position)
        self.gantry.position = [x + dx, y + dy, z + dz]
        self.update_position()

    def update_position(self):
        print(self.axis)
        index = {"x": 0, "y": 1, "z": 2}[self.axis]
        print(index)
        pos = self.gantry.position[index]
        print(pos)
        self.position_label.setText(f"{pos:.4f} mm")

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel
)
from PyQt5.QtCore import Qt


class GantryControlWidget(QWidget):
    def __init__(self, gantry):
        super().__init__()

        self.gantry = gantry

        self.setWindowTitle("PASCAL Gantry Control")
        self.setMinimumWidth(600)

        self._build_ui()

    # -------------------------
    # UI
    # -------------------------

    def _build_ui(self):
        main_layout = QVBoxLayout()

        # Status bar
        self.status_label = QLabel("Status: Idle")
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)

        # Axis controls
        axis_layout = QHBoxLayout()

        self.x_axis = AxisControlWidget("x", self.gantry)
        self.y_axis = AxisControlWidget("y", self.gantry)
        self.z_axis = AxisControlWidget("z", self.gantry)

        axis_layout.addWidget(self.x_axis)
        axis_layout.addWidget(self.y_axis)
        axis_layout.addWidget(self.z_axis)

        main_layout.addLayout(axis_layout)

        self.setLayout(main_layout)

    # -------------------------
    # Optional helper
    # -------------------------

    def refresh_all_positions(self):
        self.x_axis.update_position()
        self.y_axis.update_position()
        self.z_axis.update_position()


# from PyQt5.QtWidgets import (
#     QWidget, QVBoxLayout, QHBoxLayout,
#     QPushButton, QLineEdit, QLabel, QGroupBox
# )
# from PyQt5.QtCore import Qt


# class AxisControl(QGroupBox):
#     def __init__(self, axis_name, negative_label, positive_label,
#                  min_step, move_callback, snap_callback):
#         super().__init__(axis_name)

#         self.min_step = min_step
#         self.move_callback = move_callback
#         self.snap_callback = snap_callback

#         layout = QVBoxLayout()

#         # Step input
#         self.step_input = QLineEdit("0")
#         self.step_input.setAlignment(Qt.AlignCenter)
#         self.step_input.editingFinished.connect(self.snap_value)

#         layout.addWidget(self.step_input)

#         # Buttons
#         button_layout = QHBoxLayout()

#         self.neg_button = QPushButton(negative_label)
#         self.pos_button = QPushButton(positive_label)

#         self.neg_button.clicked.connect(lambda: self.move(-1))
#         self.pos_button.clicked.connect(lambda: self.move(+1))

#         button_layout.addWidget(self.neg_button)
#         button_layout.addWidget(self.pos_button)

#         layout.addLayout(button_layout)

#         # Min step annotation
#         self.annotation = QLabel(f"Minimum movement: {self.min_step} mm")
#         self.annotation.setAlignment(Qt.AlignCenter)
#         self.annotation.setStyleSheet("color: gray; font-size: 10px;")
#         layout.addWidget(self.annotation)

#         self.setLayout(layout)

#     def get_value(self):
#         try:
#             return float(self.step_input.text())
#         except ValueError:
#             return 0.0

#     def set_value(self, value):
#         self.step_input.setText(str(value))

#     def move(self, direction):
#         value = self.get_value()
#         new_value = value + direction * self.min_step
#         self.step_input.setText(str(new_value))
#         self.snap_value()

#     def snap_value(self):
#         """
#         Delegates snapping to controller via callback.
#         """
#         self.snap_callback()

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel,
    QGroupBox, QButtonGroup, QGridLayout
)
from PyQt5.QtCore import Qt


class AxisControl(QGroupBox):
    def __init__(self, axis_name,
                 negative_label,
                 positive_label,
                 min_step,
                 snap_callback,
                 preset_multipliers=None):

        super().__init__(axis_name)

        self.min_step = min_step
        self.decimals = self._infer_precision(min_step)
        self.current_step_size = self.min_step
        self.snap_callback = snap_callback

        if preset_multipliers is None:
            # preset_multipliers = [1, 2, 5, 10, 20, 50]
            preset_multipliers = [3, 7, 13, 67, 133, 667]

        # -----------------------
        # Main Horizontal Layout
        # -----------------------
        main_layout = QHBoxLayout()

        # =======================
        # LEFT SIDE (existing UI)
        # =======================
        left_layout = QVBoxLayout()

        input_container = QHBoxLayout()
        input_container.setContentsMargins(0, 0, 0, 0)
        input_container.setSpacing(4)

        self.step_input = QLineEdit("0")
        self.step_input.setAlignment(Qt.AlignRight)
        self.step_input.editingFinished.connect(self.snap_value)
        unit_label = QLabel("mm")
        unit_label.setStyleSheet("color: gray;")
        self.step_input.setStyleSheet(
            """
            QLineEdit {
                border-right: none;
            }
            """
        )
        unit_label.setStyleSheet(
            """
            QLabel {
                border: 1px solid gray;
                border-left: none;
                padding-left: 4px;
                padding-right: 4px;
                background-color: #f0f0f0;
            }
            """
        )
        input_container.addWidget(self.step_input)
        input_container.addWidget(unit_label)
        left_layout.addLayout(input_container)

        # Motion buttons
        button_layout = QHBoxLayout()

        self.neg_button = QPushButton(negative_label)
        self.pos_button = QPushButton(positive_label)

        self.neg_button.clicked.connect(lambda: self.move(-1))
        self.pos_button.clicked.connect(lambda: self.move(+1))

        button_layout.addWidget(self.neg_button)
        button_layout.addWidget(self.pos_button)

        left_layout.addLayout(button_layout)

        # Min spacing annotation
        annotation = QLabel(f"Minimum grid spacing: {self.min_step}")
        annotation.setAlignment(Qt.AlignCenter)
        annotation.setStyleSheet("color: gray; font-size: 10px;")
        left_layout.addWidget(annotation)

        main_layout.addLayout(left_layout)

        # =======================
        # RIGHT SIDE (presets)
        # =======================
        # preset_layout = QVBoxLayout()
        preset_layout = QGridLayout()
        preset_layout.setSpacing(3)

        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)

        self.preset_buttons = []
        print(preset_multipliers)
        rows = 3
        cols = 2
        for idx, mult in enumerate(preset_multipliers):
            if idx > rows*cols:
                break
            value = round(mult * self.min_step, 3)
            btn = QPushButton(str(value))
            btn.setCheckable(True)
            btn.setMinimumWidth(70)
            btn.setMinimumHeight(30)
            btn.clicked.connect(
                lambda checked, v=value, b=btn:
                self.select_preset(v, b)
            )
            btn.setStyleSheet("""
                QPushButton {
                    padding: 4px;
                }
                QPushButton:checked {
                    background-color: #4CAF50;
                    color: white;
                }
                """
            )

            self.button_group.addButton(btn)
            self.preset_buttons.append(btn)
            row = idx // cols
            col = idx % cols
            
            preset_layout.addWidget(btn, row, col)

        main_layout.addLayout(preset_layout)

        self.setLayout(main_layout)

    # --------------------------------
    # Core Logic
    # --------------------------------

    def get_value(self):
        try:
            return float(self.step_input.text())
        except ValueError:
            return 0.0

    def set_value(self, value):
        self.step_input.setText(
            self.format_value(
                value
            )
        )

    def move(self, direction):
        value = self.get_value()
        new_value = value + direction * self.current_step_size
        self.step_input.setText(
            self.format_value(
                new_value
            ))
        self.snap_value()

    def snap_value(self):
        """
        Delegates to controller for snapping.
        """
        self.snap_callback()

        # After snapping, update preset highlight if matched
        current = self.get_value()
        self.update_preset_selection(current)

    def _infer_precision(self, value):
        text = f"{value:.10f}".rstrip('0')
        if '.' in text:
            return len(text.split('.')[-1])
        return 0
    
    def format_value(self, value):
        return f"{value:.{self.decimals}f}"

    # --------------------------------
    # Preset Handling
    # --------------------------------

    def select_preset(self, value, button):
        """
        Called when preset button clicked.
        """
        self.current_step_size = float(self.format_value(value))
        # self.snap_value(self.current_step_size)

    def update_preset_selection(self, current_value):
        """
        Highlights preset button if current value matches one.
        """
        for btn in self.preset_buttons:
            if float(btn.text()) == current_value:
                btn.setChecked(True)
                return

        # If no match, uncheck all
        self.button_group.setExclusive(False)
        for btn in self.preset_buttons:
            btn.setChecked(False)
        self.button_group.setExclusive(True)

from PyQt5.QtWidgets import QWidget, QVBoxLayout


class BestGantryGUI(QWidget):
    def __init__(self, gantry):
        super().__init__()

        self.gantry = gantry
        self.setWindowTitle("Gantry Stepwise Control")

        layout = QVBoxLayout()

        # Axis controls
        self.x_axis = AxisControl(
            "X Axis",
            "Left",
            "Right",
            self.gantry.min_step['x_min'],
            # self.move_x,
            self.snap_all
        )
        self.y_axis = AxisControl(
            "Y Axis",
            "Front",
            "Back",
            self.gantry.min_step['y_min'],
            # self.move_y,
            self.snap_all
        )

        self.z_axis = AxisControl(
            "Z Axis",
            "Down",
            "Up",
            self.gantry.min_step['z_min'],
            # self.move_z,
            self.snap_all,
            [4, 7, 10, 14, 40, 100, 200]
        )

        layout.addWidget(self.x_axis)
        layout.addWidget(self.y_axis)
        layout.addWidget(self.z_axis)

        self.setLayout(layout)

    # -----------------------
    # Snap Logic (centralized)
    # -----------------------

    def snap_all(self):
        x = self.x_axis.get_value()
        y = self.y_axis.get_value()
        z = self.z_axis.get_value()

        tx, ty, tz = self.gantry._transform_coordinates(x, y, z)

        self.x_axis.set_value(tx)
        self.y_axis.set_value(ty)
        self.z_axis.set_value(tz)

    # -----------------------
    # Move Commands
    # -----------------------

    def move_x(self, value):
        x = self.x_axis.get_value()
        x += value
        tx, _, _ = self.gantry._transform_coordinates(x, 0, 0)
        self.x_axis.set_value(tx)
        pass  # optional real-time motion

    def move_y(self, value):
        y = self.y_axis.get_value()
        y += value
        _, ty, _ = self.gantry._transform_coordinates(0, y, 0)
        self.y_axis.set_value(ty)
        pass

    def move_z(self, value):
        z = self.z_axis.get_value()
        z += value
        _, _, tz = self.gantry._transform_coordinates(0, 0, z)
        self.x_axis.set_value(tz)
        pass