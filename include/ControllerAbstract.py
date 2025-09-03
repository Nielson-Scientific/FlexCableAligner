from abc import abstractmethod, ABC


class ButtonInventory():
    def __init__(self):
        self.toggle_fine = False
        self.toggle_carriages = False
        self.save_position = False
        self.goto_saved = False
        self.home_xy = False
        self.speed_dec = False
        self.speed_inc = False

class ControllerAbstract(ABC):
    @abstractmethod
    def __init__(self):
        pass

    @abstractmethod
    def shutdown(self):
        pass

    @abstractmethod
    def get_label(self) -> str:
        pass

    @abstractmethod
    def get_dir_and_feed(self) -> tuple[tuple[int, int, int], float]:
        pass

    @abstractmethod
    def get_button_states(self) -> ButtonInventory:
        pass

    @abstractmethod
    def get_connection_status(self) -> tuple[bool, str]:
        pass
