from typing import Optional

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout

from schema.PositionSchema import Position
from Wrappers.ToolWrapper import ToolWrapper

class JogModeDialog(QDialog):
    """Modal low-latency jog mode.

    While open:
    - 1-9 sets step size (mm)
    - WASD jogs carriage 1
    - Arrow keys jog carriage 2

    Behavior:
    - Holding a key does not spam moves (auto-repeat ignored)
    - If the tool is moving, additional jog keypresses are ignored
    - Sends non-blocking absolute moves using a local position estimate

    On close:
    - Calls tool.refresh_position() once to sync the rest of the software
    """

    STEP_SIZES_MM = [0.05, 0.1, 0.5, 1, 5, 10, 25, 50, 100]

    def __init__(self, tool: ToolWrapper, parent=None):
        super().__init__(parent)
        self.tool = tool

        self.setWindowTitle("Jog Mode")
        self.setModal(True)

        self._label = QLabel(
            "Jog Mode Active\n\n"
            "- WASD: Carriage 1\n"
            "- Arrow Keys: Carriage 2\n"
            "- 1-9: Step size\n\n"
            "Close this window to exit."
        )
        self._label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        layout = QVBoxLayout(self)
        layout.addWidget(self._label)

        self.step_mm: float = self.STEP_SIZES_MM[0]
        self._pressed_keys: set[int] = set()

        self._pos_est: Optional[Position] = None

        # Make sure we receive key events.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def showEvent(self, event: QEvent) -> None:
        super().showEvent(event)
        self.activateWindow()
        self.raise_()
        self.setFocus()

        # One-time refresh to seed the local absolute position estimate.
        try:
            self._pos_est = self.tool.refresh_absolute_position()
        except Exception as exc:
            print(f"JogModeDialog: failed to refresh on entry: {exc}")
            self._pos_est = Position(x1=0, y1=0, x2=0, y2=0)

        self._update_label()

    def closeEvent(self, event) -> None:
        # One-time refresh to sync the rest of the software.
        try:
            self.tool.refresh_position()
        except Exception as exc:
            print(f"JogModeDialog: failed to refresh on exit: {exc}")

        super().closeEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()

        # Ignore modifier combos to avoid breaking shortcuts.
        if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier):
            event.ignore()
            return

        # Step size selection
        step_index = self._step_index_for_key(key)
        if step_index is not None:
            if not event.isAutoRepeat():
                self.step_mm = self.STEP_SIZES_MM[step_index]
                self._update_label()
            event.accept()
            return

        # Movement key
        if not self._is_movement_key(key):
            event.ignore()
            return

        if event.isAutoRepeat():
            event.accept()
            return

        if key in self._pressed_keys:
            event.accept()
            return
        self._pressed_keys.add(key)

        if self._pos_est is None:
            try:
                self._pos_est = self.tool.refresh_absolute_position()
            except Exception:
                self._pos_est = Position(x1=0, y1=0, x2=0, y2=0)

        delta = self._delta_for_key(key)
        if delta is None:
            event.accept()
            return

        # Update local estimate and send a non-blocking absolute jog immediately.
        self._pos_est = self._apply_delta(self._pos_est, delta)
        target = Position(
            x1=self._pos_est.x1 if delta.x1 is not None else None,
            y1=self._pos_est.y1 if delta.y1 is not None else None,
            x2=self._pos_est.x2 if delta.x2 is not None else None,
            y2=self._pos_est.y2 if delta.y2 is not None else None,
        )
        try:
            self.tool.move_absolute(target, blocking=False)
        except Exception as exc:
            print(f"JogModeDialog: jog failed: {exc}")

        event.accept()

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        self._pressed_keys.discard(event.key())
        event.ignore()

    def _update_label(self) -> None:
        self._label.setText(
            "Jog Mode Active\n\n"
            "- WASD: Carriage 1\n"
            "- Arrow Keys: Carriage 2\n"
            "- 1-9: Step size\n\n"
            f"Current step: {self.step_mm} mm\n\n"
            "Close this window to exit."
        )

    @staticmethod
    def _step_index_for_key(key: int) -> Optional[int]:
        mapping = {
            Qt.Key.Key_1: 0,
            Qt.Key.Key_2: 1,
            Qt.Key.Key_3: 2,
            Qt.Key.Key_4: 3,
            Qt.Key.Key_5: 4,
            Qt.Key.Key_6: 5,
            Qt.Key.Key_7: 6,
            Qt.Key.Key_8: 7,
            Qt.Key.Key_9: 8,
        }
        return mapping.get(Qt.Key(key), None) if not isinstance(key, Qt.Key) else mapping.get(key, None)

    @staticmethod
    def _is_movement_key(key: int) -> bool:
        keys = {
            Qt.Key.Key_W,
            Qt.Key.Key_A,
            Qt.Key.Key_S,
            Qt.Key.Key_D,
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
        }
        return (Qt.Key(key) in keys) if not isinstance(key, Qt.Key) else (key in keys)

    def _delta_for_key(self, key: int) -> Optional[Position]:
        step = float(self.step_mm)

        # Carriage 1
        if key == Qt.Key.Key_W:
            return Position(y1=+step)
        if key == Qt.Key.Key_S:
            return Position(y1=-step)
        if key == Qt.Key.Key_A:
            return Position(x1=-step)
        if key == Qt.Key.Key_D:
            return Position(x1=+step)

        # Carriage 2
        if key == Qt.Key.Key_Up:
            return Position(y2=+step)
        if key == Qt.Key.Key_Down:
            return Position(y2=-step)
        if key == Qt.Key.Key_Left:
            return Position(x2=-step)
        if key == Qt.Key.Key_Right:
            return Position(x2=+step)

        return None

    @staticmethod
    def _apply_delta(pos: Position, delta: Position) -> Position:
        def add(a: Optional[float], b: Optional[float]) -> Optional[float]:
            if b is None:
                return a
            if a is None:
                return b
            return a + b

        return Position(
            x1=add(pos.x1, delta.x1),
            y1=add(pos.y1, delta.y1),
            x2=add(pos.x2, delta.x2),
            y2=add(pos.y2, delta.y2),
        )
