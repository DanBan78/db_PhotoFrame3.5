"""
Simple LCD Display Controller for Turing Smart Screen 3.5" Rev A
Clean implementation without system monitor dependencies
"""

import os
import random
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
        self._last_clock_corner = None   # zeby zegar nie trafial dwa razy w ten sam rog

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

    def _build_clock_box(self, metrics, total_h, max_w, font, base_font_size, corner_radius):
        """Zbuduj prostokat zegara jako osobna warstwe RGBA (tekst poziomo)."""
        padding = 10
        box_w = max_w + 2 * padding
        box_h = total_h + 2 * padding

        box = Image.new('RGBA', (box_w, box_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(box)
        try:
            draw.rounded_rectangle((0, 0, box_w - 1, box_h - 1),
                                   radius=corner_radius, fill=OVERLAY_BACKGROUND_COLOR)
        except Exception:
            draw.rectangle((0, 0, box_w - 1, box_h - 1), fill=OVERLAY_BACKGROUND_COLOR)

        shadow_offset = max(1, int(base_font_size * SHADOW_OFFSET_MULTIPLIER)) \
            if isinstance(font, ImageFont.FreeTypeFont) else 1
        spacing = 4

        y = padding
        for txt, txt_w, txt_h in metrics:
            x = (box_w - txt_w) // 2
            draw.text((x + shadow_offset, y + shadow_offset), txt, font=font, fill=SHADOW_COLOR)
            draw.text((x, y), txt, font=font, fill=(220, 220, 220, 230))
            y += txt_h + spacing

        return box

    def _pick_clock_corner(self):
        """Wylosuj rog dla zegara, unikajac powtorzenia poprzedniego."""
        wybor = [c for c in CLOCK_CORNERS if c != self._last_clock_corner] or list(CLOCK_CORNERS)
        corner = random.choice(wybor)
        self._last_clock_corner = corner
        return corner

    def _add_text_overlay(self, image, show_time):
        """Nalóż zegar w losowo wybranym rogu ekranu."""
        img_w, img_h = image.size

        overlay_layer = Image.new('RGBA', (img_w, img_h), TRANSPARENT)
        measure = ImageDraw.Draw(overlay_layer)

        is_landscape = self.frame_orientation == ORIENTATION_LANDSCAPE
        font, base_font_size = self._create_overlay_font(img_w, img_h, is_landscape)
        texts = self._prepare_overlay_texts(show_time)
        if not texts:
            return image

        metrics, total_h, max_w = self._calculate_text_metrics(texts, font, measure)
        corner_radius = min(12, base_font_size // 2)
        box = self._build_clock_box(metrics, total_h, max_w, font, base_font_size, corner_radius)

        # Zdjecie zostalo juz obrocone pod fizyczny ekran - zegar musi przejsc
        # te same obroty, zeby patrzacy na ramke widzial go poziomo.
        rotation = 270 if is_landscape else 0
        if self.inverse:
            rotation = (rotation + 180) % 360
        if rotation:
            box = box.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)

        margin = int(max(MIN_OVERLAY_MARGIN, min(img_w, img_h) * MARGIN_MULTIPLIER))
        corner = self._pick_clock_corner()
        # Pudelko musi zmiescic sie w calosci - wczesniejszy kod liczyl prawa
        # krawedz jako 320-9+20=331 przy szerokosci 320 i zegar byl przyciety.
        x = margin if corner.endswith('left') else img_w - box.width - margin
        y = margin if corner.startswith('top') else img_h - box.height - margin
        x = max(0, min(x, img_w - box.width))
        y = max(0, min(y, img_h - box.height))

        overlay_layer.paste(box, (x, y), box)
        debug_print(f"zegar: rog {corner}, pozycja ({x},{y}), rozmiar {box.size}")

        try:
            base_img = image if image.mode == 'RGBA' else image.convert('RGBA')
            return Image.alpha_composite(base_img, overlay_layer).convert('RGB')
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