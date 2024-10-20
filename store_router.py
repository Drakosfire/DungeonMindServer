from fastapi import APIRouter, Depends, HTTPException, Request, File, UploadFile, Form
from auth_router import get_current_user
import os
import json
import shutil

router = APIRouter()

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
    store_name = store_data.get('name', 'unnamed_store')
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

@router.post('/upload-image')
async def upload_image(
    request: Request,
    image: UploadFile = File(...),
    directoryName: str = Form(...),
    blockId: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    if not allowed_file(image.filename):
        raise HTTPException(status_code=400, detail="File type not allowed")
    
    user_id = current_user['sub']
    user_directory = os.path.join('saved_data', user_id, directoryName)
    os.makedirs(user_directory, exist_ok=True)

    filename = f"{blockId}_{image.filename}"
    image_path = os.path.join(user_directory, filename)

    try:
        with open(image_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        return {"fileUrl": f"/saved_data/{user_id}/{directoryName}/{filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))