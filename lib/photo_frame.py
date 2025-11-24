# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python photo frame module
# https://github.com/mathoudebine/turing-smart-screen-python/
#
# Copyright (C) 2021 Matthieu Houdebine (mathoudebine)
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

"""
Photo Frame Module - Handles photo frame functionality including image scaling
and random image selection for smart displays
"""

import glob
import math
import os
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

from lib.log import logger

try:
    import psutil
except ImportError:
    psutil = None


class PhotoFrame:
    """
    Photo Frame manager for displaying images on smart displays
    """
    
    SUPPORTED_EXTENSIONS = ['*.png', '*.jpg', '*.jpeg', '*.bmp', '*.gif', '*.webp']
    
    def __init__(self):
        self.current_images = []
        self.current_index = 0
        self.use_random = False
        self.random_order = False
        
    def load_images_from_folder(self, folder_path: str) -> list:
        """
        Load all supported image files from a folder
        
        Args:
            folder_path: Path to folder containing images
            
        Returns:
            List of image file paths
        """
        if not os.path.isdir(folder_path):
            logger.error(f"Folder not found: {folder_path}")
            return []
        
        images = set()  # Use set to avoid duplicates
        # Use pathlib for case-insensitive matching on Windows
        from pathlib import Path
        folder = Path(folder_path)
        
        # Get all files and filter by extension (case-insensitive)
        for file_path in folder.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in [ext[1:] for ext in self.SUPPORTED_EXTENSIONS]:
                images.add(str(file_path))
        
        self.current_images = sorted(list(images))
        self.current_index = 0
        
        logger.info(f"Loaded {len(self.current_images)} images from {folder_path}")
        return self.current_images
    
    def scale_image_to_screen(self, image_path: str, screen_width: int, screen_height: int, 
                             maintain_aspect_ratio: bool = True, rotate_180: bool = False, orientation: str = 'Portrait') -> Image.Image:
        """
        Scale image to fit screen size while maintaining quality
        
        Args:
            image_path: Path to image file
            screen_width: Display width in pixels
            screen_height: Display height in pixels
            maintain_aspect_ratio: If True, maintain aspect ratio and add letterboxing
            
        Returns:
            PIL Image object scaled to screen size
        """
        try:
            image = Image.open(image_path)
            
            # Auto-correct EXIF orientation (fix rotated photos)
            try:
                from PIL.ExifTags import ORIENTATION
                exif = image._getexif()
                if exif is not None:
                    orientation = exif.get(0x0112)  # EXIF orientation tag
                    if orientation == 3:
                        image = image.rotate(180, expand=True)
                    elif orientation == 6:
                        image = image.rotate(270, expand=True)
                    elif orientation == 8:
                        image = image.rotate(90, expand=True)
            except Exception:
                # If EXIF reading fails, continue without rotation correction
                pass
            
            # Apply rotation based on orientation and rotate_180 parameter
            if orientation == 'Landscape':
                image = image.rotate(90, expand=True)  # Rotate 90° clockwise for landscape
            elif rotate_180:
                image = image.rotate(180, expand=True)
            
            original_width, original_height = image.size
            
            if maintain_aspect_ratio:
                # Calculate scaling factor to maintain aspect ratio
                width_scale = screen_width / original_width
                height_scale = screen_height / original_height
                scale_factor = min(width_scale, height_scale)
                
                new_width = int(original_width * scale_factor)
                new_height = int(original_height * scale_factor)
                
                # Resize image
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Create new image with screen dimensions and black background
                final_image = Image.new('RGB', (screen_width, screen_height), (0, 0, 0))
                
                # Calculate position to center the scaled image
                x_offset = (screen_width - new_width) // 2
                y_offset = (screen_height - new_height) // 2
                
                # Paste scaled image onto final image
                final_image.paste(image, (x_offset, y_offset))
                image = final_image
            else:
                # Simply stretch/crop to fit screen dimensions
                image = image.resize((screen_width, screen_height), Image.Resampling.LANCZOS)
            
            # Convert RGBA to RGB if necessary
            if image.mode == 'RGBA':
                rgb_image = Image.new('RGB', image.size, (0, 0, 0))
                rgb_image.paste(image, mask=image.split()[3])
                image = rgb_image
            elif image.mode != 'RGB':
                image = image.convert('RGB')
            
            return image
        except Exception as e:
            logger.error(f"Error scaling image {image_path}: {e}")
            return None
    
    def get_next_image(self, random_order: bool = False) -> str:
        """
        Get next image path
        
        Args:
            random_order: If True, return random image; if False, return next in sequence
            
        Returns:
            Path to next image or None if no images available
        """
        if not self.current_images:
            return None
        
        # Remember the random order setting for overlay
        self.use_random = random_order
        
        if random_order:
            image_path = random.choice(self.current_images)
        else:
            image_path = self.current_images[self.current_index % len(self.current_images)]
            self.current_index += 1
        
        return image_path
    
    def add_system_overlay(self, image: Image.Image, rotate_180: bool = False, orientation: str = 'Portrait') -> Image.Image:
        """
        Add system information overlay (CPU, RAM, temp, time) to image
        
        Args:
            image: PIL Image to add overlay to
            rotate_180: If True, position overlay for rotated image
            orientation: 'Portrait' or 'Landscape' - affects overlay rotation
            
        Returns:
            Image with overlay added
        """
        # Create a drawing context
        draw = ImageDraw.Draw(image)
        
        # Try to load font, fallback to default if not available
        try:
            font_path = "res/fonts/roboto-mono/RobotoMono-Regular.ttf"
            if os.path.exists(font_path):
                font = ImageFont.truetype(font_path, 14)
                font_small = ImageFont.truetype(font_path, 12)
            else:
                font = ImageFont.load_default()
                font_small = font
        except:
            font = ImageFont.load_default()
            font_small = font
        
        # Get system stats if psutil available
        cpu_percent = "N/A"
        ram_percent = "N/A"
        cpu_temp = "N/A"
        
        if psutil:
            try:
                cpu_percent = f"{psutil.cpu_percent(interval=0.1):.0f}%"
                ram_percent = f"{psutil.virtual_memory().percent:.0f}%"
                
                # Try to get CPU temperature using library.stats
                try:
                    import lib.stats as stats
                    temp_value = stats.sensors.Cpu.temperature()
                    if temp_value and temp_value > 0 and not math.isnan(temp_value):
                        cpu_temp = f"{temp_value:.0f}°C"
                except Exception as e:
                    logger.debug(f"Could not get CPU temperature: {e}")
            except:
                pass
        
        # Get current time
        current_time = datetime.now().strftime("%H:%M")
        
        # Get photo counter
        if self.use_random:
            photo_counter = f"{len(self.current_images)}"
        else:
            photo_counter = f"[{(self.current_index % len(self.current_images)) + 1}/{len(self.current_images)}]"
        
        # Create overlay - adjust dimensions based on orientation
        overlay_height = 28  # Consistent height
        
        # For landscape mode, overlay needs to be as wide as image height (since it will be rotated)
        if orientation == 'Landscape':
            overlay_width = image.height  # This will be the width after rotation
        else:
            overlay_width = image.width
            
        overlay = Image.new('RGBA', (overlay_width, overlay_height), (0, 0, 0, 180))
        overlay_draw = ImageDraw.Draw(overlay)
        
        # Draw system stats - layout: licznik z lewej, CPU/RAM środek, czas z prawej
        text_y = 9  # Text position
        
        # Licznik zdjęć z lewej
        overlay_draw.text((5, text_y), photo_counter, fill=(255, 255, 255), font=font)
        
        # CPU/RAM w środku
        center_text = f"CPU:{cpu_percent}  RAM:{ram_percent}"
        center_bbox = overlay_draw.textbbox((0, 0), center_text, font=font)
        center_width = center_bbox[2] - center_bbox[0]
        center_x = (overlay.width - center_width) // 2
        overlay_draw.text((center_x, text_y), center_text, fill=(255, 255, 255), font=font)
        
        # Czas z prawej
        time_bbox = overlay_draw.textbbox((0, 0), current_time, font=font)
        time_width = time_bbox[2] - time_bbox[0]
        time_x = overlay.width - time_width - 5
        overlay_draw.text((time_x, text_y), current_time, fill=(255, 255, 255), font=font)
        
        # Position overlay based on orientation
        if orientation == 'Landscape':
            # For landscape (90° rotated image), overlay goes on the "new bottom" 
            # which is actually the right side of the original image
            overlay_x_pos = image.width - overlay_height  # Use height as width offset
            overlay_y_pos = 0
            # Rotate overlay 90° to match image orientation
            overlay = overlay.rotate(90, expand=True)
        elif rotate_180:
            overlay = overlay.rotate(180)
            overlay_x_pos = 0
            overlay_y_pos = 0  # Top position (becomes bottom after image rotation)
        else:
            overlay_x_pos = 0
            overlay_y_pos = image.height - overlay_height  # Bottom position
        
        # Paste overlay onto image
        image_rgba = image.convert('RGBA')
        image_rgba.paste(overlay, (overlay_x_pos, overlay_y_pos), overlay)
        
        # Convert back to RGB
        image = image_rgba.convert('RGB')
        
        return image
    
    
    
    def display_image(self, lcd_comm, image_path: str, screen_width: int, screen_height: int,
                     maintain_aspect_ratio: bool = True, rotate_180: bool = False, orientation: str = 'Portrait'):
        """
        Scale and display image on LCD display
        """
        try:
            logger.debug(f"Starting display_image for: {image_path}")
            scaled_image = self.scale_image_to_screen(image_path, screen_width, screen_height, 
                                                     maintain_aspect_ratio, rotate_180, orientation)
            if scaled_image:
                logger.debug(f"Image scaled successfully to {scaled_image.size}")
                
                # Add system information overlay
                scaled_image = self.add_system_overlay(scaled_image, rotate_180, orientation)
                logger.debug(f"System overlay added")
                
                # Save scaled image with timestamp to bypass LCD cache
                import time
                timestamp = int(time.time() * 1000)
                temp_image_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                                              f"photo_frame_display_{timestamp}.jpg")
                logger.debug(f"Saving to: {temp_image_path}")
                scaled_image.save(temp_image_path, "JPEG", quality=95)
                logger.debug(f"Image saved, calling DisplayBitmap...")
                
                # Wait before sending to prevent "Too fast! Slow down!"
                time.sleep(0.8)  # Optimized delay to prevent warnings
                
                lcd_comm.DisplayBitmap(temp_image_path)
                
                # Additional delay after DisplayBitmap
                time.sleep(0.5)
                logger.debug(f"DisplayBitmap returned, image displayed: {image_path}")
                
                # Clean up old temp file
                try:
                    os.remove(temp_image_path)
                except:
                    pass
            else:
                logger.error(f"Failed to scale image: {image_path}")
        except Exception as e:
            logger.error(f"Error displaying image {image_path}: {e}")
            import traceback
            logger.error(traceback.format_exc())


# Global instance
photo_frame = PhotoFrame()
