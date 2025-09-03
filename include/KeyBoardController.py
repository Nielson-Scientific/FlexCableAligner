from ControllerAbstract import ButtonInventory, ControllerAbstract

class KeyBoardController(ControllerAbstract):
    def __init__(self):
        self.bi = ButtonInventory()
        

    def get_label(self) -> str:
        return "Keyboard Controller"

    def shutdown(self):
        pass

    def get_dir_and_feed(self) -> tuple[tuple[int, int, int], float]:
        return (0, 0, 0), 1.0

    def get_button_states(self) -> ButtonInventory:
        return self.bi

    def get_connection_status(self) -> tuple[bool, str]:
        return True, 'keyboard'

