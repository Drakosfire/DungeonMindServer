#!/usr/bin/env python3
"""
OpenAI Image Generation Model Comparison Script

Tests and compares OpenAI's image generation models:
- gpt-image-1 (full quality model)
- gpt-image-1-mini (faster/cheaper model)

Provides verbose logging with detailed timing for performance analysis.
"""

import os
import sys
import time
import logging
import base64
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import asyncio
from dataclasses import dataclass, asdict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from openai import OpenAI
import fal_client
import httpx
from PIL import Image
import io

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'image_gen_comparison_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)

# Test configuration
TEST_PROMPT = """Dr. Jupiter, Small, Dr. Jupiter is a peculiar creature, a mix of a white Shiba Inu and an all white American Eskimo Dog, with pointy ears the color of a toasted marshmallow. Adorned with a lab coat and a stethoscope, this small canine is known for its medical prowess, often seen with a head mirror on its forehead. Dr. Jupiter roams the lands offering healing and medical assistance to those in need, always eager to help with a wagging tail and a cheerful bark., fantasy art, detailed portrait, dramatic lighting, high quality, in the style of an oil painting in a doctor's office."""

NUM_IMAGES = 4  # Number of images to generate per model
OUTPUT_DIR = Path(__file__).parent / "image_comparison_output" / datetime.now().strftime("%Y%m%d_%H%M%S")


@dataclass
class TimingMetrics:
    """Timing metrics for a generation step"""
    step_name: str
    start_time: float
    end_time: float
    duration_seconds: float
    details: Optional[str] = None
    
    def __str__(self):
        return f"{self.step_name}: {self.duration_seconds:.2f}s {f'({self.details})' if self.details else ''}"


@dataclass
class ImageGenerationResult:
    """Results from an image generation attempt"""
    model_name: str
    success: bool
    images: List[Dict[str, Any]]
    error: Optional[str] = None
    total_duration: float = 0.0
    timing_breakdown: List[TimingMetrics] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.timing_breakdown is None:
            self.timing_breakdown = []
        if self.metadata is None:
            self.metadata = {}


class Timer:
    """Context manager for timing code blocks"""
    
    def __init__(self, name: str):
        self.name = name
        self.start_time = None
        self.end_time = None
        
    def __enter__(self):
        self.start_time = time.time()
        logger.info(f"⏱️  START: {self.name}")
        return self
        
    def __exit__(self, *args):
        self.end_time = time.time()
        duration = self.end_time - self.start_time
        logger.info(f"⏱️  END: {self.name} - Duration: {duration:.2f}s")
        
    @property
    def duration(self) -> float:
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return 0.0
    
    def get_metric(self, details: Optional[str] = None) -> TimingMetrics:
        return TimingMetrics(
            step_name=self.name,
            start_time=self.start_time,
            end_time=self.end_time,
            duration_seconds=self.duration,
            details=details
        )


class ImageGenerationTester:
    """Test harness for comparing image generation models"""
    
    def __init__(self, output_dir: Path = OUTPUT_DIR):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.openai_client = OpenAI()
        logger.info(f"📁 Output directory: {self.output_dir}")
        
    async def test_openai_model(self, model_name: str, prompt: str, num_images: int = 1) -> ImageGenerationResult:
        """
        Test OpenAI image generation models (gpt-image-1, gpt-image-1-mini)
        
        Uses the new OpenAI Images API:
        client.images.generate(
            model=model_name,
            prompt=prompt
        )
        """
        logger.info("=" * 80)
        logger.info(f"🎨 Testing OpenAI {model_name}")
        logger.info("=" * 80)
        
        result = ImageGenerationResult(
            model_name=f"openai-{model_name}",
            success=False,
            images=[],
            timing_breakdown=[]
        )
        
        overall_timer = Timer(f"OpenAI {model_name} - Overall")
        
        try:
            with overall_timer:
                # OpenAI gpt-image-1 doesn't support num_images parameter directly
                # Generate images one at a time
                logger.info(f"📝 Prompt: {prompt[:100]}...")
                logger.info(f"🔢 Requesting {num_images} images (sequential generation)")
                
                for i in range(num_images):
                    logger.info(f"\n--- Image {i+1}/{num_images} ---")
                    
                    # API call timing
                    api_timer = Timer(f"OpenAI API Call {i+1}")
                    with api_timer:
                        logger.info("🌐 Calling OpenAI Images API...")
                        logger.info(f"   Model: {model_name}")
                        logger.info(f"   Response format: url (default)")
                        
                        response = self.openai_client.images.generate(
                            model=model_name,
                            prompt=prompt,
                            n=1  # Generate one image at a time
                        )
                    
                    result.timing_breakdown.append(api_timer.get_metric(f"Image {i+1} generation"))
                    logger.info(f"✅ API call complete: {api_timer.duration:.2f}s")
                    
                    # Process and save timing
                    save_timer = Timer(f"Process & Save {i+1}")
                    with save_timer:
                        # Check if response has b64_json or url
                        if hasattr(response.data[0], 'b64_json') and response.data[0].b64_json:
                            logger.info("🔓 Processing base64 image data...")
                            
                            # Decode base64 to image
                            image_bytes = base64.b64decode(response.data[0].b64_json)
                            image = Image.open(io.BytesIO(image_bytes))
                            image_url = None
                        elif hasattr(response.data[0], 'url') and response.data[0].url:
                            logger.info("📥 Downloading image from URL...")
                            image_url = response.data[0].url
                            logger.info(f"   URL: {image_url[:80]}...")
                            
                            # Download image
                            import httpx
                            async with httpx.AsyncClient(timeout=30.0) as client:
                                img_response = await client.get(image_url)
                                image = Image.open(io.BytesIO(img_response.content))
                        else:
                            raise ValueError(f"Response contains neither b64_json nor url")
                        
                        logger.info(f"   Image size: {image.size}")
                        logger.info(f"   Image mode: {image.mode}")
                        logger.info(f"   Image format: {image.format}")
                        
                        # Save image
                        image_filename = f"openai_{model_name.replace('-', '_')}_{i+1}.png"
                        image_path = self.output_dir / image_filename
                        image.save(image_path, "PNG")
                        
                        logger.info(f"💾 Saved: {image_path}")
                    
                    result.timing_breakdown.append(save_timer.get_metric(f"Image {i+1} process/save"))
                    
                    # Add to results
                    result.images.append({
                        "index": i + 1,
                        "path": str(image_path),
                        "filename": image_filename,
                        "url": image_url if image_url else "base64",
                        "size": image.size,
                        "mode": image.mode,
                        "api_duration": api_timer.duration,
                        "process_duration": save_timer.duration
                    })
                
                result.success = True
                result.total_duration = overall_timer.duration
                result.metadata = {
                    "model": model_name,
                    "response_format": "b64_json (default)",
                    "images_generated": len(result.images),
                    "avg_api_time": sum(img["api_duration"] for img in result.images) / len(result.images),
                    "avg_process_time": sum(img["process_duration"] for img in result.images) / len(result.images),
                    "total_time": overall_timer.duration
                }
                
                logger.info(f"\n✅ OpenAI {model_name} generation SUCCESSFUL")
                logger.info(f"📊 Generated {len(result.images)} images in {overall_timer.duration:.2f}s")
                logger.info(f"⚡ Average time per image: {overall_timer.duration / len(result.images):.2f}s")
                
        except Exception as e:
            result.success = False
            result.error = str(e)
            logger.error(f"❌ OpenAI {model_name} generation FAILED: {e}")
            logger.exception("Full traceback:")
        
        return result
    
    async def test_openai_gpt_image_1(self, prompt: str, num_images: int = 1) -> ImageGenerationResult:
        """Test OpenAI's gpt-image-1 model (full version)"""
        return await self.test_openai_model("gpt-image-1", prompt, num_images)
    
    async def test_openai_gpt_image_mini(self, prompt: str, num_images: int = 1) -> ImageGenerationResult:
        """Test OpenAI's gpt-image-1-mini model (smaller/faster version)"""
        return await self.test_openai_model("gpt-image-1-mini", prompt, num_images)
    
    async def test_fal_flux_pro(self, prompt: str, num_images: int = 4) -> ImageGenerationResult:
        """Test Fal.ai Flux-Pro model"""
        logger.info("=" * 80)
        logger.info("🎨 Testing Fal.ai Flux-Pro")
        logger.info("=" * 80)
        
        result = ImageGenerationResult(
            model_name="fal-ai/flux-pro/new",
            success=False,
            images=[],
            timing_breakdown=[]
        )
        
        overall_timer = Timer("Fal.ai Flux-Pro - Overall")
        
        try:
            with overall_timer:
                logger.info(f"📝 Prompt: {prompt[:100]}...")
                logger.info(f"🔢 Requesting {num_images} images")
                
                # API call timing
                api_timer = Timer("Fal.ai Flux-Pro API Call")
                with api_timer:
                    logger.info("🌐 Calling Fal.ai API...")
                    logger.info(f"   Model: fal-ai/flux-pro/new")
                    logger.info(f"   Image size: 1024x1024")
                    logger.info(f"   Num images: {num_images}")
                    
                    fal_result = fal_client.subscribe(
                        "fal-ai/flux-pro/new",
                        arguments={
                            "prompt": prompt,
                            "num_images": num_images,
                            "image_size": {
                                "width": 1024,
                                "height": 1024
                            },
                            "enable_safety_checker": True
                        }
                    )
                
                result.timing_breakdown.append(api_timer.get_metric(f"{num_images} images batch"))
                logger.info(f"✅ API call complete: {api_timer.duration:.2f}s")
                logger.info(f"   Response keys: {list(fal_result.keys())}")
                logger.info(f"   Images in response: {len(fal_result.get('images', []))}")
                
                # Download and save timing
                download_timer = Timer("Download & Save Images")
                with download_timer:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        for idx, image_data in enumerate(fal_result.get("images", [])):
                            image_url = image_data.get("url")
                            logger.info(f"\n   📥 Downloading image {idx+1}/{num_images}")
                            logger.info(f"      URL: {image_url[:80]}...")
                            
                            img_download_timer = Timer(f"Download {idx+1}")
                            with img_download_timer:
                                response = await client.get(image_url)
                                image = Image.open(io.BytesIO(response.content))
                                
                                logger.info(f"      Image size: {image.size}")
                                logger.info(f"      Image mode: {image.mode}")
                                
                                # Save image
                                image_filename = f"flux_pro_{idx+1}.png"
                                image_path = self.output_dir / image_filename
                                image.save(image_path, "PNG")
                                
                                logger.info(f"      💾 Saved: {image_path}")
                            
                            result.images.append({
                                "index": idx + 1,
                                "path": str(image_path),
                                "filename": image_filename,
                                "url": image_url,
                                "size": image.size,
                                "mode": image.mode,
                                "download_duration": img_download_timer.duration
                            })
                
                result.timing_breakdown.append(download_timer.get_metric(f"{num_images} images download"))
                
                result.success = True
                result.total_duration = overall_timer.duration
                result.metadata = {
                    "model": "fal-ai/flux-pro/new",
                    "batch_generation": True,
                    "images_generated": len(result.images),
                    "api_time": api_timer.duration,
                    "download_time": download_timer.duration,
                    "total_time": overall_timer.duration
                }
                
                logger.info("\n✅ Fal.ai Flux-Pro generation SUCCESSFUL")
                logger.info(f"📊 Generated {len(result.images)} images in {overall_timer.duration:.2f}s")
                logger.info(f"⚡ Average time per image: {overall_timer.duration / len(result.images):.2f}s")
                
        except Exception as e:
            result.success = False
            result.error = str(e)
            logger.error(f"❌ Fal.ai Flux-Pro generation FAILED: {e}")
            logger.exception("Full traceback:")
        
        return result
    
    async def test_fal_imagen4(self, prompt: str, num_images: int = 4) -> ImageGenerationResult:
        """Test Fal.ai Imagen4 model"""
        logger.info("=" * 80)
        logger.info("🎨 Testing Fal.ai Imagen4")
        logger.info("=" * 80)
        
        result = ImageGenerationResult(
            model_name="fal-ai/imagen4/preview",
            success=False,
            images=[],
            timing_breakdown=[]
        )
        
        overall_timer = Timer("Fal.ai Imagen4 - Overall")
        
        try:
            with overall_timer:
                logger.info(f"📝 Prompt: {prompt[:100]}...")
                logger.info(f"🔢 Requesting {num_images} images")
                
                # API call timing
                api_timer = Timer("Fal.ai Imagen4 API Call")
                with api_timer:
                    logger.info("🌐 Calling Fal.ai API...")
                    logger.info(f"   Model: fal-ai/imagen4/preview")
                    logger.info(f"   Image size: 1024x1024")
                    logger.info(f"   Num images: {num_images}")
                    logger.info(f"   Inference steps: 28")
                    logger.info(f"   Guidance scale: 3.5")
                    
                    fal_result = fal_client.subscribe(
                        "fal-ai/imagen4/preview",
                        arguments={
                            "prompt": prompt,
                            "num_inference_steps": 28,
                            "guidance_scale": 3.5,
                            "num_images": num_images,
                            "image_size": {
                                "width": 1024,
                                "height": 1024
                            }
                        }
                    )
                
                result.timing_breakdown.append(api_timer.get_metric(f"{num_images} images batch"))
                logger.info(f"✅ API call complete: {api_timer.duration:.2f}s")
                logger.info(f"   Response keys: {list(fal_result.keys())}")
                logger.info(f"   Images in response: {len(fal_result.get('images', []))}")
                
                # Download and save timing
                download_timer = Timer("Download & Save Images")
                with download_timer:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        for idx, image_data in enumerate(fal_result.get("images", [])):
                            image_url = image_data.get("url")
                            logger.info(f"\n   📥 Downloading image {idx+1}/{num_images}")
                            logger.info(f"      URL: {image_url[:80]}...")
                            
                            img_download_timer = Timer(f"Download {idx+1}")
                            with img_download_timer:
                                response = await client.get(image_url)
                                image = Image.open(io.BytesIO(response.content))
                                
                                logger.info(f"      Image size: {image.size}")
                                logger.info(f"      Image mode: {image.mode}")
                                
                                # Save image
                                image_filename = f"imagen4_{idx+1}.png"
                                image_path = self.output_dir / image_filename
                                image.save(image_path, "PNG")
                                
                                logger.info(f"      💾 Saved: {image_path}")
                            
                            result.images.append({
                                "index": idx + 1,
                                "path": str(image_path),
                                "filename": image_filename,
                                "url": image_url,
                                "size": image.size,
                                "mode": image.mode,
                                "download_duration": img_download_timer.duration
                            })
                
                result.timing_breakdown.append(download_timer.get_metric(f"{num_images} images download"))
                
                result.success = True
                result.total_duration = overall_timer.duration
                result.metadata = {
                    "model": "fal-ai/imagen4/preview",
                    "batch_generation": True,
                    "images_generated": len(result.images),
                    "api_time": api_timer.duration,
                    "download_time": download_timer.duration,
                    "total_time": overall_timer.duration
                }
                
                logger.info("\n✅ Fal.ai Imagen4 generation SUCCESSFUL")
                logger.info(f"📊 Generated {len(result.images)} images in {overall_timer.duration:.2f}s")
                logger.info(f"⚡ Average time per image: {overall_timer.duration / len(result.images):.2f}s")
                
        except Exception as e:
            result.success = False
            result.error = str(e)
            logger.error(f"❌ Fal.ai Imagen4 generation FAILED: {e}")
            logger.exception("Full traceback:")
        
        return result
    
    def generate_comparison_report(self, results: List[ImageGenerationResult]) -> str:
        """Generate a detailed comparison report"""
        logger.info("\n" + "=" * 80)
        logger.info("📊 COMPARISON REPORT")
        logger.info("=" * 80)
        
        report_lines = [
            "=" * 80,
            "OPENAI IMAGE GENERATION MODEL COMPARISON REPORT",
            "=" * 80,
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Test Prompt: {TEST_PROMPT[:100]}...",
            f"Images Requested Per Model: {NUM_IMAGES}",
            "",
            "=" * 80,
            "RESULTS SUMMARY",
            "=" * 80,
            ""
        ]
        
        # Table header
        report_lines.append(f"{'Model':<35} {'Status':<10} {'Images':<8} {'Total Time':<12} {'Avg/Image':<12}")
        report_lines.append("-" * 80)
        
        # Results table
        for result in results:
            status = "✅ SUCCESS" if result.success else "❌ FAILED"
            num_images = len(result.images)
            total_time = f"{result.total_duration:.2f}s" if result.success else "N/A"
            avg_time = f"{result.total_duration / num_images:.2f}s" if result.success and num_images > 0 else "N/A"
            
            report_lines.append(f"{result.model_name:<35} {status:<10} {num_images:<8} {total_time:<12} {avg_time:<12}")
            
            if not result.success and result.error:
                report_lines.append(f"  Error: {result.error}")
        
        report_lines.append("")
        
        # Detailed timing breakdown
        report_lines.extend([
            "=" * 80,
            "DETAILED TIMING BREAKDOWN",
            "=" * 80,
            ""
        ])
        
        for result in results:
            report_lines.append(f"\n{result.model_name}:")
            report_lines.append("-" * 40)
            
            if result.success:
                for timing in result.timing_breakdown:
                    report_lines.append(f"  {str(timing)}")
                
                if result.metadata:
                    report_lines.append("\nMetadata:")
                    for key, value in result.metadata.items():
                        if isinstance(value, float):
                            report_lines.append(f"  {key}: {value:.2f}")
                        else:
                            report_lines.append(f"  {key}: {value}")
            else:
                report_lines.append(f"  FAILED: {result.error}")
        
        # Output files
        report_lines.extend([
            "",
            "=" * 80,
            "OUTPUT FILES",
            "=" * 80,
            f"Output Directory: {self.output_dir}",
            ""
        ])
        
        for result in results:
            if result.success:
                report_lines.append(f"\n{result.model_name}:")
                for img in result.images:
                    report_lines.append(f"  {img['filename']}")
        
        report_lines.extend([
            "",
            "=" * 80,
            ""
        ])
        
        report_text = "\n".join(report_lines)
        
        # Print to console
        print(report_text)
        
        # Save to file
        report_path = self.output_dir / "comparison_report.txt"
        with open(report_path, "w") as f:
            f.write(report_text)
        logger.info(f"\n💾 Report saved to: {report_path}")
        
        # Save JSON results
        json_path = self.output_dir / "comparison_results.json"
        json_data = {
            "test_date": datetime.now().isoformat(),
            "prompt": TEST_PROMPT,
            "num_images_requested": NUM_IMAGES,
            "results": [
                {
                    "model_name": r.model_name,
                    "success": r.success,
                    "error": r.error,
                    "total_duration": r.total_duration,
                    "images": r.images,
                    "metadata": r.metadata,
                    "timing_breakdown": [asdict(t) for t in r.timing_breakdown]
                }
                for r in results
            ]
        }
        
        with open(json_path, "w") as f:
            json.dump(json_data, f, indent=2)
        logger.info(f"💾 JSON results saved to: {json_path}")
        
        return report_text


async def main():
    """Main test execution"""
    logger.info("🚀 Starting OpenAI Image Generation Model Comparison")
    logger.info(f"📝 Test Prompt: {TEST_PROMPT[:100]}...")
    logger.info(f"🔢 Images per model: {NUM_IMAGES}")
    logger.info("")
    
    # Verify environment variables
    required_vars = ["OPENAI_API_KEY"]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        logger.error(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        return
    
    logger.info("✅ Environment variables verified")
    logger.info("")
    
    # Initialize tester
    tester = ImageGenerationTester()
    
    # Run tests
    results = []
    
    # Test OpenAI gpt-image-1 (full model)
    logger.info("Testing gpt-image-1 (full quality model)...")
    gpt1_result = await tester.test_openai_gpt_image_1(TEST_PROMPT, NUM_IMAGES)
    results.append(gpt1_result)
    
    # Test OpenAI gpt-image-1-mini (faster/cheaper model)
    logger.info("\nTesting gpt-image-1-mini (faster/cheaper model)...")
    gpt1_mini_result = await tester.test_openai_gpt_image_mini(TEST_PROMPT, NUM_IMAGES)
    results.append(gpt1_mini_result)
    
    # Generate comparison report
    tester.generate_comparison_report(results)
    
    logger.info("\n✅ All tests complete!")


if __name__ == "__main__":
    asyncio.run(main())
