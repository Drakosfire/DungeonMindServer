"""
Map Compositing Module

Composites base map image with grid overlay and text labels into a single flattened image.
Uses Pillow for server-side image processing.
"""

import logging
import io
from typing import List
from PIL import Image, ImageDraw, ImageFont
from mapgenerator.models import GridConfig, MapLabel
import math
import os

logger = logging.getLogger(__name__)

# Font directory path
FONT_DIR = os.path.join(os.path.dirname(__file__), '..', 'static', 'fonts')


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert hex color string to RGB tuple"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def calculate_square_grid_lines(
    width: int,
    height: int,
    cell_size: int,
    offset_x: int,
    offset_y: int
) -> List[tuple[int, int, int, int]]:
    """
    Calculate square grid line segments.
    
    Returns list of (x1, y1, x2, y2) tuples.
    """
    lines = []
    
    if cell_size <= 0:
        return lines
    
    # Calculate starting positions
    start_x = ((offset_x % cell_size) + cell_size) % cell_size
    start_y = ((offset_y % cell_size) + cell_size) % cell_size
    
    # Generate vertical lines
    for x in range(int(start_x), width + 1, cell_size):
        lines.append((x, 0, x, height))
    
    # Generate horizontal lines
    for y in range(int(start_y), height + 1, cell_size):
        lines.append((0, y, width, y))
    
    return lines


def calculate_hex_grid_lines(
    width: int,
    height: int,
    cell_size: int,
    offset_x: int,
    offset_y: int
) -> List[tuple[int, int, int, int]]:
    """
    Calculate hex grid line segments (pointy-top orientation).
    
    Returns list of (x1, y1, x2, y2) tuples.
    """
    lines = []
    
    if cell_size <= 0:
        return lines
    
    # Pointy-top hex dimensions
    hex_width = math.sqrt(3) * cell_size
    hex_height = 2 * cell_size
    vert_dist = hex_height * 0.75
    
    # Calculate coverage area
    cols = int(math.ceil(width / hex_width)) + 2
    rows = int(math.ceil(height / vert_dist)) + 2
    
    # Starting offsets
    start_col = int(math.floor(-offset_x / hex_width)) - 1
    start_row = int(math.floor(-offset_y / vert_dist)) - 1
    
    # Track drawn edges to avoid duplicates
    drawn_edges = set()
    
    for row in range(start_row, start_row + rows):
        for col in range(start_col, start_col + cols):
            # Calculate center position
            center_x = col * hex_width + offset_x
            center_y = row * vert_dist + offset_y
            
            # Offset odd rows for pointy-top
            if row % 2 != 0:
                center_x += hex_width / 2
            
            # Get hex corners (6 corners for pointy-top)
            corners = []
            for i in range(6):
                angle_deg = 60 * i - 30
                angle_rad = math.radians(angle_deg)
                corners.append((
                    int(center_x + cell_size * math.cos(angle_rad)),
                    int(center_y + cell_size * math.sin(angle_rad))
                ))
            
            # Add edges (6 edges per hex)
            for i in range(6):
                start = corners[i]
                end = corners[(i + 1) % 6]
                
                # Create unique key for edge (order-independent)
                x1, y1 = start
                x2, y2 = end
                edge_key = (
                    min(x1, x2), min(y1, y2),
                    max(x1, x2), max(y1, y2)
                )
                
                # Skip if edge already drawn
                if edge_key in drawn_edges:
                    continue
                drawn_edges.add(edge_key)
                
                # Only add lines that are at least partially visible
                min_x = min(x1, x2)
                max_x = max(x1, x2)
                min_y = min(y1, y2)
                max_y = max(y1, y2)
                
                if max_x >= 0 and min_x <= width and max_y >= 0 and min_y <= height:
                    lines.append((x1, y1, x2, y2))
    
    return lines


def load_font(font_family: str, font_size: int) -> ImageFont.FreeTypeFont:
    """
    Load a font file for text rendering.
    
    Args:
        font_family: Font family name
        font_size: Font size in pixels
        
    Returns:
        PIL ImageFont object
    """
    # Map font family names to font file names
    font_file_map = {
        'MedievalSharp': 'MedievalSharp-Regular.ttf',
        'Pirata One': 'PirataOne-Regular.ttf',
        'Uncial Antiqua': 'UncialAntiqua-Regular.ttf',
        'Cinzel': 'Cinzel-Regular.ttf',
        'IM Fell English': 'IMFellEnglish-Regular.ttf',
    }
    
    font_file = font_file_map.get(font_family, 'MedievalSharp-Regular.ttf')
    font_path = os.path.join(FONT_DIR, font_file)
    
    try:
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, font_size)
        else:
            logger.warning(f"Font file not found: {font_path}, using default")
            return ImageFont.load_default()
    except Exception as e:
        logger.warning(f"Failed to load font {font_path}: {e}, using default")
        return ImageFont.load_default()


def composite_map_export(
    base_image_bytes: bytes,
    grid_config: GridConfig,
    labels: List[MapLabel],
    width: int,
    height: int
) -> Image.Image:
    """
    Composite a map export by combining base image, grid overlay, and labels.
    
    Args:
        base_image_bytes: Base map image as bytes (PNG/JPEG)
        grid_config: Grid overlay configuration
        labels: List of text labels to render
        width: Image width in pixels
        height: Image height in pixels
        
    Returns:
        Composited PIL Image
    """
    # Load base image from bytes
    base_image = Image.open(io.BytesIO(base_image_bytes))
    
    # Ensure image is in RGB mode (convert RGBA to RGB if needed)
    if base_image.mode == 'RGBA':
        # Create white background
        rgb_image = Image.new('RGB', base_image.size, (255, 255, 255))
        rgb_image.paste(base_image, mask=base_image.split()[3])  # Use alpha channel as mask
        base_image = rgb_image
    elif base_image.mode != 'RGB':
        base_image = base_image.convert('RGB')
    
    # Resize if dimensions don't match
    if base_image.size != (width, height):
        base_image = base_image.resize((width, height), Image.Resampling.LANCZOS)
    
    # Create a copy for compositing
    composite = base_image.copy()
    draw = ImageDraw.Draw(composite)
    
    # Draw grid overlay if visible
    if grid_config.visible:
        grid_color = hex_to_rgb(grid_config.color)
        
        if grid_config.type == 'square':
            grid_lines = calculate_square_grid_lines(
                width, height,
                grid_config.cell_size_px,
                grid_config.offset_x,
                grid_config.offset_y
            )
        else:  # hex
            grid_lines = calculate_hex_grid_lines(
                width, height,
                grid_config.cell_size_px,
                grid_config.offset_x,
                grid_config.offset_y
            )
        
        # Create overlay layer for grid with opacity support
        overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        
        # Draw grid lines on overlay with opacity
        alpha = int(255 * grid_config.opacity)
        for line in grid_lines:
            x1, y1, x2, y2 = line
            overlay_draw.line(
                [(x1, y1), (x2, y2)],
                fill=(*grid_color, alpha),
                width=1
            )
        
        # Composite grid overlay onto base image
        composite = Image.alpha_composite(
            composite.convert('RGBA'),
            overlay
        ).convert('RGB')
        draw = ImageDraw.Draw(composite)
    
    # Draw text labels
    for label in labels:
        try:
            # Load font
            font = load_font(label.font_family, label.font_size)
            
            # Get text color
            text_color = hex_to_rgb(label.color)
            
            # Get text size using textbbox
            # Create a temporary image and draw context to measure text
            temp_img = Image.new('RGB', (1, 1))
            temp_draw = ImageDraw.Draw(temp_img)
            try:
                bbox = temp_draw.textbbox((0, 0), label.text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
            except AttributeError:
                # Fallback for older Pillow versions
                text_width, text_height = temp_draw.textsize(label.text, font=font)
            
            # Create text image (larger to accommodate rotation)
            # Use diagonal of text size + some padding
            text_size = int(math.sqrt(text_width**2 + text_height**2)) + 40
            text_img = Image.new('RGBA', (text_size, text_size), (0, 0, 0, 0))
            text_draw = ImageDraw.Draw(text_img)
            
            # Draw text centered in text image
            text_x = (text_size - text_width) // 2
            text_y = (text_size - text_height) // 2
            
            # Draw stroke/outline first if configured
            stroke_width = getattr(label, 'stroke_width', None) or 0
            stroke_color_hex = getattr(label, 'stroke_color', None)
            
            if stroke_width > 0 and stroke_color_hex:
                stroke_color = hex_to_rgb(stroke_color_hex)
                # Pillow 10+ supports stroke directly
                try:
                    text_draw.text(
                        (text_x, text_y),
                        label.text,
                        fill=(*text_color, 255),
                        font=font,
                        stroke_width=int(stroke_width),
                        stroke_fill=(*stroke_color, 255)
                    )
                except TypeError:
                    # Fallback for older Pillow: draw text multiple times offset for stroke effect
                    offsets = [(-1, -1), (-1, 1), (1, -1), (1, 1), (-1, 0), (1, 0), (0, -1), (0, 1)]
                    for i in range(int(stroke_width)):
                        for ox, oy in offsets:
                            text_draw.text(
                                (text_x + ox * (i + 1), text_y + oy * (i + 1)),
                                label.text,
                                fill=(*stroke_color, 255),
                                font=font
                            )
                    # Draw fill on top
                    text_draw.text(
                        (text_x, text_y),
                        label.text,
                        fill=(*text_color, 255),
                        font=font
                    )
            else:
                # No stroke, just draw text
                text_draw.text(
                    (text_x, text_y),
                    label.text,
                    fill=(*text_color, 255),
                    font=font
                )
            
            # Rotate if needed (around center of text image)
            if label.rotation != 0:
                text_img = text_img.rotate(
                    -label.rotation,  # Negative because Pillow rotates counter-clockwise
                    center=(text_size // 2, text_size // 2),
                    expand=False
                )
            
            # Calculate position to paste text (label position is top-left of text)
            paste_x = int(label.x - text_size // 2)
            paste_y = int(label.y - text_size // 2)
            
            # Create a full-size transparent layer to hold the text
            text_layer = Image.new('RGBA', (width, height), (0, 0, 0, 0))
            
            # Paste the text image onto the layer at the correct position
            # Use text_img as both image and mask for proper alpha handling
            text_layer.paste(text_img, (paste_x, paste_y), text_img)
            
            # Composite text layer onto main image
            composite = Image.alpha_composite(
                composite.convert('RGBA'),
                text_layer
            ).convert('RGB')
            draw = ImageDraw.Draw(composite)
            
        except Exception as e:
            logger.error(f"Failed to render label {label.id}: {e}")
            continue
    
    return composite
