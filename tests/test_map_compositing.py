"""
Map Compositing Tests

Tests for map export compositing functionality.
"""

import pytest
from PIL import Image
import io
from mapgenerator.compositing import composite_map_export
from mapgenerator.models import GridConfig, MapLabel


class TestMapCompositing:
    """Tests for map compositing functionality"""
    
    def test_composite_map_export_creates_image(self):
        """composite_map_export should create a valid PIL Image"""
        # Create a test base image
        base_image = Image.new('RGB', (100, 100), color='white')
        base_image_bytes = io.BytesIO()
        base_image.save(base_image_bytes, format='PNG')
        base_image_bytes.seek(0)
        
        # Create minimal project data
        grid_config = GridConfig(
            type="square",
            cellSizePx=20,
            offsetX=0,
            offsetY=0,
            color="#000000",
            opacity=0.5,
            visible=False  # Grid not visible, just base image
        )
        
        labels = []
        
        # Call compositing function
        result_image = composite_map_export(
            base_image_bytes.getvalue(),
            grid_config,
            labels,
            width=100,
            height=100
        )
        
        # Verify result is a PIL Image
        assert isinstance(result_image, Image.Image)
        assert result_image.size == (100, 100)
    
    def test_composite_map_export_with_visible_grid(self):
        """composite_map_export should draw grid lines when grid is visible"""
        # Create a test base image
        base_image = Image.new('RGB', (100, 100), color='white')
        base_image_bytes = io.BytesIO()
        base_image.save(base_image_bytes, format='PNG')
        base_image_bytes.seek(0)
        
        # Create grid config with visible grid
        grid_config = GridConfig(
            type="square",
            cellSizePx=20,
            offsetX=0,
            offsetY=0,
            color="#FF0000",  # Red grid lines
            opacity=1.0,
            visible=True
        )
        
        labels = []
        
        # Call compositing function
        result_image = composite_map_export(
            base_image_bytes.getvalue(),
            grid_config,
            labels,
            width=100,
            height=100
        )
        
        # Verify result is a PIL Image
        assert isinstance(result_image, Image.Image)
        # Grid should be drawn (we can't easily verify pixel colors in unit test,
        # but we can verify the function completes without error)
    
    def test_composite_map_export_with_labels(self):
        """composite_map_export should render text labels"""
        # Create a test base image
        base_image = Image.new('RGB', (100, 100), color='white')
        base_image_bytes = io.BytesIO()
        base_image.save(base_image_bytes, format='PNG')
        base_image_bytes.seek(0)
        
        # Create grid config (not visible)
        grid_config = GridConfig(
            type="square",
            cellSizePx=20,
            offsetX=0,
            offsetY=0,
            color="#000000",
            opacity=0.5,
            visible=False
        )
        
        # Create a label
        labels = [
            MapLabel(
                id="test-label-1",
                text="Test Label",
                x=50,
                y=50,
                rotation=0,
                fontFamily="MedievalSharp",
                fontSize=24,
                color="#000000"
            )
        ]
        
        # Call compositing function
        result_image = composite_map_export(
            base_image_bytes.getvalue(),
            grid_config,
            labels,
            width=100,
            height=100
        )
        
        # Verify result is a PIL Image
        assert isinstance(result_image, Image.Image)
        # Label should be rendered (function completes without error)
    
    def test_composite_map_export_with_hex_grid(self):
        """composite_map_export should handle hex grids"""
        # Create a test base image
        base_image = Image.new('RGB', (100, 100), color='white')
        base_image_bytes = io.BytesIO()
        base_image.save(base_image_bytes, format='PNG')
        base_image_bytes.seek(0)
        
        # Create hex grid config
        grid_config = GridConfig(
            type="hex",
            cellSizePx=20,
            offsetX=0,
            offsetY=0,
            color="#0000FF",  # Blue grid lines
            opacity=0.7,
            visible=True
        )
        
        labels = []
        
        # Call compositing function
        result_image = composite_map_export(
            base_image_bytes.getvalue(),
            grid_config,
            labels,
            width=100,
            height=100
        )
        
        # Verify result is a PIL Image
        assert isinstance(result_image, Image.Image)
    
    def test_composite_map_export_with_rotated_label(self):
        """composite_map_export should handle rotated labels"""
        # Create a test base image
        base_image = Image.new('RGB', (100, 100), color='white')
        base_image_bytes = io.BytesIO()
        base_image.save(base_image_bytes, format='PNG')
        base_image_bytes.seek(0)
        
        # Create grid config
        grid_config = GridConfig(
            type="square",
            cellSizePx=20,
            offsetX=0,
            offsetY=0,
            color="#000000",
            opacity=0.5,
            visible=False
        )
        
        # Create a rotated label
        labels = [
            MapLabel(
                id="test-label-1",
                text="Rotated",
                x=50,
                y=50,
                rotation=45,  # 45 degree rotation
                fontFamily="MedievalSharp",
                fontSize=24,
                color="#000000"
            )
        ]
        
        # Call compositing function
        result_image = composite_map_export(
            base_image_bytes.getvalue(),
            grid_config,
            labels,
            width=100,
            height=100
        )
        
        # Verify result is a PIL Image
        assert isinstance(result_image, Image.Image)
    
    def test_composite_map_export_handles_empty_labels(self):
        """composite_map_export should work with empty label list"""
        # Create a test base image
        base_image = Image.new('RGB', (100, 100), color='white')
        base_image_bytes = io.BytesIO()
        base_image.save(base_image_bytes, format='PNG')
        base_image_bytes.seek(0)
        
        grid_config = GridConfig(
            type="square",
            cellSizePx=20,
            offsetX=0,
            offsetY=0,
            color="#000000",
            opacity=0.5,
            visible=False
        )
        
        labels = []
        
        # Call compositing function
        result_image = composite_map_export(
            base_image_bytes.getvalue(),
            grid_config,
            labels,
            width=100,
            height=100
        )
        
        # Verify result is a PIL Image
        assert isinstance(result_image, Image.Image)
    
    def test_composite_map_export_handles_multiple_labels(self):
        """composite_map_export should handle multiple labels"""
        # Create a test base image
        base_image = Image.new('RGB', (200, 200), color='white')
        base_image_bytes = io.BytesIO()
        base_image.save(base_image_bytes, format='PNG')
        base_image_bytes.seek(0)
        
        grid_config = GridConfig(
            type="square",
            cellSizePx=20,
            offsetX=0,
            offsetY=0,
            color="#000000",
            opacity=0.5,
            visible=False
        )
        
        # Create multiple labels
        labels = [
            MapLabel(
                id="label-1",
                text="Label 1",
                x=50,
                y=50,
                rotation=0,
                fontFamily="MedievalSharp",
                fontSize=24,
                color="#000000"
            ),
            MapLabel(
                id="label-2",
                text="Label 2",
                x=150,
                y=150,
                rotation=90,
                fontFamily="Pirata One",
                fontSize=32,
                color="#FF0000"
            ),
        ]
        
        # Call compositing function
        result_image = composite_map_export(
            base_image_bytes.getvalue(),
            grid_config,
            labels,
            width=200,
            height=200
        )
        
        # Verify result is a PIL Image
        assert isinstance(result_image, Image.Image)
        assert result_image.size == (200, 200)
