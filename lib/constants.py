"""
Application constants for PhotoFrame
"""

# File and path constants
DEFAULT_CONFIG_PATH = "tools/config.yaml"
PORTRAIT_HISTORY_FILE = "tools/portrait_folders_history.txt"
LANDSCAPE_HISTORY_FILE = "tools/landscape_folders_history.txt"

# LCD Display constants
DEFAULT_LCD_WIDTH = 320
DEFAULT_LCD_HEIGHT = 480
DEFAULT_COM_PORT = "COM3"

# Display orientations
ORIENTATION_PORTRAIT = "Portrait"
ORIENTATION_LANDSCAPE = "Landscape"
VALID_ORIENTATIONS = [ORIENTATION_PORTRAIT, ORIENTATION_LANDSCAPE]

# Slideshow constants
MIN_SLIDESHOW_INTERVAL = 1
DEFAULT_SLIDESHOW_INTERVAL = 30
DEFAULT_SHUFFLE_ENABLED = True

# Image processing constants
TEMP_IMAGE_PREFIX = "temp_display_"
TEMP_BLACK_IMAGE = "temp_black.png"

# Font constants
DEFAULT_FONT_PATH = "res/fonts/roboto/Roboto-Bold.ttf"
MIN_FONT_SIZE = 16
FONT_SIZE_MULTIPLIER = 0.04
FONT_SIZE_BONUS = 11

# Overlay constants
MIN_OVERLAY_MARGIN = 8
MARGIN_MULTIPLIER = 0.02
OVERLAY_PADDING_MIN = 6
OVERLAY_NUDGE = 1
SHADOW_OFFSET_MULTIPLIER = 0.08

# Color constants (RGBA)
OVERLAY_BACKGROUND_COLOR = (0, 0, 0, 200)
TEXT_COLOR = (255, 255, 255, 255)
SHADOW_COLOR = (0, 0, 0, 200)
TRANSPARENT = (0, 0, 0, 0)

# Debug levels
DEBUG_LEVELS = ['debug', 'info', 'warning', 'error']
DEFAULT_DEBUG_LEVEL = 'info'

# Tray icon constants
TRAY_DOUBLE_CLICK_DELAY = 0.5  # seconds

# Configuration sections
CONFIG_SECTION_SLIDESHOW = 'slideshow'
CONFIG_SECTION_PHOTOS = 'photos'
CONFIG_SECTION_DISPLAY = 'display'
CONFIG_SECTION_CONFIG = 'config'
CONFIG_SECTION_DEBUG = 'debug'

# File extensions
SUPPORTED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff'}