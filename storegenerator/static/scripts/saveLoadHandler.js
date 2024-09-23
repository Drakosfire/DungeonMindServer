import { getState, updateState } from "/storegenerator/static/scripts/state.js";
import { initializeTextareaResizing } from "/storegenerator/static/scripts/handleTextareas.js";
import { uploadImages } from "/storegenerator/static/scripts/imageHandler.js";
import { iterateThroughBlocks } from "/storegenerator/static/scripts/jsonToBlocks.js";
import { clearBlocks } from "/storegenerator/static/scripts/utils.js";


// Function to save JSON data to the server
async function saveJson(dataToSend) {
    return fetch('/storegenerator/save-json', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(dataToSend)
    })
        .then(response => response.json())
        .then(data => {
            console.log('Success:', data);
            return data;
        })
        .catch((error) => {
            console.error('Error:', error);
        });
}

// Main save handler
export async function saveHandler() {
    let state = getState();
    let jsonData = state.jsonData;
    console.log('JSON Data:', jsonData);
    let title = '';
    for (const blockId in jsonData.storeData) {
        if (jsonData.storeData[blockId].type === 'title') {
            title = jsonData.storeData[blockId].title;
            break;
        }
    }
    let sanitizedTitle = title.replace(/\W+/g, '_').trim('_');

    // Prepare image data for upload
    let imagesToUpload = [];
    for (const blockId in jsonData.storeData) {
        const block = jsonData.storeData[blockId];
        if (block.type === 'image' && block.imgUrl !== '') {
            console.log('Image block:', block);
            imagesToUpload.push({
                blockId: blockId, imgUrl: block.imgUrl
            });
        }
    }

    try {
        // Upload images and get new URLs
        if (imagesToUpload.length > 0) {
            const uploadedImages = await uploadImages(imagesToUpload, sanitizedTitle);
            uploadedImages.forEach(({ blockId, fileUrl }) => {
                jsonData.storeData[blockId].imgUrl = fileUrl;
            });
        }

        // Prepare data to send to the backend
        let dataToSend = {
            filename: sanitizedTitle,
            jsonData: jsonData
        };

        // Save the JSON data to the server
        await saveJson(dataToSend);
    } catch (error) {
        console.error('Error during save process:', error);
    }
    console.log('Saved JSON data:', jsonData);
    updateState('jsonData', jsonData.storeData);
}

export function loadHandler() {
    clearBlocks();
    let state = getState();
    console.log('State:', state);
    let blocks = state.jsonData.storeData;
    console.log('jsonData:', state.jsonData);
    console.log('Blocks:', blocks);
    let ownerCount = 0;
    let employeeCount = 0;
    for (const [blockId, block] of Object.entries(blocks)) {
        if (block.type === 'owner') {
            ownerCount++;
        }
        if (block.type === 'employee') {
            employeeCount++;
        }
    }

    // Future feature: allow for indexing position on page

    // let blockIndex = 0;
    // for (const block of Object.values(pageBlocks)) {
    //     block['page-container-index'] = blockIndex++;
    // }

    iterateThroughBlocks(blocks, ownerCount, employeeCount);
    initializeTextareaResizing();
}

// Function to fetch the list of saved stores from the server
export async function fetchSavedStores() {
    try {
        const response = await fetch('/storegenerator/list-saved-stores');
        if (response.ok) {
            const data = await response.json();
            console.log('Fetched saved stores:', data.stores);

            // Populate the UI with the list of stores (e.g., in a dropdown)
            populateSavedStoresDropdown(data.stores);
        } else {
            console.error('Failed to fetch saved stores');
        }
    } catch (error) {
        console.error('Error fetching saved stores:', error);
    }
}

// Function to populate the dropdown with saved stores
function populateSavedStoresDropdown(stores) {
    const dropdown = document.getElementById('savedStoresDropdown');
    dropdown.innerHTML = '';  // Clear any existing options

    stores.forEach((store) => {
        const option = document.createElement('option');
        option.value = store;
        option.textContent = store;  // Display the store name
        dropdown.appendChild(option);
    });
    dropdown.onchange = loadSelectedStore;
}

// Function to load the selected store
export async function loadSelectedStore() {
    const dropdown = document.getElementById('savedStoresDropdown');
    const selectedStore = dropdown.value;  // Get the selected store's name

    if (selectedStore) {
        try {
            const response = await fetch(`storegenerator/load-store?storeName=${encodeURIComponent(selectedStore)}`);
            if (response.ok) {
                const responseData = await response.json();
                console.log('Loaded response data:', responseData);
                // Now you can update the UI with the loaded store data
                updateState('jsonData', responseData);
                loadHandler();
            } else {
                console.error('Failed to load the store');
            }
        } catch (error) {
            console.error('Error loading the store:', error);
        }
    }
}





