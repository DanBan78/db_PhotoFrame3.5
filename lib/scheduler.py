# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays like Turing Smart Screen or XuanFang
# https://github.com/mathoudebine/turing-smart-screen-python/
#
# Copyright (C) 2021 Matthieu Houdebine (mathoudebine)
# Copyright (C) 2022 Rollbacke
# Copyright (C) 2022 Ebag333
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import sched
import threading
import time
from datetime import timedelta
from functools import wraps

import lib.config as config
# stats import removed - not needed for photo frame mode
from lib.log import logger

STOPPING = False


def async_job(threadname=None):
    """ wrapper to handle asynchronous threads """

    def decorator(func):
        """ Decorator to extend async_func """

        @wraps(func)
        def async_func(*args, **kwargs):
            """ create an asynchronous function to wrap around our thread """
            func_hl = threading.Thread(target=func, name=threadname, args=args, kwargs=kwargs)
            func_hl.start()
            return func_hl

        return async_func

    return decorator


def schedule(interval):
    """ wrapper to schedule asynchronous threads """

    def decorator(func):
        """ Decorator to extend periodic """

        def periodic(scheduler, periodic_interval, action, actionargs=()):
            """ Wrap the scheduler with our periodic interval """
            if not STOPPING:
                # If the program is not stopping: re-schedule the task for future execution
                scheduler.enter(periodic_interval, 1, periodic,
                                (scheduler, periodic_interval, action, actionargs))
            action(*actionargs)

        @wraps(func)
        def wrap(
                *args,
                **kwargs
        ):
            """ Wrapper to create our schedule and run it at the appropriate time """
            if interval == 0:
                return
            scheduler = sched.scheduler(time.time, time.sleep)
            periodic(scheduler, interval, func)
            scheduler.run()

        return wrap

    return decorator


# System monitor functions removed - photo frame only application


@async_job("Picture_Frame")
@schedule(timedelta(seconds=config.CONFIG_DATA['config'].get('PHOTO_FRAME_INTERVAL', 5)).total_seconds())
def PictureFrame():
    from lib import display
    from lib.photo_frame import photo_frame

    # Initialize photo frame on first run or when orientation changes
    orientation = config.CONFIG_DATA['config'].get('PHOTO_FRAME_ORIENTATION', 'Portrait')
    
    if not hasattr(PictureFrame, 'initialized') or getattr(PictureFrame, 'last_orientation', None) != orientation:
        # Choose folder based on orientation
        if orientation == 'Portrait':
            photo_frame_folder = config.CONFIG_DATA['config'].get('PHOTO_FRAME_FOLDER_PORTRAIT', 
                                                                config.CONFIG_DATA['config'].get('PHOTO_FRAME_FOLDER', 'res/backgrounds'))
        else:  # Landscape
            photo_frame_folder = config.CONFIG_DATA['config'].get('PHOTO_FRAME_FOLDER_LANDSCAPE', 
                                                                config.CONFIG_DATA['config'].get('PHOTO_FRAME_FOLDER', 'res/backgrounds'))
        
        photo_frame.load_images_from_folder(photo_frame_folder)
        PictureFrame.initialized = True
        PictureFrame.last_orientation = orientation
        logger.info(f"Photo frame initialized for {orientation} orientation from folder: {photo_frame_folder}")

    if not photo_frame.current_images:
        logger.warning("No images found in photo frame folder")
        return

    # Get display dimensions
    screen_width = display.display.lcd.get_width()
    screen_height = display.display.lcd.get_height()
    
    # Check if random order is enabled
    use_random = config.CONFIG_DATA['config'].get('PHOTO_FRAME_RANDOM', False)
    
    # Get next image
    image_path = photo_frame.get_next_image(random_order=use_random)
    
    if image_path:
        maintain_aspect = config.CONFIG_DATA['config'].get('PHOTO_FRAME_MAINTAIN_ASPECT_RATIO', True)
        logger.debug(f"Displaying photo: {image_path}")
        try:
            # Use timeout to prevent blocking
            import threading
            
            def display_with_timeout():
                rotate_180 = config.CONFIG_DATA['config'].get('PHOTO_FRAME_INVERSE', False)
                photo_frame.display_image(display.display.lcd, image_path, screen_width, screen_height, 
                                         maintain_aspect_ratio=maintain_aspect, rotate_180=rotate_180, orientation=orientation)
            
            thread = threading.Thread(target=display_with_timeout, daemon=True)
            thread.start()
            thread.join(timeout=5.0)  # 5 second timeout
            
            if thread.is_alive():
                logger.warning(f"Display timeout for image: {image_path}")
            
            # Delay handled in photo_frame.display_image
        except Exception as e:
            logger.error(f"Error displaying image {image_path}: {e}")


@async_job("Queue_Handler")
@schedule(timedelta(milliseconds=1).total_seconds())
def QueueHandler():
    # Do next action waiting in the queue
    if STOPPING:
        # Empty the action queue to allow program to exit cleanly
        while not config.update_queue.empty():
            f, args = config.update_queue.get()
            f(*args)
    else:
        # Execute first action in the queue
        f, args = config.update_queue.get()
        if f:
            f(*args)


def is_queue_empty() -> bool:
    return config.update_queue.empty()
