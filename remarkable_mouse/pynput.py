import logging
import struct
import time
from screeninfo import get_monitors
from pynput.mouse import Button, Controller

MONITORS = get_monitors()

logging.basicConfig(format='%(message)s')
log = logging.getLogger('remouse')

# see https://github.com/canselcik/libremarkable/blob/master/src/input/ecodes.rs

# evtype_sync = 0
# evtype_key = 1
e_type_abs = 3

# evcode_stylus_distance = 25
# evcode_stylus_xtilt = 26
# evcode_stylus_ytilt = 27
e_code_stylus_xpos = 1
e_code_stylus_ypos = 0
e_code_stylus_pressure = 24

# wacom digitizer dimensions
wacom_width = 15725
wacom_height = 20967

# minimum seconds between checks of which monitor the cursor is on
MONITOR_CHECK_INTERVAL = 0.25

# remap wacom coordinates to screen coordinates
def remap(x, y, wacom_width, wacom_height, monitor_width,
          monitor_height, mode, orientation):

    if orientation == 'bottom':
        y = wacom_height - y
    elif orientation == 'right':
        x, y = wacom_height - y, wacom_width - x
        wacom_width, wacom_height = wacom_height, wacom_width
    elif orientation == 'left':
        x, y = y, x
        wacom_width, wacom_height = wacom_height, wacom_width
    elif orientation == 'top':
        x = wacom_width - x

    ratio_width, ratio_height = monitor_width / wacom_width, monitor_height / wacom_height

    if mode == 'fill':
        scaling = max(ratio_width, ratio_height)
    elif mode == 'fit':
        scaling = min(ratio_width, ratio_height)
    else:
        raise NotImplementedError

    return (
        scaling * (x - (wacom_width - monitor_width / scaling) / 2),
        scaling * (y - (wacom_height - monitor_height / scaling) / 2)
    )


def read_tablet(rm_inputs, *, orientation, monitor_idx, threshold, mode):
    """Loop forever and map evdev events to mouse

    Args:
        rm_inputs (dictionary of paramiko.ChannelFile): dict of pen and
            button input streams
        orientation (str): tablet orientation
        monitor (int): monitor number to map to
        threshold (int): pressure threshold
        mode (str): mapping mode
    """

    monitor = MONITORS[monitor_idx]
    log.debug('Chose monitor: {}'.format(monitor))

    handle_pen(rm_inputs, orientation, monitor, threshold, mode)


def get_current_monitor(mouse):
    """Find which monitor the cursor is currently on.

    Args:
        mouse (pynput.mouse.Controller): shared controller, reused rather than
            constructed here since creating one opens a new X11 connection
    """
    x, y = mouse.position
    for _monitor in MONITORS:
        if _monitor.x < x < _monitor.x + _monitor.width and _monitor.y < y < _monitor.y + _monitor.height:
            return _monitor


def handle_pen(rm_inputs, orientation, monitor, threshold, mode):
    mouse = Controller()
    lifted = True
    new_x = new_y = False
    last_monitor_check = 0

    while True:
        tv_sec, tv_usec, e_type, e_code, e_value = struct.unpack('2IHHi', rm_inputs['pen'].read(16))

        now = time.monotonic()
        if now - last_monitor_check > MONITOR_CHECK_INTERVAL:
            last_monitor_check = now
            _monitor = get_current_monitor(mouse)
            if _monitor and _monitor != monitor:
                monitor = _monitor

        if e_type == e_type_abs:
            # handle x direction
            if e_code == e_code_stylus_xpos:
                x = e_value
                new_x = True

            # handle y direction
            if e_code == e_code_stylus_ypos:
                y = e_value
                new_y = True

            # handle draw
            if e_code == e_code_stylus_pressure:
                if e_value > threshold:
                    if lifted:
                        log.debug('PRESS')
                        lifted = False
                        mouse.press(Button.left)
                else:
                    if not lifted:
                        log.debug('RELEASE')
                        lifted = True
                        mouse.release(Button.left)


            # only move when x and y are updated for smoother mouse
            if new_x and new_y:
                mapped_x, mapped_y = remap(
                    x, y,
                    wacom_width, wacom_height,
                    monitor.width, monitor.height,
                    mode, orientation
                )
                mouse.move(
                    monitor.x + mapped_x - mouse.position[0],
                    monitor.y + mapped_y - mouse.position[1]
                )
                new_x = new_y = False
