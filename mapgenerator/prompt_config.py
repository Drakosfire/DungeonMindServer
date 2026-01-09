"""
Default values and configuration for map prompt generation.
"""

def get_defaults() -> dict:
    """Get default values for MapSpec generation."""
    return {
        "fantasy_level": "low",
        "scale": "encounter",
        "pathways": "organic",
        "elevation_present": False,
        "rendering": "hand-painted",
        "genre": "low-fantasy",
        "palette": {
            "saturation": "muted",
            "contrast": "high",
            "temperature": "neutral"
        },
        "texture_density": "medium",
        "movement_space": "open",
        "cover_density": "medium",
        "system": "dnd5e",
        "readability_priority": True,
        "perspective": "top-down-90"
    }
