from utils.AutoFocus import Autofocus

HIGH = 11
LOW = 10
BROAD_STEP = 0.1
FINE_STEP = 0.01
FINER_STEP = 0.001


if __name__ == "__main__":
    Autofocus.fast_autofocus(HIGH, LOW, BROAD_STEP, FINE_STEP, finer_pass_step=FINER_STEP)