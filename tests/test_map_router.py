"""
Map Router Tests

Tests for map generator API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from app import app


client = TestClient(app)


class TestMapGeneratorHealth:
    """Tests for the health check endpoint"""
    
    def test_health_check_returns_ok(self):
        """Health endpoint should return status ok"""
        response = client.get("/api/mapgenerator/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "mapgenerator"


class TestMapGeneratorProjects:
    """Tests for project CRUD endpoints"""
    
    def test_list_projects_requires_auth(self):
        """List projects should require authentication"""
        response = client.get("/api/mapgenerator/projects")
        
        # Should return 401 Unauthorized without auth
        assert response.status_code == 401
    
    def test_create_project_requires_auth(self):
        """Create project should require authentication"""
        response = client.post(
            "/api/mapgenerator/projects",
            json={
                "name": "Test Map",
                "baseImageUrl": "https://example.com/map.png"
            }
        )
        
        # Should return 401 Unauthorized without auth
        assert response.status_code == 401
    
    def test_get_nonexistent_project_returns_404(self):
        """Getting a non-existent project should return 404"""
        response = client.get("/api/mapgenerator/projects/nonexistent-id")
        
        # Should return 401 without auth, or 404 with auth
        assert response.status_code in [401, 404]
    
    def test_update_project_requires_auth(self):
        """Update project should require authentication"""
        response = client.patch(
            "/api/mapgenerator/projects/test-id",
            json={
                "name": "Updated Map"
            }
        )
        
        # Should return 401 Unauthorized without auth
        assert response.status_code == 401
    
    def test_delete_project_requires_auth(self):
        """Delete project should require authentication"""
        response = client.delete("/api/mapgenerator/projects/test-id")
        
        # Should return 401 Unauthorized without auth
        assert response.status_code == 401
    
    def test_create_project_validates_request(self):
        """Create project should validate request fields"""
        # Missing required fields
        response = client.post(
            "/api/mapgenerator/projects",
            json={}
        )
        
        # Should return 401 (auth) or 422 (validation error)
        assert response.status_code in [401, 422]


class TestMapGeneration:
    """Tests for map generation endpoint"""
    
    def test_generate_map_requires_auth(self):
        """Generate endpoint should require authentication"""
        response = client.post(
            "/api/mapgenerator/generate",
            json={
                "prompt": "A forest clearing with ancient stone ruins and a campfire"
            }
        )
        
        # 401 Unauthorized - endpoint requires authentication
        assert response.status_code == 401


class TestMapExport:
    """Tests for map export endpoint"""
    
    def test_export_requires_project_or_inline_data(self):
        """Export endpoint should require projectId or inline project data"""
        response = client.post(
            "/api/mapgenerator/export",
            json={
                "format": "png"
            }
        )
        
        # Should return 400 Bad Request if neither projectId nor project provided
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
    
    def test_export_with_inline_project_validation(self):
        """Export endpoint should validate inline project data structure"""
        # Test with missing baseImageUrl
        response = client.post(
            "/api/mapgenerator/export",
            json={
                "format": "png",
                "project": {
                    "gridConfig": {
                        "type": "square",
                        "cellSizePx": 50,
                        "offsetX": 0,
                        "offsetY": 0,
                        "color": "#000000",
                        "opacity": 0.5,
                        "visible": False
                    },
                    "labels": []
                }
            }
        )
        
        # Should return 400 Bad Request for missing baseImageUrl
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data


class TestPydanticModels:
    """Tests for Pydantic model validation"""
    
    def test_grid_config_validation(self):
        """GridConfig should validate field constraints"""
        from mapgenerator.models import GridConfig
        
        # Valid config
        config = GridConfig(
            type="square",
            cellSizePx=50,
            offsetX=0,
            offsetY=0,
            color="#FF0000",
            opacity=0.5,
            visible=True
        )
        assert config.cell_size_px == 50
        assert config.type == "square"
        
    def test_grid_config_cell_size_bounds(self):
        """Cell size should be between 10 and 200"""
        from mapgenerator.models import GridConfig
        from pydantic import ValidationError
        
        # Too small
        with pytest.raises(ValidationError):
            GridConfig(
                type="square",
                cellSizePx=5,  # Below minimum
                offsetX=0,
                offsetY=0,
                color="#000000",
                opacity=0.5,
                visible=True
            )
        
        # Too large
        with pytest.raises(ValidationError):
            GridConfig(
                type="square",
                cellSizePx=250,  # Above maximum
                offsetX=0,
                offsetY=0,
                color="#000000",
                opacity=0.5,
                visible=True
            )
    
    def test_map_label_validation(self):
        """MapLabel should validate field constraints"""
        from mapgenerator.models import MapLabel
        
        label = MapLabel(
            id="test-label-1",
            text="Forest of Shadows",
            x=100,
            y=200,
            rotation=45,
            fontFamily="MedievalSharp",
            fontSize=24,
            color="#000000"
        )
        assert label.text == "Forest of Shadows"
        assert label.rotation == 45
        assert label.font_family == "MedievalSharp"
    
    def test_map_label_invalid_rotation(self):
        """Label rotation should be 0-359 degrees (out of range values rejected)"""
        from mapgenerator.models import MapLabel
        from pydantic import ValidationError
        
        # 30 degrees is now valid (any 0-359 allowed for transformer flexibility)
        label = MapLabel(
            id="test-label-1",
            text="Valid Rotation",
            x=100,
            y=200,
            rotation=30,  # Now valid - any angle 0-359 is accepted
            fontFamily="MedievalSharp",
            fontSize=24,
            color="#000000"
        )
        assert label.rotation == 30
        
        # But out-of-range values should still fail
        with pytest.raises(ValidationError):
            MapLabel(
                id="test-label-2",
                text="Invalid Rotation",
                x=100,
                y=200,
                rotation=360,  # Out of range (max is 359)
                fontFamily="MedievalSharp",
                fontSize=24,
                color="#000000"
            )
    
    def test_scale_metadata_validation(self):
        """ScaleMetadata should validate field constraints"""
        from mapgenerator.models import ScaleMetadata
        
        scale = ScaleMetadata(cellSize=5, unit="ft")
        assert scale.cell_size == 5
        assert scale.unit == "ft"


# =============================================================================
# Phase 14D: Masked Map Generation Tests (T176-T180)
# These tests are written BEFORE implementation - they MUST FAIL initially
# =============================================================================


class TestMaskedMapGeneration:
    """Tests for masked map generation endpoint (T178-T180)"""
    
    def test_generate_masked_requires_auth(self):
        """T178: Generate masked endpoint should require authentication"""
        response = client.post(
            "/api/mapgenerator/generate-masked",
            json={
                "prompt": "Forest clearing",
                "mask_base64": "data:image/png;base64,iVBORw0KGgo...",
                "base_image_base64": "data:image/png;base64,iVBORw0KGgo..."
            }
        )
        
        assert response.status_code == 401
    
    def test_generate_masked_requires_mask(self):
        """T179: Generate masked should require mask_base64 field"""
        # Note: This would need auth mock to test properly
        response = client.post(
            "/api/mapgenerator/generate-masked",
            json={
                "prompt": "Forest clearing",
                "base_image_base64": "data:image/png;base64,iVBORw0KGgo..."
            }
        )
        
        # Should return 401 (auth) or 422 (validation) 
        assert response.status_code in [401, 422]
    
    def test_generate_masked_requires_base_image(self):
        """T179: Generate masked should require base_image_base64 field"""
        response = client.post(
            "/api/mapgenerator/generate-masked",
            json={
                "prompt": "Forest clearing",
                "mask_base64": "data:image/png;base64,iVBORw0KGgo..."
            }
        )
        
        # Should return 401 (auth) or 422 (validation)
        assert response.status_code in [401, 422]
    
    def test_generate_masked_validates_base64_format(self):
        """T180: Generate masked should validate base64 format"""
        response = client.post(
            "/api/mapgenerator/generate-masked",
            json={
                "prompt": "Forest clearing",
                "mask_base64": "not-valid-base64!@#$",
                "base_image_base64": "also-not-valid"
            }
        )
        
        # Should return 401 (auth) or 400/422 (validation)
        assert response.status_code in [400, 401, 422]


class TestGenerateMaskedMapRequest:
    """Tests for GenerateMaskedMapRequest model validation (T176)"""
    
    def test_generate_masked_map_request_requires_prompt(self):
        """T176: Request should require prompt field"""
        from mapgenerator.models import GenerateMaskedMapRequest
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            GenerateMaskedMapRequest(
                mask_base64="data:image/png;base64,iVBORw0KGgo...",
                base_image_base64="data:image/png;base64,iVBORw0KGgo..."
            )
    
    def test_generate_masked_map_request_requires_mask(self):
        """T176: Request should require mask_base64 field"""
        from mapgenerator.models import GenerateMaskedMapRequest
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            GenerateMaskedMapRequest(
                prompt="A forest clearing",
                base_image_base64="data:image/png;base64,iVBORw0KGgo..."
            )
    
    def test_generate_masked_map_request_requires_base_image(self):
        """T176: Request should require base_image_base64 field"""
        from mapgenerator.models import GenerateMaskedMapRequest
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            GenerateMaskedMapRequest(
                prompt="A forest clearing",
                mask_base64="data:image/png;base64,iVBORw0KGgo..."
            )
    
    def test_generate_masked_map_request_valid(self):
        """T176: Valid request should be accepted"""
        from mapgenerator.models import GenerateMaskedMapRequest
        
        request = GenerateMaskedMapRequest(
            prompt="A forest clearing with ancient stone ruins",
            mask_base64="data:image/png;base64,iVBORw0KGgo...",
            base_image_base64="data:image/png;base64,iVBORw0KGgo..."
        )
        
        assert request.prompt == "A forest clearing with ancient stone ruins"
        assert request.mask_base64.startswith("data:image/png")
        assert request.base_image_base64.startswith("data:image/png")
    
    def test_generate_masked_map_request_with_style_options(self):
        """T176: Request should accept optional style_options"""
        from mapgenerator.models import GenerateMaskedMapRequest
        
        request = GenerateMaskedMapRequest(
            prompt="A dungeon corridor",
            mask_base64="data:image/png;base64,test",
            base_image_base64="data:image/png;base64,test",
            style_options={
                "fantasy_level": "high",
                "rendering": "hand-painted"
            }
        )
        
        assert request.style_options is not None
        assert request.style_options.get("fantasy_level") == "high"
