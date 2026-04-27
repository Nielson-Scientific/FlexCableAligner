from utils.AutoFocus import Autofocus

HIGH = 11
LOW = 10
STEP_SIZE = 0.05


if __name__ == "__main__":
    Autofocus.autofocus(HIGH, LOW, STEP_SIZE, show_plot = True)