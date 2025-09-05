from .ControllerAbstract import ButtonInventory, ControllerAbstract
from threading import Thread #right now, rather than using a thread, we just call pygame.event.pump() everytime we read from the joystick
import time
try:
    import pygame
except Exception:  # pygame is optional; keyboard mode still works
    pygame = None



class JoyStickController(ControllerAbstract):
    def __init__(self, deadzone: float=0.12, invert_z: bool=True, z_speed_scale: float=0.33) -> tuple[bool, str]:
        self.bi = ButtonInventory()
        self._last_button_times = {}
        self.deadzone = deadzone
        self.invert_z = invert_z
        self.z_speed_scale = z_speed_scale
        self.label = None

        if pygame is None:
            self.label = "Pygame not available"
        try:
            pygame.init()
            pygame.joystick.init()
            if pygame.joystick.get_count() == 0:
                self.label = "Controller: Not detected"
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            self.label = f"Controller: {self.joystick.get_name()}"
        except Exception as e:
            self.label = f"Controller error: {e}"

    def update_pygame(self):
        pygame.event.pump()
        
    def get_label(self) -> str:
        return self.label

    def shutdown(self):
        try:
            if self.joystick:
                self.joystick.quit()
        except Exception:
            pass
        try:
            if pygame:
                pygame.quit()
        except Exception:
            pass
        self.joystick = None

    def get_dir_and_feed(self) -> tuple[tuple[int, int, int], float]:
        pygame.event.pump()
        try:
            ax0 = float(self.joystick.get_axis(0))
            ax1 = float(self.joystick.get_axis(1))
        except Exception:
            ax0 = 0.0
            ax1 = 0.0
        dead = float(self.deadzone)
        
        dx = 1 if ax0 > dead else (-1 if ax0 < -dead else 0)
        dy = 1 if ax1 > dead else (-1 if ax1 < -dead else 0)

        # Only keep the largest axis movement
        if abs(ax0) > abs(ax1):
            dy = 0
        else:
            dx = 0

        # Hat Vertical for Z/C axis
        try:
            hat = self.joystick.get_hat(0)
            dz = 1 if hat[1] > 0 else (-1 if hat[1] < 0 else 0)
            if self.invert_z:
                dz = -dz
        except Exception:
            dz = 0
        
        feed = 1
        #note on feed - i don't think it makes sense to set feed from within joystick if it isnt an analog represenation of stick movement.
        #TODO: make feed a function of the joystick's axis values
        return (dx, dy, dz), float(feed)

    def get_button_states(self) -> ButtonInventory:
        pygame.event.pump()
        t = time.time()

        def debounce(key, interval) -> bool:
            last = self._last_button_times.get(key, 0)
            if t - last > interval:
                self._last_button_times[key] = t
                return True
            return False

        def read_button(button_num: int, debounce_time: float=0.2) -> bool:
            return self.joystick.get_button(button_num) and debounce(button_num, debounce_time)

        self.bi.toggle_carriages = read_button(1)
        self.bi.save_position = read_button(2)
        self.bi.goto_saved = read_button(4)
        self.bi.home_xy = read_button(0, debounce_time=0.3)
        return self.bi

    def get_connection_status(self) -> tuple[bool, str]:
        return True, 'joystick'
    
    def read_speed_knob(self) -> float:
        if pygame is None:
            return 0.0
        if not getattr(self, 'joystick', None):
            return 0.0
        try:
            pygame.event.pump()
        except Exception:
            return 0.0
        # Axis 3 controls overall max speed in UI (throttled updates)
        try:
            ax3 = -float(self.joystick.get_axis(3))
        except Exception:
            ax3 = 0.0
        norm = (ax3 + 1.0) / 2.0
        return norm
