import asyncio
import logging
from Adafruit_BBIO import GPIO

from boneio.helper.exceptions import GPIOInputException
from boneio.const import LOW, FALLING, Gpio_Edges, Gpio_States
from typing import Callable
import subprocess

from boneio.const import (
    CONFIG_PIN,
    GPIO as GPIO_STR,
    GPIO_MODE,
    ClickTypes,
)

_LOGGER = logging.getLogger(__name__)


def configure_pin(pin: str, mode: str = GPIO_STR) -> None:
    pin = f"{pin[0:3]}0{pin[3]}" if len(pin) == 4 else pin
    _LOGGER.debug(f"Configuring pin {pin} for mode {mode}.")
    subprocess.run(
        [CONFIG_PIN, pin, mode],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        timeout=1,
    )


def setup_output(pin: str) -> None:
    """Set up a GPIO as output."""

    GPIO.setup(pin, GPIO.OUT, pull_up_down=GPIO.PUD_DOWN)


def setup_input(pin: str, pull_mode: str = "UP") -> None:
    """Set up a GPIO as input."""
    try:
        GPIO.setup(pin, GPIO.IN, GPIO.PUD_DOWN if pull_mode == "DOWN" else GPIO.PUD_UP)
    except (ValueError, SystemError) as err:
        raise GPIOInputException(err)


def write_output(pin: str, value: str) -> None:
    """Write a value to a GPIO."""

    GPIO.output(pin, value)


def read_input(pin: str, on_state: Gpio_States = LOW) -> None:
    """Read a value from a GPIO."""
    return GPIO.input(pin) is on_state


def edge_detect(
    pin: str, callback: Callable, bounce: int = 0, edge: Gpio_Edges = FALLING
) -> None:
    """Add detection for RISING and FALLING events."""
    try:
        GPIO.add_event_detect(gpio=pin, edge=edge, callback=callback, bouncetime=bounce)
    except RuntimeError as err:
        raise GPIOInputException(err)


class GpioBaseClass:
    """Base class for initialize GPIO"""

    def __init__(
        self, pin: str, press_callback: Callable[[ClickTypes, str], None], **kwargs
    ) -> None:
        """Setup GPIO Input Button"""
        self._pin = pin
        gpio = kwargs.get("rest_pin", {GPIO_MODE: GPIO_STR})
        self._bounce_time = gpio.get("bounce_time", 25)
        configure_pin(pin=pin, mode=gpio.get(GPIO_MODE, GPIO_STR))
        self._loop = asyncio.get_running_loop()
        self._press_callback = press_callback
        setup_input(pin=self._pin)

    @property
    def is_pressed(self):
        """Is button pressed."""
        return read_input(self._pin)
