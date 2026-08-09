"""
Simple LCD Display Controller for Turing Smart Screen 3.5" Rev A
Clean implementation without system monitor dependencies
"""

import os
import time
from PIL import Image, ImageDraw, ImageFont
from lib.lcd import lcd_comm_rev_a

# Import shared utilities
from .debug_utils import debug_print
from .config_manager import config_manager, settings
from .constants import *

class LCDDisplay:
    def __init__(self, serial_port=None, brightness=None):
        """Argumenty nadpisuja wartosci z konfiguracji (przydatne w testach)."""
        # default physical screen size for portrait device
        self.width = DEFAULT_LCD_WIDTH
        self.height = DEFAULT_LCD_HEIGHT
        self.lcd = None
        self.frame_orientation = ORIENTATION_PORTRAIT
        self.inverse = False
        self.scale_mode = 'fit'

        cfg = settings(config_manager.load_config())
        self.serial_port = serial_port or cfg['com_port'] or DEFAULT_COM_PORT
        try:
            self.brightness = int(brightness if brightness is not None else cfg['brightness'])
        except (TypeError, ValueError):
            self.brightness = 85

        self.apply_config(config_manager.load_config())
        debug_print(f"Display init => port={self.serial_port}, brightness={self.brightness}, "
                    f"frame_orientation={self.frame_orientation}, inverse={self.inverse}, "
                    f"scale_mode={self.scale_mode}, target={self.width}x{self.height}")
        
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
    
    def _create_overlay_font(self, img_w, img_h, is_landscape=True):
        """Create font for overlay text"""
        # Użyj domyślnej czcionki systemowej PIL zamiast TTF
        # PIL domyślna czcionka zawsze działa i ma stały rozmiar
        base_font_size = 24 if is_landscape else 24  # Zmniejszone o połowę (było 60/80)
        
        # Zamiast TTF użyj prostej czcionki PIL
        try:
            # Spróbuj Arial Bold lub inną systemową
            font_path = "C:\\Windows\\Fonts\\arialbd.ttf"  # Pogrubiona wersja
            return ImageFont.truetype(font_path, base_font_size), base_font_size
        except:
            try:
                # Fallback - Arial zwykły
                font_path = "C:\\Windows\\Fonts\\arial.ttf"
                return ImageFont.truetype(font_path, base_font_size), base_font_size
            except:
                # Ostateczny fallback
                return ImageFont.load_default(), base_font_size
    
    def _prepare_overlay_texts(self, show_time):
        """Prepare text content for overlay"""
        texts = []
        if show_time:
            texts.append(time.strftime("%H:%M"))
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
        # Stałe wymiary dla landscape (480x320)
        padding = 20
        box_w = 70   # Zmniejszone o 50% (było 140)
        box_h = 36   # Zmniejszone o 60% (było 90) 
        
        # Create small RGBA box for overlay
        box_layer = Image.new('RGBA', (box_w, box_h), (0, 0, 0, 0))
        draw_box = ImageDraw.Draw(box_layer)
        
        # Draw rounded rectangle background
        try:
            draw_box.rounded_rectangle((0, 0, box_w, box_h), radius=corner_radius, fill=(0, 0, 0, 200))
        except Exception:
            draw_box.rectangle((0, 0, box_w, box_h), fill=(0, 0, 0, 200))
        
        # Draw text with shadow
        yb = box_h - padding + 4  # Podniesienie o 3 piksele w górę
        shadow_offset = max(1, int(base_font_size * 0.08)) if isinstance(font, ImageFont.FreeTypeFont) else 1
        spacing = 4
        
        for txt, txt_w, txt_h in metrics:
            xb = (box_w - txt_w) // 2
            # Shadow
            draw_box.text((xb + shadow_offset, yb - txt_h + shadow_offset), txt, 
                         font=font, fill=(0, 0, 0, 200))
            # Text - lekko szary z przezroczystością
            draw_box.text((xb, yb - txt_h), txt, font=font, fill=(220, 220, 220, 230))
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
        # Stałe wymiary dla portrait (320x480)
        padding = 20
        box_w = 90   # Zmniejszone o 50% (było 180)
        box_h = 44   # Zmniejszone o 60% (było 110)
        
        # Calculate rectangle bounds
        rect_right = img_w - margin + padding
        rect_left = rect_right - box_w
        rect_bottom = img_h - margin + padding - overlay_nudge
        rect_top = rect_bottom - box_h
        
        # Draw background rectangle
        try:
            draw.rounded_rectangle((rect_left, rect_top, rect_right, rect_bottom), 
                                 radius=corner_radius, fill=(0, 0, 0, 200))
        except Exception:
            draw.rectangle((rect_left, rect_top, rect_right, rect_bottom), fill=(0, 0, 0, 200))
        
        # Draw text with shadow
        y = rect_bottom - padding - 3  # Podniesienie o 3 piksele w górę
        shadow_offset = max(1, int(base_font_size * 0.08)) if isinstance(font, ImageFont.FreeTypeFont) else 1
        spacing = 4
        
        for txt, txt_w, txt_h in metrics:
            x = img_w - margin - txt_w
            # Shadow
            draw.text((x + shadow_offset, y - txt_h + shadow_offset), txt, 
                     font=font, fill=(0, 0, 0, 200))
            # Text - lekko szary z przezroczystością
            draw.text((x, y - txt_h), txt, font=font, fill=(220, 220, 220, 230))
            y -= (txt_h + spacing)
    
    def _send_image_to_lcd(self, image, with_overlay=False):
        """Send final image to LCD display
        
        Args:
            image: PIL Image to send
            with_overlay: Whether this image includes overlay (for logging)
        """
        try:
            overlay_text = " (with overlay)" if with_overlay else ""
            debug_print(f"display_image_with_overlay: sending {image.size} image{overlay_text}, mode={image.mode}")
            
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

    def display_image_with_overlay(self, image_path, show_time=True):
        """Display image with optional clock overlay"""
        if not self.lcd:
            return False

        try:
            # _prepare_image_for_display zwraca juz obraz w rozmiarze fizycznego
            # ekranu, wiec nie ma tu ponownego skalowania (ktore wczesniej
            # znieksztalcalo kadr w trybie poziomym).
            image = Image.open(image_path)
            image = self._prepare_image_for_display(image)

            if show_time:
                image = self._add_text_overlay(image, show_time)
                return self._send_image_to_lcd(image, with_overlay=True)
            return self._send_image_to_lcd(image, with_overlay=False)

        except Exception as e:
            debug_print(f"Error displaying image with overlay: {e}", 'error')
            return False

    def _add_text_overlay(self, image, show_time):
        """Add text overlay to image"""
        img_w, img_h = image.size
        
        # Create overlay layer
        overlay_layer = Image.new('RGBA', (img_w, img_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay_layer)
        
        # Check orientation first
        is_landscape = getattr(self, 'frame_orientation', 'Portrait') == 'Landscape'
        
        # Prepare font and text
        font, base_font_size = self._create_overlay_font(img_w, img_h, is_landscape)
        texts = self._prepare_overlay_texts(show_time)
        
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
        """Apply configuration at runtime (orientation, inverse, scale mode)."""
        try:
            values = settings(cfg)
            self.frame_orientation = (ORIENTATION_PORTRAIT if values['orientation_portrait']
                                      else ORIENTATION_LANDSCAPE)
            self.inverse = bool(values['inverse'])
            self.scale_mode = values['scale_mode']
            # Adjust width/height according to frame orientation
            if self.frame_orientation == ORIENTATION_PORTRAIT:
                self.width, self.height = DEFAULT_LCD_WIDTH, DEFAULT_LCD_HEIGHT
            else:
                self.width, self.height = DEFAULT_LCD_HEIGHT, DEFAULT_LCD_WIDTH
            debug_print(f"LCDDisplay.apply_config => frame_orientation={self.frame_orientation}, "
                        f"inverse={self.inverse}, scale_mode={self.scale_mode}, "
                        f"target={self.width}x{self.height}")
        except Exception as e:
            debug_print(f"apply_config error: {e}", 'error')

    def _scale_to_canvas(self, img: Image.Image, target_w: int, target_h: int) -> Image.Image:
        """Wpasuj obraz w plotno target_w x target_h wedlug scale_mode.

        fit  - cale zdjecie widoczne, reszta plotna zostaje czarna (letterbox)
        fill - zdjecie pokrywa cale plotno, nadmiar jest przyciety

        Proporcje sa zachowane w obu trybach - zdjecie nigdy nie jest rozciagane.
        """
        src_w, src_h = img.size
        if src_w <= 0 or src_h <= 0:
            return img

        if self.scale_mode == 'fill':
            scale = max(target_w / src_w, target_h / src_h)
        else:
            scale = min(target_w / src_w, target_h / src_h)

        new_w = max(1, round(src_w * scale))
        new_h = max(1, round(src_h * scale))
        resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        canvas = Image.new('RGB', (target_w, target_h), (0, 0, 0))
        offset_x = (target_w - new_w) // 2
        offset_y = (target_h - new_h) // 2
        # Przy 'fill' offsety sa ujemne - PIL sam przycina to, co wychodzi poza plotno
        canvas.paste(resized, (offset_x, offset_y))
        debug_print(f"_scale_to_canvas: {src_w}x{src_h} -> {new_w}x{new_h} "
                    f"({self.scale_mode}) na {target_w}x{target_h}, offset ({offset_x},{offset_y})")
        return canvas

    def _prepare_image_for_display(self, image: Image.Image) -> Image.Image:
        """Obroc i przeskaluj zdjecie pod fizyczny ekran.

        Ekran jest fizycznie pionowy (320x480). Tryb poziomy uzyskujemy obracajac
        obraz o 270 stopni, wiec plotno kompozycji ma wtedy wymiary 480x320,
        a dopiero gotowa kompozycja jest obracana. Dzieki temu oba tryby uzywaja
        tej samej logiki skalowania i zdjecie nigdzie nie jest rozciagane.
        """
        try:
            img = image
            debug_print(f"_prepare_image_for_display: source size before transforms {img.size}")

            landscape = self.frame_orientation == ORIENTATION_LANDSCAPE
            if landscape:
                canvas_w, canvas_h = DEFAULT_LCD_HEIGHT, DEFAULT_LCD_WIDTH   # 480x320
            else:
                canvas_w, canvas_h = DEFAULT_LCD_WIDTH, DEFAULT_LCD_HEIGHT   # 320x480
                # Zdjecie poziome w ramce pionowej obracamy, zeby wykorzystac ekran
                if img.width > img.height:
                    debug_print("_prepare_image_for_display: rotating 90deg to match portrait frame")
                    img = img.rotate(90, expand=True)

            final = self._scale_to_canvas(img, canvas_w, canvas_h)

            if landscape:
                # Kompozycja 480x320 -> fizyczne 320x480
                final = final.rotate(270, expand=True)

            if self.inverse:
                debug_print("_prepare_image_for_display: applying 180deg inverse flip")
                final = final.rotate(180)

            debug_print(f"_prepare_image_for_display: final size {final.size}")
            return final
        except Exception as e:
            debug_print(f"_prepare_image_for_display: error: {e}", 'error')
            # Awaryjnie: proste dopasowanie do fizycznego rozmiaru ekranu
            try:
                return image.resize((DEFAULT_LCD_WIDTH, DEFAULT_LCD_HEIGHT),
                                    Image.Resampling.LANCZOS)
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