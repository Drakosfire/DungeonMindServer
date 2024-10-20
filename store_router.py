from fastapi import APIRouter, Depends, HTTPException, Request
from auth_router import get_current_user
import os
import json

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
async def load_store(store_name: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user['sub']
    store_directory = os.path.join('saved_data', user_id, store_name)
    store_file_path = os.path.join(store_directory, f'{store_name}.json')
    
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

# Add more routes as needed for other operations