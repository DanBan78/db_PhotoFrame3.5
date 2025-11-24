# SPDX-License-Identifier: GPL-3.0-or-later
from typing import Iterator, Literal
import struct
from PIL import Image


def chunked(data: bytes, chunk_size: int) -> Iterator[bytes]:
    for i in range(0, len(data), chunk_size):
        yield data[i: i + chunk_size]


def image_to_RGB565(image: Image.Image, endianness: Literal["big", "little"]) -> bytes:
    """Convert PIL Image to RGB565 bytes with specified endianness."""
    if image.mode != 'RGB':
        image = image.convert('RGB')

    pixels = list(image.getdata())
    out = bytearray()
    
    for (r, g, b) in pixels:
        # Better scaling: multiply by max value then divide by 255
        r5 = (r * 31) // 255
        g6 = (g * 63) // 255  
        b5 = (b * 31) // 255
        
        value = (r5 << 11) | (g6 << 5) | b5
        
        if endianness == 'little':
            out.append(value & 0xFF)
            out.append((value >> 8) & 0xFF)
        else:
            out.append((value >> 8) & 0xFF)
            out.append(value & 0xFF)
            
    return bytes(out)


def image_to_BGR(image: Image.Image) -> (bytes, int):
    if image.mode not in ["RGB", "RGBA"]:
        # we need the first 3 channels to be R, G and B
        image = image.convert("RGB")
    
    # Get pixel data and convert RGB to BGR
    pixels = list(image.getdata())
    bgr_data = bytearray()
    
    for pixel in pixels:
        r, g, b = pixel[:3]
        bgr_data.extend([b, g, r])  # Reverse RGB to BGR
    
    return bytes(bgr_data), 3


def image_to_BGRA(image: Image.Image) -> (bytes, int):
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    
    # Get pixel data and convert RGBA to BGRA
    pixels = list(image.getdata())
    bgra_data = bytearray()
    
    for pixel in pixels:
        r, g, b, a = pixel
        bgra_data.extend([b, g, r, a])  # Reverse RGB to BGR, keep A
    
    return bytes(bgra_data), 4


# FIXME: to optimize like other functions above
def image_to_compressed_BGRA(image: Image.Image) -> (bytes, int):
    compressed_bgra = bytearray()
    image_data = image.convert("RGBA").load()
    for h in range(image.height):
        for w in range(image.width):
            # r = pixel[0], g = pixel[1], b = pixel[2], a = pixel[3]
            pixel = image_data[w, h]
            a = pixel[3] >> 4
            compressed_bgra.append(pixel[2] & 0xFC | a >> 2)
            compressed_bgra.append(pixel[1] & 0xFC | a & 2)
            compressed_bgra.append(pixel[0])
    return bytes(compressed_bgra), 3
