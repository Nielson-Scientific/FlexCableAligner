"""
Controller Debug Utility

Run this script to print the state of all axes, buttons, and hats on the
first detected game controller using pygame. Useful for mapping controls.

Usage:
  python helper.py [poll_hz]

Example:
  python helper.py 20   # 20 updates per second
"""

from __future__ import annotations

import sys
import time
from typing import List, Tuple

import pygame


def clear_screen():
	# ANSI clear; works on most terminals
	sys.stdout.write("\x1b[2J\x1b[H")
	sys.stdout.flush()


def format_list(prefix: str, values: List, fmt: str = "{:.3f}") -> str:
	parts = [f"{i}:{(fmt.format(v) if isinstance(v, float) else v)}" for i, v in enumerate(values)]
	return f"{prefix} (count={len(values)}): [" + ", ".join(parts) + "]"


def main():
	poll_hz = 10.0
	if len(sys.argv) > 1:
		try:
			poll_hz = float(sys.argv[1])
		except ValueError:
			print("Invalid poll_hz; using default 10 Hz")
	interval = 1.0 / max(1e-3, poll_hz)

	pygame.init()
	pygame.joystick.init()
	try:
		count = pygame.joystick.get_count()
		if count == 0:
			print("No joystick detected. Connect a controller and try again.")
			return 1

		js = pygame.joystick.Joystick(0)
		js.init()

		name = js.get_name()
		axes_n = js.get_numaxes()
		buttons_n = js.get_numbuttons()
		hats_n = js.get_numhats()

		print(f"Using controller: {name}")
		print(f"Axes: {axes_n}, Buttons: {buttons_n}, Hats: {hats_n}")
		print("Press Ctrl+C to exit.\n")
		time.sleep(0.8)

		while True:
			pygame.event.pump()

			axes = [float(js.get_axis(i)) for i in range(axes_n)]
			buttons = [int(js.get_button(i)) for i in range(buttons_n)]
			hats: List[Tuple[int, int]] = [js.get_hat(i) for i in range(hats_n)]

			clear_screen()
			print(f"Controller: {name}")
			print(f"Polling: {poll_hz:.1f} Hz\n")

			print(format_list("Axes", axes))
			print(format_list("Buttons", buttons, fmt="{}"))
			if hats_n:
				# hats are tuples; show as ix:(x,y)
				hat_str = ", ".join([f"{i}:{hats[i]}" for i in range(len(hats))])
				print(f"Hats (count={hats_n}): [" + hat_str + "]")

			# Guidance to help mapping
			print("\nTip: Press one button at a time and observe which index changes to 1.")
			print("     Move each stick and observe which axis indices change.")

			time.sleep(interval)
	except KeyboardInterrupt:
		print("\nExiting...")
	finally:
		try:
			js.quit()  # type: ignore[name-defined]
		except Exception:
			pass
		pygame.joystick.quit()
		pygame.quit()
	return 0


if __name__ == "__main__":
	raise SystemExit(main())

