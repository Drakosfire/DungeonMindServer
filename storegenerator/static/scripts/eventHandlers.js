// eventHandlers.js
import { printScreen, handleReset } from './utils.js';
import { addPage, removePage } from './pageHandler.js';
import {
    toggleAllTextBlocks,
    autofillBlocks,
    storeInitialPositions
} from './blockHandler.js';
import { startLoadingAnimation, stopLoadingAnimation } from './loadingImage.js';
import { handleDragOver, handleDrop, } from './dragDropHandler.js';
import { handleTrashOver, handleTrashDrop, handleTrashLeave } from './trashHandler.js';
import { getState, updateState, resetState } from './state.js';
import { loadHandler, saveHandler, fetchSavedStores } from './saveLoadHandler.js';
import { convertToBlockFormat } from './jsonToBlocks.js';
import { loadSelectedStore, initializeSavedStoresDropdown } from './saveLoadHandler.js';
import { getConfig } from './config.js';

// Function to handle click events
export function handleClick(event, elements) {
    console.log('Click detected:', event.target);

    // Handle image clicks for modal display
    if (event.target.tagName === 'IMG' && event.target.id.startsWith('generated-image-')) {
        console.log('Image clicked for modal display. Image ID:', event.target.id);
        elements.modal.style.display = 'block';
        elements.modalImg.src = event.target.src;
        captionText.innerHTML = event.target.alt;
    }

    if (event.target.id === 'dungeonmindButton') {
        console.log('DungeonMind button clicked. Element ID:', event.target.id);
        const { DUNGEONMIND_BASE_URL } = getConfig();

        // Ensure the URL is absolute
        if (DUNGEONMIND_BASE_URL.startsWith('http://') || DUNGEONMIND_BASE_URL.startsWith('https://')) {
            window.location.href = DUNGEONMIND_BASE_URL;
        } else {
            // If it doesn't start with a protocol, assume http://
            window.location.href = `http://${DUNGEONMIND_BASE_URL}`;
        }
    }

    if (event.target.id === 'loginButton') {
        console.log('Login button clicked. Element ID:', event.target.id);
        window.location.href = '/auth/login';
    }

    if (event.target.id === 'logoutButton') {
        console.log('Logout button clicked. Element ID:', event.target.id);
        resetState();
        window.location.href = '/auth/logout';
    }
    // Handle modal close button
    if (event.target.id === 'closeModal') {
        // console.log('Close button clicked for modal. Element ID:', event.target.id);
        elements.modal.style.display = "none";
    }

    // Handle modal close when clicking outside of the modal content
    if (event.target === elements.modal) {
        // console.log('Clicked outside of modal content, closing modal.');
        elements.modal.style.display = "none";
    }
    // Handle print button click
    if (event.target.id === 'printButton') {
        // console.log('Print button clicked. Element ID:', event.target.id);
        printScreen();
    }
    // Handle generate image button click

    const button = event.target.closest('.generate-image-button');

    if (button) {
        const blockId = button.getAttribute('data-block-id');
        // console.log('Generate image button clicked. Block ID:', blockId);
        generateImage(blockId);
    }

    // Handle page add button
    if (event.target.id === 'addPageButton') {
        // console.log('Add page button clicked. Element ID:', event.target.id);
        addPage(elements);
    }

    // Handle page remove button
    if (event.target.id === 'removePageButton') {
        // console.log('Remove page button clicked. Element ID:', event.target.id);
        removePage(elements);
    }

    // Handle toggle button click
    if (event.target.id === 'toggleButton') {
        // console.log('Toggle button clicked. Element ID:', event.target.id);
        toggleAllTextBlocks();
    }

    // Handle autofill button click
    if (event.target.id === 'autofillButton') {
        // console.log('Autofill button clicked. Element ID:', event.target.id);
        autofillBlocks(elements);
    }

    // Handle reset button click
    if (event.target.id === 'resetButton') {
        // console.log('Reset button clicked. Element ID:', event.target.id);
        handleReset(elements);
    }

    // Handle reset button click
    if (event.target.id === 'saveButton') {
        saveHandler();
        // console.log('Save button clicked. Element ID:', event.target.id);
    }

    // Handle load button click
    if (event.target.id === 'loadButton') {
        // console.log('Load button clicked. Element ID:', event.target.id);
        loadSelectedStore();

    }

    if (event.target.id === 'submitButton') {
        let state = getState();
        // console.log('Submit description button clicked. Element ID:', event.target.id);
        const userInput = document.getElementById('user-description').value;
        elements.blockContainerPage.innerHTML = ''; // Clear the block container before inserting new blocks
        startLoadingAnimation();
        // console.log('State before:', state);


        fetch('store/process-description', {

            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ user_input: userInput })
        })
            .then(response => response.json())
            .then(data => {
                // console.log('Success:', data);
                // Store the llm_output in the state for future use



                updateState('jsonData', convertToBlockFormat(data.llm_output));

                // console.log('State after:', state.jsonData);
                state.initialPositions.length = 0; // Clear the initialPositions array
                loadHandler();
                storeInitialPositions(elements.blockContainer);
            })
            .catch((error) => {
                // console.error('Error:', error);
            })
            .finally(() => {
                stopLoadingAnimation();
            });
    }
}

// Function to generate image
export function generateImage(blockId) {
    let state = getState();

    // Check if state.jsonData exists
    if (!state.jsonData) {
        // console.error('Error: jsonData is undefined in the state.');
        return;
    }

    // Check if the blockId exists in jsonData
    let block = state.jsonData.storeData[blockId];
    if (!block) {
        // console.error(`Error: No block found with ID ${blockId} in jsonData.`);
        return;
    }

    // Get the elements related to the block
    const sdPromptElement = document.getElementById(`sd-prompt-${blockId}`);
    const imageElement = document.getElementById(`generated-image-${blockId}`);

    // Check if the required elements exist
    if (!sdPromptElement) {
        // console.error(`Error: Element with ID sd-prompt-${blockId} not found.`);
        return;
    }

    if (!imageElement) {
        // console.error(`Error: Element with ID generated-image-${blockId} not found.`);
        return;
    }

    // Get the prompt text
    const sdPrompt = sdPromptElement.value;
    // console.log('sdPrompt:', sdPrompt);

    // Proceed with generating the image
    fetch('store/generate-image', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ sd_prompt: sdPrompt })
    })
        .then(response => {
            // Check if response is OK (status 200-299)
            if (!response.ok) {
                throw new Error(`Server error: ${response.status} ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            // Check if the data contains the image URL
            if (!data.image_url) {
                throw new Error('Error: Image URL not found in the response.');
            }

            // Update the block and the image element
            block['imgUrl'] = data.image_url;
            block['isNewImage'] = true;
            imageElement.src = data.image_url;
            imageElement.style.display = 'block';

            // Log the updated image element's HTML structure
            // console.log('Updated imageElement HTML:', imageElement.outerHTML);
        })
        .catch((error) => {
            // Catch and log any errors
            // console.error('Error:', error.message || error);
        });
}


export function setupEventListeners(elements) {
    // Click event listener
    document.addEventListener('click', (event) => handleClick(event, elements));
    // Event listeners for drag and drop functionality
    elements.blockContainer.addEventListener('dragover', handleDragOver);

    // Use an anonymous function to pass elements to handleDrop
    elements.blockContainer.addEventListener('drop', (event) => handleDrop(event, elements));
    elements.pageContainer.addEventListener('dragover', handleDragOver);
    elements.pageContainer.addEventListener('drop', (event) => handleDrop(event, elements));

    // Event listeners for trash area
    elements.trashArea.addEventListener('dragover', handleTrashOver);
    elements.trashArea.addEventListener('dragleave', handleTrashLeave);
    elements.trashArea.addEventListener('drop', (event) => handleTrashDrop(event, elements));

    // Add this line to initialize the dropdown when the page loads
    initializeSavedStoresDropdown();
}

