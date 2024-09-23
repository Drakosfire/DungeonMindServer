from fastapi import APIRouter, Request, HTTPException, File, UploadFile, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import os
import json
import storegenerator.block_builder as block_builder
import storegenerator.store_helper as store_helper
import storegenerator.sd_generator as sd

router = APIRouter(prefix="/storegenerator")
templates = Jinja2Templates(directory="templates")

# Models
class DescriptionRequest(BaseModel):
    user_input: str

class GenerateImageRequest(BaseModel):
    sd_prompt: str

class SaveJsonRequest(BaseModel):
    filename: str
    jsonData: dict

# Route to serve the main page
@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    css_files = {
        'all_css': '/static/css/all.css',
        'font_css': '/static/css/css.css?family=Open+Sans:400,300,600,700',
        'bundle_css': '/static/css/bundle.css',
        'style_css': '/static/css/style.css',
        'phb_style_css': '/static/css/5ePHBstyle.css',
        'store_ui_css': '/static/css/storeUI.css'
    }
    return templates.TemplateResponse('storeUI.html', {"request": request, "css_files": css_files})
# Routes for store generator
@router.post('/process-description')
async def process_description(data: DescriptionRequest):
    user_input = data.user_input
    llm_output = store_helper.call_llm_and_cleanup(user_input)
    processed_blocks = block_builder.build_blocks(llm_output, block_builder.block_id)
    return {"html_blocks": processed_blocks, "llm_output": llm_output}

@router.post('/generate-image')
async def generate_image(data: GenerateImageRequest):
    sd_prompt = data.sd_prompt
    if not sd_prompt:
        raise HTTPException(status_code=400, detail="Missing sd_prompt")
    try:
        image_url = sd.preview_and_generate_image(sd_prompt)
        return {"image_url": image_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post('/save-json')
async def save_generated_data(request: Request, data: SaveJsonRequest):
    user = request.session.get('user')
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    user_id = user.get('sub')
    user_directory = os.path.join('saved_data', user_id, data.filename)
    os.makedirs(user_directory, exist_ok=True)

    file_path = os.path.join(user_directory, f'{data.filename}.json')
    try:
        with open(file_path, 'w') as json_file:
            json.dump(data.jsonData, json_file, indent=4)
        return {"message": "Data saved successfully!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# Helper function to check allowed file extensions
def allowed_file(filename):
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

# Route to upload images and save them
@router.post('/upload-image')
async def upload_image(request: Request, image: UploadFile = File(...), directoryName: str = Form(...), blockId: str = Form(...)):
    if not allowed_file(image.filename):
        raise HTTPException(status_code=400, detail="File type not allowed")
    user = request.session.get('user')
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    user_id = user.get('sub')
    user_directory = os.path.join('saved_data', user_id, directoryName)
    os.makedirs(user_directory, exist_ok=True)

    filename = f"{blockId}_{image.filename}"
    image_path = os.path.join(user_directory, filename)

    try:
        with open(image_path, "wb") as buffer:
            buffer.write(image.file.read())
        return {"fileUrl": image_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/list-loading-images")
async def list_loading_images():
    # Path to the folder containing loading images
    loading_images_folder = os.path.join('static', 'images', 'loadingMimic')
    try:
        # List all files in the directory
        files = os.listdir(loading_images_folder)
        # Filter and get only the image files
        image_files = [f"/static/images/loadingMimic/{file}" for file in files if file.endswith(('.png', '.jpg', '.jpeg', '.gif'))]
        return {"images": image_files}
    except FileNotFoundError:
        return {"images": []}

@router.get("/list-saved-stores")
async def list_saved_stores(request: Request):
    print("Listing saved stores")
    # Get the user's session info (assuming OAuth is implemented)
    user = request.session.get('user')
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Get the user ID (using OAuth 'sub' for unique identification)
    user_id = user.get('sub')

    # Path to the user's saved stores directory
    user_directory = os.path.join('saved_data', user_id)
    
    try:
        # List all saved stores (subdirectories) in the user's directory
        saved_stores = [store for store in os.listdir(user_directory) if os.path.isdir(os.path.join(user_directory, store))]
        return {"stores": saved_stores}

    except FileNotFoundError:
        return {"stores": []}  # Return an empty list if no stores are found

@router.get("/load-store")
async def load_store(storeName: str, request: Request):
    user = request.session.get('user')
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    user_id = user.get('sub')
    store_directory = os.path.join('saved_data', user_id, storeName)
    
    # Load the main JSON file for the store 
    store_file_path = os.path.join(store_directory, f'{storeName}.json')
    
    try:
        with open(store_file_path, 'r') as json_file:
            store_data = json.load(json_file)
        
        return store_data
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Store not found")
