"""
Asset Router

Focused router handling static asset delivery.
Replaces hardcoded arrays with proper service architecture.

Extracted from monolithic cardgenerator_router.py as part of architectural refactoring.
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel

from cardgenerator.services.asset_service import asset_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/assets", tags=["Assets"])

# Response models
class ExampleImageResponse(BaseModel):
    url: str
    name: str
    category: str
    description: str
    id: str

class BorderOptionResponse(BaseModel):
    id: str
    url: str
    name: str
    style: str
    description: str

class ExampleImagesResponse(BaseModel):
    examples: List[ExampleImageResponse]
    total: int
    categories: List[str]

class BorderOptionsResponse(BaseModel):
    borders: List[BorderOptionResponse]
    total: int
    styles: List[str]

@router.get('/examples', response_model=ExampleImagesResponse)
async def get_example_images(category: Optional[str] = Query(None, description="Filter by category")):
    """
    Get curated example images for Step 2 inspiration
    
    Clean endpoint that replaces hardcoded arrays in the router
    """
    try:
        logger.info(f"Example images request - category: {category}")
        
        # Get examples from service
        if category:
            examples = asset_service.get_example_by_category(category)
        else:
            examples = asset_service.get_example_images()
        
        # Convert to response format
        example_responses = [
            ExampleImageResponse(
                url=example.url,
                name=example.name,
                category=example.category,
                description=example.description,
                id=example.id or f"example_{i+1}"
            )
            for i, example in enumerate(examples)
        ]
        
        # Get available categories
        categories = asset_service.get_asset_categories()
        
        logger.info(f"Returning {len(example_responses)} examples")
        return ExampleImagesResponse(
            examples=example_responses,
            total=len(example_responses),
            categories=categories
        )
        
    except Exception as e:
        logger.error(f"Error fetching example images: {e}")
        # Return empty result rather than failing
        return ExampleImagesResponse(examples=[], total=0, categories=[])

@router.get('/borders', response_model=BorderOptionsResponse)
async def get_border_options(style: Optional[str] = Query(None, description="Filter by style")):
    """
    Get available border options for Step 3 card frames
    
    Clean endpoint that replaces hardcoded arrays in the router
    """
    try:
        logger.info(f"Border options request - style: {style}")
        
        # Get borders from service
        if style:
            borders = asset_service.get_border_by_style(style)
        else:
            borders = asset_service.get_border_options()
        
        # Convert to response format
        border_responses = [
            BorderOptionResponse(
                id=border.id,
                url=border.url,
                name=border.name,
                style=border.style,
                description=border.description
            )
            for border in borders
        ]
        
        # Get available styles
        styles = asset_service.get_border_styles()
        
        logger.info(f"Returning {len(border_responses)} border options")
        return BorderOptionsResponse(
            borders=border_responses,
            total=len(border_responses),
            styles=styles
        )
        
    except Exception as e:
        logger.error(f"Error fetching border options: {e}")
        # Return empty result rather than failing
        return BorderOptionsResponse(borders=[], total=0, styles=[])

@router.get('/categories')
async def get_asset_categories():
    """
    Get list of available asset categories
    
    Utility endpoint for frontend dropdowns
    """
    try:
        categories = asset_service.get_asset_categories()
        logger.info(f"Returning {len(categories)} categories")
        return {"categories": categories}
        
    except Exception as e:
        logger.error(f"Error fetching categories: {e}")
        return {"categories": []}

@router.get('/styles')
async def get_border_styles():
    """
    Get list of available border styles
    
    Utility endpoint for frontend dropdowns
    """
    try:
        styles = asset_service.get_border_styles()
        logger.info(f"Returning {len(styles)} styles")
        return {"styles": styles}
        
    except Exception as e:
        logger.error(f"Error fetching styles: {e}")
        return {"styles": []}