import pygame
import sys

# Initialize pygame and joystick
pygame.init()
pygame.joystick.init()

# Check for joystick
if pygame.joystick.get_count() == 0:
    print("No joystick detected.")
    pygame.quit()
    sys.exit()

# Use the first joystick
joystick = pygame.joystick.Joystick(0)
joystick.init()
print(f"Joystick Name: {joystick.get_name()}")
print(f"Number of Axes: {joystick.get_numaxes()}")
print(f"Number of Buttons: {joystick.get_numbuttons()}")
print(f"Number of Hats: {joystick.get_numhats()}")

print("\nPress buttons or move sticks (Ctrl+C to quit)...\n")

# Main loop
try:
    while True:
        for event in pygame.event.get():
            if event.type == pygame.JOYBUTTONDOWN:
                print(f"Button {event.button} pressed")
            elif event.type == pygame.JOYBUTTONUP:
                print(f"Button {event.button} released")
            elif event.type == pygame.JOYAXISMOTION:
                print(f"Axis {event.axis} moved to {event.value:.3f}")
            elif event.type == pygame.JOYHATMOTION:
                print(f"Hat {event.hat} moved to {event.value}")
except KeyboardInterrupt:
    print("\nExiting...")
    pygame.quit()
    sys.exit()