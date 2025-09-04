from ControllerAbstract import ButtonInventory, ControllerAbstract
from threading import Lock
from pynput import keyboard

class KeyBoardController(ControllerAbstract):
    def __init__(self, invert_z: bool=True, z_speed_scale: float=0.33):
        self.invert_z = invert_z
        self.z_speed_scale = z_speed_scale

        self._pressed_keys = set()
        self._keys_lock = Lock()
        self._listener = None
        self._start_keyboard_listener

        self.bi = ButtonInventory()

        
        
    def get_label(self) -> str:
        return "Keyboard Controller"

    def shutdown(self):
        pass

    def get_dir_and_feed(self) -> tuple[tuple[int, int, int], float]:
        # Parse pressed keys
        with self._keys_lock:
            pressed = set(self._pressed_keys)
        dx = 0
        dy = 0
        dz = 0
        # planar
        if 'left' in pressed:
            dx -= 1
        if 'right' in pressed:
            dx += 1
        if 'down' in pressed:
            dy -= 1
        if 'up' in pressed:
            dy += 1
        if 'pagedown' in pressed:
            dz -= 1
        if 'pageup' in pressed:
            dz += 1
        
        #constrain function
        def constrain(val):
            return int(max(-1, min(1, val)))

        # Z/C slower
        if dz != 0:
            feed *= float(self.z_speed_scale)
        return (constrain(dx), constrain(dy), constrain(dz)), 1

    def get_button_states(self) -> ButtonInventory:
        with self._keys_lock:
            self.bi.toggle_fine = 'f' in self._pressed_keys
            self.bi.toggle_carriages = 'space' in self._pressed_keys
            self.bi.save_position = 's' in self._pressed_keys
            self.bi.goto_saved = 'g' in self._pressed_keys
            self.bi.home_xy = 'h' in self._pressed_keys
            self.speed_dec = '-' in self._pressed_keys
            self.speed_inc = '+' in self._pressed_keys
        return self.bi

    def get_connection_status(self) -> tuple[bool, str]:
        return True, 'keyboard'
    
    def _start_keyboard_listener(self):
        if self._listener:
            return
        self._listener = keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release)
        self._listener.start()

    def _key_to_token(self, key) -> str | None:
        try:
            if isinstance(key, keyboard.Key):
                special = {
                    keyboard.Key.left: 'left',
                    keyboard.Key.right: 'right',
                    keyboard.Key.up: 'up',
                    keyboard.Key.down: 'down',
                    keyboard.Key.space: 'space',
                    keyboard.Key.esc: 'esc',
                }
                return special.get(key)
            if isinstance(key, keyboard.KeyCode):
                if key.char is None:
                    return None
                return key.char.lower()
        except Exception:
            return None
        return None

    def _on_key_press(self, key):
        token = self._key_to_token(key)
        if token is None:
            return
        first_press = False
        with self._keys_lock:
            if token not in self._pressed_keys:
                self._pressed_keys.add(token)
                first_press = True
            self._recompute_target_vel_locked()
        if first_press and token in self._action_bindings:
            name, args = self._action_bindings[token]
            self._enqueue_action(name, *args)

    def _on_key_release(self, key):
        token = self._key_to_token(key)
        if token is None:
            return
        with self._keys_lock:
            if token in self._pressed_keys:
                self._pressed_keys.remove(token)
            self._recompute_target_vel_locked()
