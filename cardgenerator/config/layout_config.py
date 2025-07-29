"""
Card layout configuration - defines dimensions, text areas, and asset positioning
"""

CARD_LAYOUT = {
    "dimensions": {
        "width": 768,
        "height": 1024
    },
    "text_areas": {
        "title": {
            "x": 395, 
            "y": 55, 
            "width": 600, 
            "height": 60,
            "font_size": 50,
            "alignment": "center"
        },
        "type": {
            "x": 384, 
            "y": 545, 
            "width": 600, 
            "height": 45,
            "font_size": 50,
            "alignment": "center"
        },
        "description": {
            "x": 105, 
            "y": 630, 
            "width": 590, 
            "height": 215,
            "font_size": 50,
            "alignment": "left",
            "multiline": True
        },
        "value": {
            "x": 660, 
            "y": 905, 
            "width": 125, 
            "height": 50,
            "font_size": 50,
            "alignment": "center"
        },
        "quote": {
            "x": 110, 
            "y": 885, 
            "width": 470, 
            "height": 60,
            "font_size": 50,
            "alignment": "left",
            "style": "italic"
        }
    },
    "fonts": {
        "regular": "cardgenerator/fonts/Balgruf.ttf",
        "italic": "cardgenerator/fonts/BalgrufItalic.ttf"
    }
}

ASSET_CONFIG = {
    "value_overlay": {
        "url": "https://media.githubusercontent.com/media/Drakosfire/CardGenerator/main/card_parts/Value_box_transparent.png",
        "position": {"x": 0, "y": 0},
        "size": {"width": 768, "height": 1024}
    },
    "rarity_stickers": {
        "urls": {
            "Default": "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/451a66ad-5116-4649-137b-aed784e5c700/public",
            "Common": "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/8b579f17-7f92-4a0a-e891-e8990be9e400/public",
            "Uncommon": "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/65889c14-dc2b-4b6a-9cbf-7d7704fba100/public",
            "Rare": "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/dedf72a3-00b8-43cf-e95f-7b13b899d100/public",
            "Very Rare": "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/3b452c8b-e945-448a-f461-48b99c266c00/public",
            "Legendary": "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/2c60b814-ab4c-46ac-e479-d3a860413700/public"
        },
        "position": {"x": 0, "y": 909},
        "size": {"width": 115, "height": 115}
    }
}