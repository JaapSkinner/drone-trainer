import pygame

# read from the xbox 1 controller sticks and print the values
pygame.init()
pygame.joystick.init()
controller = pygame.joystick.Joystick(0)
controller.init()

while True:
    for event in pygame.event.get():
        if event.type == pygame.JOYAXISMOTION:
            print("Left Stick X: ", controller.get_axis(0))
            print("Left Stick Y: ", controller.get_axis(1))
            print("Right Stick X: ", controller.get_axis(3))
            print("Right Stick Y: ", controller.get_axis(4))
        if event.type == pygame.JOYBUTTONDOWN:
            print("Button Pressed: ", event.button)
        if event.type == pygame.JOYBUTTONUP:
            print("Button Released: ", event.button)
        if event.type == pygame.JOYHATMOTION:
            print("D-Pad: ", controller.get_hat(0))
        
pygame.quit()