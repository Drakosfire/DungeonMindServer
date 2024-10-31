from fastapi import APIRouter, Depends, HTTPException, Request, File, UploadFile, Form
from auth_router import get_current_user
import os
import json
import shutil
from pydantic import BaseModel
import storegenerator.block_builder as block_builder
import storegenerator.store_helper as store_helper
import storegenerator.sd_generator as sd
import httpx
# import logging
from cloudflare.handle_images import upload_image_to_cloudflare

# Cloudflare credentials
cloudflare_account_id = os.getenv('CLOUDFLARE_ACCOUNT_ID')
cloudflare_api_token = os.getenv('CLOUDFLARE_IMAGES_API_TOKEN')

# Models
class DescriptionRequest(BaseModel):
    user_input: str

class GenerateImageRequest(BaseModel):
    sd_prompt: str

class SaveJsonRequest(BaseModel):
    filename: str
    jsonData: dict

# Define the request model
class ImageUploadRequest(BaseModel):
    image_url: str

router = APIRouter()

# Configure logging
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

@router.get("/list-saved-stores")
async def list_saved_stores(current_user: dict = Depends(get_current_user)):
    user_id = current_user['sub']
    user_directory = os.path.join('saved_data', user_id)
    try:
        saved_stores = [store for store in os.listdir(user_directory) if os.path.isdir(os.path.join(user_directory, store))]
        return {"stores": saved_stores}
    except FileNotFoundError:
        return {"stores": []}

@router.get("/load-store")
async def load_store(storeName: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user['sub']
    store_directory = os.path.join('saved_data', user_id, storeName)
    store_file_path = os.path.join(store_directory, f'{storeName}.json')
    
    try:
        with open(store_file_path, 'r') as json_file:
            store_data = json.load(json_file)
        return store_data
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Store not found")

@router.post("/save-store")
async def save_store(store_data: dict, current_user: dict = Depends(get_current_user)):
    user_id = current_user['sub']
    print(f"store_data: {store_data}")
    store_name = extract_title(store_data)
    user_directory = os.path.join('saved_data', user_id, store_name)
    os.makedirs(user_directory, exist_ok=True)

    file_path = os.path.join(user_directory, f'{store_name}.json')
    try:
        with open(file_path, 'w') as json_file:
            json.dump(store_data, json_file, indent=4)
        return {"message": "Store saved successfully!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def allowed_file(filename):
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

@router.get("/list-loading-images")
async def list_loading_images():
    #Print the current working directory
    # print(f"Current working directory: {os.getcwd()}")
    # Absolute path to the folder containing loading images
    loading_images_folder = os.path.join('static', 'images', 'loadingMimic')
    # print(f"Loading images folder: {loading_images_folder}")
    try:
        # List all files in the directory
        files = os.listdir(loading_images_folder)
        print(f"Files in loading images folder: {files}")
        # Filter and get only the image files
        image_files = [f"{loading_images_folder}/{file}" for file in files if file.endswith(('.png', '.jpg', '.jpeg', '.gif'))]
        return {"images": image_files}
    except FileNotFoundError:
        print(f"Loading images folder not found: {loading_images_folder}")
        return {"images": []}
    
@router.post('/process-description')
async def process_description(data: DescriptionRequest):
    user_input = data.user_input
    llm_output = store_helper.call_llm_and_cleanup(user_input)
    processed_blocks = block_builder.build_blocks(llm_output, block_builder.block_id)
    return {"html_blocks": processed_blocks, "llm_output": llm_output}
    
def extract_title(json_data):
    title = ''

    for block_id, block_data in json_data['storeData'].items():
        print(f'Block ID: {block_id}, Type: {block_data["type"]}')
        if block_data['type'] == 'title':
            print(f'Title found: {block_data["title"]}')
            title = block_data['title']
            break

    sanitized_title = ''.join('_' if not c.isalnum() else c for c in title).strip('_')
    # print(f'Sanitized title: {sanitized_title}')

    return sanitized_title  

# Generate image and upload to Cloudflare
# This is called from the saveLoadHandler.js file
# It is called when the user clicks the "Generate Image" button
# I should manage the upload to Cloudflare in the saveLoadHandler.js file
@router.post('/generate-image')
async def generate_image(data: GenerateImageRequest):
    sd_prompt = data.sd_prompt
    if not sd_prompt:
        raise HTTPException(status_code=400, detail="Missing sd_prompt")
    try:
        image_url = sd.preview_and_generate_image(sd_prompt)
        # logger.info("Generated image URL: %s", image_url)
        uploaded_image = await upload_image_to_cloudflare(image_url)
        # logger.info("Uploaded image: %s", uploaded_image)
        return {"image_url": uploaded_image}
    except Exception as e:
        # logger.error("Error generating image: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal Server Error")