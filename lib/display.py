"""
Simple LCD Display Controller for Turing Smart Screen 3.5" Rev A
Clean implementation without system monitor dependencies
"""

import os
import time
import yaml
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from lib.lcd import lcd_comm_rev_a

# Import shared utilities
from .debug_utils import debug_print
from .constants import *

class LCDDisplay:
    def __init__(self, serial_port="COM3", brightness=85):
        self.serial_port = serial_port
        self.brightness = brightness
        # default physical screen size for portrait device
        self.width = DEFAULT_LCD_WIDTH
        self.height = DEFAULT_LCD_HEIGHT
        self.lcd = None
        # load photo-frame orientation settings from config.yaml if available
        # Prefer an external config file (next to the EXE or working directory)
        try:
            cfg = {}
            # Simplified config path: prefer package-relative tools/config.yaml (fixed location).
            # Fallback: current working directory if package-relative file not present.
            cfg_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools', 'config.yaml'))
            if not os.path.exists(cfg_path):
                cfg_path = os.path.abspath('tools/config.yaml')

            if cfg_path and os.path.exists(cfg_path):
                try:
                    with open(cfg_path, 'r', encoding='utf-8') as f:
                        cfg = yaml.safe_load(f) or {}
                    debug_print(f"Loaded config from: {cfg_path}")
                except (FileNotFoundError, yaml.YAMLError, PermissionError) as e:
                    debug_print(f"Failed to load config '{cfg_path}': {e}", 'error')
                except Exception as e:
                    debug_print(f"Unexpected error loading config '{cfg_path}': {e}", 'error')
                    cfg = {}
            else:
                cfg = {}

            # prefer photos.orientation (used by PhotoFrame) if present, otherwise fallback to config.PHOTO_FRAME_ORIENTATION
            photos_cfg = cfg.get('photos', {})
            config_cfg = cfg.get('config', {})
            orientation = photos_cfg.get('orientation') if photos_cfg.get('orientation') is not None else config_cfg.get('PHOTO_FRAME_ORIENTATION', 'Portrait')
            inverse = config_cfg.get('PHOTO_FRAME_INVERSE', False)
            # Normalize values
            orientation = str(orientation).capitalize()
            self.frame_orientation = orientation if orientation in ('Portrait', 'Landscape') else 'Portrait'
            self.inverse = bool(inverse)
        except Exception:
            self.frame_orientation = 'Portrait'
            self.inverse = False

        # Adjust width/height according to frame orientation
        if self.frame_orientation == 'Portrait':
            self.width, self.height = 320, 480
        else:
            self.width, self.height = 480, 320
        # Debug info
        debug_print(f"Display init => frame_orientation={self.frame_orientation}, inverse={self.inverse}, target={self.width}x{self.height}")
        
    def initialize(self):
        """Initialize LCD connection"""
        try:
            debug_print(f"Connecting to LCD on {self.serial_port}...")
            # Create rev A comm object and run its initialization handshake
            self.lcd = lcd_comm_rev_a.LcdCommRevA(self.serial_port)
            # Use the library's initialization method
            try:
                self.lcd.InitializeComm()
            except Exception:
                # Some variants may initialize in constructor; ignore if not available
                pass
            # Set brightness using provided API
            try:
                self.lcd.SetBrightness(self.brightness)
            except Exception:
                pass
            debug_print("LCD initialized successfully")
            return True
        except Exception as e:
            debug_print(f"Failed to initialize LCD: {e}", 'error')
            return False
    
    def display_image(self, image_path):
        """Display image on LCD screen"""
        if not self.lcd:
            debug_print("LCD not initialized", 'error')
            return False
            
        try:
            # Load and prepare image for display (rotate/resize according to orientation and inverse)
            image = Image.open(image_path)
            image = self._prepare_image_for_display(image)
            
            # Ensure image matches the LCD's expected size before sending.
            try:
                try:
                    if self.lcd and hasattr(self.lcd, 'get_width') and hasattr(self.lcd, 'get_height'):
                        lcd_w, lcd_h = self.lcd.get_width(), self.lcd.get_height()
                    else:
                        lcd_w, lcd_h = self.width, self.height
                except Exception:
                    lcd_w, lcd_h = self.width, self.height
                if image.size != (lcd_w, lcd_h):
                    debug_print(f"display_image: resizing image from {image.size} to LCD target {(lcd_w,lcd_h)} before send")
                    image = image.resize((lcd_w, lcd_h), Image.Resampling.LANCZOS)
                self.lcd.DisplayPILImage(image, 0, 0, image.size[0], image.size[1])
            except Exception:
                # Fallback: try DisplayBitmap with a temporary file
                temp_path = f"temp_display_{int(time.time())}.png"
                image.save(temp_path)
                try:
                    self.lcd.DisplayBitmap(str(temp_path), 0, 0)
                finally:
                    try:
                        os.remove(temp_path)
                    except:
                        pass
            return True
        except Exception as e:
            debug_print(f"Error displaying image {image_path}: {e}", 'error')
            return False
    
    def _create_overlay_font(self, img_w, img_h):
        """Create font for overlay text"""
        try:
            # Increase font size for better readability
            base_font_size = max(MIN_FONT_SIZE, int(min(img_w, img_h) * FONT_SIZE_MULTIPLIER)) + FONT_SIZE_BONUS
            return ImageFont.truetype(DEFAULT_FONT_PATH, base_font_size), base_font_size
        except Exception:
            # Default font does not accept size param; keep default
            return ImageFont.load_default(), MIN_FONT_SIZE
    
    def _prepare_overlay_texts(self, show_time, show_date):
        """Prepare text content for overlay"""
        texts = []
        if show_time:
            current_time = time.strftime("%H:%M")
            texts.append(current_time)
        # Date functionality removed per user request
        return texts
    
    def _calculate_text_metrics(self, texts, font, draw):
        """Calculate text dimensions and layout metrics"""
        metrics = []
        total_h = 0
        max_w = 0
        spacing = 4  # Simple fixed spacing
        
        for txt in reversed(texts):
            bbox = draw.textbbox((0, 0), txt, font=font)
            txt_w = bbox[2] - bbox[0]
            txt_h = bbox[3] - bbox[1]
            metrics.append((txt, txt_w, txt_h))
            total_h += txt_h + spacing
            if txt_w > max_w:
                max_w = txt_w
        
        if total_h > 0:
            total_h -= spacing
        
        return metrics, total_h, max_w
    
    def _create_landscape_overlay(self, overlay_layer, metrics, total_h, max_w, 
                                  font, base_font_size, corner_radius, img_h, overlay_nudge):
        """Create overlay for landscape orientation"""
        padding = max(6, base_font_size // 3) + 6
        box_w = max_w + padding * 2
        box_h = total_h + padding * 2
        
        # Create small RGBA box for overlay
        box_layer = Image.new('RGBA', (box_w, box_h), (0, 0, 0, 0))
        draw_box = ImageDraw.Draw(box_layer)
        
        # Draw rounded rectangle background
        try:
            draw_box.rounded_rectangle((0, 0, box_w, box_h), radius=corner_radius, fill=(0, 0, 0, 200))
        except Exception:
            draw_box.rectangle((0, 0, box_w, box_h), fill=(0, 0, 0, 200))
        
        # Draw text with shadow
        yb = box_h - padding
        shadow_offset = max(1, int(base_font_size * 0.08)) if isinstance(font, ImageFont.FreeTypeFont) else 1
        spacing = 4
        
        for txt, txt_w, txt_h in metrics:
            xb = (box_w - txt_w) // 2
            # Shadow
            draw_box.text((xb + shadow_offset, yb - txt_h + shadow_offset), txt, 
                         font=font, fill=(0, 0, 0, 200))
            # Text
            draw_box.text((xb, yb - txt_h), txt, font=font, fill=(255, 255, 255, 255))
            yb -= (txt_h + spacing)
        
        # Rotate and position
        try:
            rotated_box = box_layer.rotate(270, expand=True, resample=Image.Resampling.BICUBIC)
        except Exception:
            rotated_box = box_layer
        
        pos_x = 0
        pos_y = max(0, img_h - rotated_box.height - overlay_nudge)
        overlay_layer.paste(rotated_box, (pos_x, pos_y), rotated_box)
    
    def _create_portrait_overlay(self, draw, metrics, total_h, max_w, 
                                font, base_font_size, corner_radius, img_w, img_h, margin, overlay_nudge):
        """Create overlay for portrait orientation"""
        padding = max(6, base_font_size // 3) + 6
        
        # Calculate rectangle bounds
        rect_right = img_w - margin + padding
        rect_left = img_w - margin - max_w - padding
        rect_bottom = img_h - margin + padding - overlay_nudge
        rect_top = rect_bottom - total_h - padding
        
        # Draw background rectangle
        try:
            draw.rounded_rectangle((rect_left, rect_top, rect_right, rect_bottom), 
                                 radius=corner_radius, fill=(0, 0, 0, 200))
        except Exception:
            draw.rectangle((rect_left, rect_top, rect_right, rect_bottom), fill=(0, 0, 0, 200))
        
        # Draw text with shadow
        y = rect_bottom - padding
        shadow_offset = max(1, int(base_font_size * 0.08)) if isinstance(font, ImageFont.FreeTypeFont) else 1
        spacing = 4
        
        for txt, txt_w, txt_h in metrics:
            x = img_w - margin - txt_w
            # Shadow
            draw.text((x + shadow_offset, y - txt_h + shadow_offset), txt, 
                     font=font, fill=(0, 0, 0, 200))
            # Text
            draw.text((x, y - txt_h), txt, font=font, fill=(255, 255, 255, 255))
            y -= (txt_h + spacing)
    
    def _send_image_to_lcd(self, image):
        """Send final image to LCD display"""
        try:
            debug_print(f"display_image_with_overlay: final image size before send {image.size}, mode={image.mode}")
            
            # Ensure correct size for LCD
            try:
                if self.lcd and hasattr(self.lcd, 'get_width') and hasattr(self.lcd, 'get_height'):
                    lcd_w, lcd_h = self.lcd.get_width(), self.lcd.get_height()
                else:
                    lcd_w, lcd_h = self.width, self.height
            except Exception:
                lcd_w, lcd_h = self.width, self.height
            
            if image.size != (lcd_w, lcd_h):
                debug_print(f"display_image_with_overlay: resizing from {image.size} to {(lcd_w, lcd_h)}")
                image = image.resize((lcd_w, lcd_h), Image.Resampling.LANCZOS)
            
            if self.lcd:
                self.lcd.DisplayPILImage(image, 0, 0, image.size[0], image.size[1])
            return True
        except Exception:
            # Fallback to bitmap display
            return self._fallback_bitmap_display(image)
    
    def _fallback_bitmap_display(self, image):
        """Fallback display method using temporary bitmap file"""
        if not self.lcd:
            debug_print("No LCD connection available for fallback display", 'error')
            return False
            
        temp_path = f"{TEMP_IMAGE_PREFIX}{int(time.time())}.png"
        try:
            image.save(temp_path)
            debug_print("display_image_with_overlay: DisplayPILImage failed, using DisplayBitmap fallback")
            self.lcd.DisplayBitmap(str(temp_path), 0, 0)
            return True
        except Exception as e:
            debug_print(f"Error in bitmap fallback: {e}", 'error')
            return False
        finally:
            try:
                os.remove(temp_path)
            except (FileNotFoundError, PermissionError, OSError) as e:
                debug_print(f"Could not remove temp file: {e}", 'debug')

    def display_image_with_overlay(self, image_path, show_time=True, show_date=True):
        """Display image with time/date overlay"""
        if not self.lcd:
            return False
            
        try:
            # Load and prepare image
            image = Image.open(image_path)
            image = self._prepare_image_for_display(image)
            
            # Ensure correct size before overlay
            try:
                if self.lcd and hasattr(self.lcd, 'get_width') and hasattr(self.lcd, 'get_height'):
                    lcd_w, lcd_h = self.lcd.get_width(), self.lcd.get_height()
                else:
                    lcd_w, lcd_h = self.width, self.height
            except Exception:
                lcd_w, lcd_h = self.width, self.height
            
            if image.size != (lcd_w, lcd_h):
                debug_print(f"display_image_with_overlay: resizing image from {image.size} to LCD target {(lcd_w,lcd_h)} before overlay")
                image = image.resize((lcd_w, lcd_h), Image.Resampling.LANCZOS)
            
            # Add overlay if requested
            if show_time or show_date:
                image = self._add_text_overlay(image, show_time, show_date)
            
            # Send to LCD
            return self._send_image_to_lcd(image)
            
        except Exception as e:
            debug_print(f"Error displaying image with overlay: {e}", 'error')
            return False
    
    def _add_text_overlay(self, image, show_time, show_date):
        """Add text overlay to image"""
        img_w, img_h = image.size
        
        # Create overlay layer
        overlay_layer = Image.new('RGBA', (img_w, img_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay_layer)
        
        # Prepare font and text
        font, base_font_size = self._create_overlay_font(img_w, img_h)
        texts = self._prepare_overlay_texts(show_time, show_date)
        
        if not texts:
            return image
        
        # Calculate layout metrics
        metrics, total_h, max_w = self._calculate_text_metrics(texts, font, draw)
        margin = int(max(8, min(img_w, img_h) * 0.02))
        corner_radius = min(12, base_font_size // 2)
        overlay_nudge = 1
        
        # Create overlay based on orientation
        if getattr(self, 'frame_orientation', 'Portrait') == 'Landscape':
            self._create_landscape_overlay(overlay_layer, metrics, total_h, max_w, 
                                         font, base_font_size, corner_radius, img_h, overlay_nudge)
        else:
            self._create_portrait_overlay(draw, metrics, total_h, max_w, 
                                        font, base_font_size, corner_radius, img_w, img_h, margin, overlay_nudge)
        
        # Composite overlay onto image
        try:
            if image.mode != 'RGBA':
                base_img = image.convert('RGBA')
            else:
                base_img = image
            
            composed = Image.alpha_composite(base_img, overlay_layer)
            return composed.convert('RGB')
        except Exception as e:
            debug_print(f"display_image_with_overlay: compositing overlay failed: {e}", 'error')
            return image
    
    def clear_screen(self):
        """Clear LCD screen"""
        if self.lcd:
            try:
                # Create black image
                black_image = Image.new('RGB', (self.width, self.height), (0, 0, 0))
                try:
                    self.lcd.DisplayPILImage(black_image, 0, 0, black_image.size[0], black_image.size[1])
                except Exception:
                    tmp = TEMP_BLACK_IMAGE
                    black_image.save(tmp)
                    try:
                        self.lcd.DisplayBitmap(tmp, 0, 0)
                    finally:
                        try:
                            os.remove(tmp)
                        except Exception as e:
                            debug_print(f"Could not remove temp file: {e}", 'debug')
            except Exception as e:
                debug_print(f"Error clearing screen: {e}", 'error')

    def apply_config(self, cfg: dict):
        """Apply configuration at runtime (update orientation and inverse)."""
        try:
            photos_cfg = cfg.get('photos', {}) if isinstance(cfg, dict) else {}
            config_cfg = cfg.get('config', {}) if isinstance(cfg, dict) else {}
            orientation = photos_cfg.get('orientation') if photos_cfg.get('orientation') is not None else config_cfg.get('PHOTO_FRAME_ORIENTATION', 'Portrait')
            inverse = config_cfg.get('PHOTO_FRAME_INVERSE', False)
            orientation = str(orientation).capitalize()
            self.frame_orientation = orientation if orientation in ('Portrait', 'Landscape') else 'Portrait'
            self.inverse = bool(inverse)
            # Adjust width/height according to frame orientation
            if self.frame_orientation == ORIENTATION_PORTRAIT:
                self.width, self.height = DEFAULT_LCD_WIDTH, DEFAULT_LCD_HEIGHT
            else:
                self.width, self.height = DEFAULT_LCD_HEIGHT, DEFAULT_LCD_WIDTH
            debug_print(f"LCDDisplay.apply_config => frame_orientation={self.frame_orientation}, inverse={self.inverse}, target={self.width}x{self.height}")
        except Exception as e:
            debug_print(f"apply_config error: {e}", 'error')

    def _prepare_image_for_display(self, image: Image.Image) -> Image.Image:
        """Rotate and resize image according to configured frame orientation and inverse flag.

        Steps:
        - If target orientation is Portrait and image is landscape -> rotate 90deg
        - If target orientation is Landscape -> rotate 90deg (always) to match physical wiring
        - Resize to (self.width, self.height)
        - If inverse flag set -> rotate 180deg (final flip)
        """
        try:
            img = image
            # Log source size before any transforms (rotation/resize)
            try:
                debug_print(f"_prepare_image_for_display: source size before transforms {img.size}")
            except Exception:
                pass
            # Determine target size explicitly
            if self.frame_orientation == 'Landscape':
                target_w, target_h = 480, 320
            else:
                target_w, target_h = 320, 480

            # Decide whether we need to rotate source image to match target
            rotate_degrees = 0
            # Use fixed 90° rotation when the source orientation doesn't match target
            if self.frame_orientation == 'Portrait':
                if img.width > img.height:
                    rotate_degrees = 90
            else:
                # For Landscape frames, rotate 270° (equivalent to -90°)
                # so landscape-folder images are oriented correctly on the display.
                rotate_degrees = 270

            if rotate_degrees:
                try:
                    debug_print(f"_prepare_image_for_display: rotating {rotate_degrees}deg to match frame")
                    img = img.rotate(rotate_degrees, expand=True)
                except Exception as e:
                    debug_print(f"_prepare_image_for_display: rotation failed: {e}", 'error')

            # For Landscape mode we want the image scaled to full portrait target (320x480)
            # so that landscape-folder images appear the same as portrait ones.
            try:
                if self.frame_orientation == 'Landscape':
                    debug_print(f"_prepare_image_for_display: force-resizing to {target_w}x{target_h} for landscape display")
                    final = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
                    # Apply 180deg flip if device is inverted (after composing)
                    if getattr(self, 'inverse', False):
                        debug_print("_prepare_image_for_display: applying 180deg inverse flip")
                        final = final.rotate(180)
                    debug_print(f"_prepare_image_for_display: final size {final.size}")
                    return final

                # Fit image into target while preserving aspect ratio and center it (portrait/default)
                src_w, src_h = img.size
                scale = min(target_w / src_w, target_h / src_h)
                new_w = max(1, int(src_w * scale))
                new_h = max(1, int(src_h * scale))
                debug_print(f"_prepare_image_for_display: resizing from {src_w}x{src_h} to {new_w}x{new_h} (target {target_w}x{target_h})")
                img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

                # Create final canvas and paste centered
                final = Image.new('RGB', (target_w, target_h), (0, 0, 0))
                offset_x = (target_w - new_w) // 2
                offset_y = (target_h - new_h) // 2
                final.paste(img_resized, (offset_x, offset_y))

                # Apply 180deg flip if device is inverted (after composing)
                if getattr(self, 'inverse', False):
                    debug_print("_prepare_image_for_display: applying 180deg inverse flip")
                    final = final.rotate(180)

                debug_print(f"_prepare_image_for_display: final size {final.size}, pasted at ({offset_x},{offset_y})")
                return final
            except Exception as e:
                debug_print(f"_prepare_image_for_display: error during resize/compose: {e}", 'error')
                # Fallback: simple resize to target
                try:
                    fallback = image.resize((target_w, target_h), Image.Resampling.LANCZOS)
                    if getattr(self, 'inverse', False):
                        fallback = fallback.rotate(180)
                    return fallback
                except Exception:
                    return image
        except Exception:
            # On error, fallback to a safe resize without rotations
            try:
                return image.resize((self.width, self.height), Image.Resampling.LANCZOS)
            except Exception:
                return image
    
    def close(self):
        """Close LCD connection"""
        self.clear_screen()
        if self.lcd:
            try:
                # Use closeSerial if available to close the underlying serial port
                try:
                    self.lcd.closeSerial()
                except Exception:
                    # closeSerial failed, LCD may already be closed
                    debug_print("closeSerial method not available or failed", 'debug')
                debug_print("LCD connection closed")
            except Exception as e:
                debug_print(f"Error during LCD cleanup: {e}", 'error')