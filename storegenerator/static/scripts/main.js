// main.js

import { initializeDOMElements } from './domInit.js';
import { getState, updateState } from './state.js';
import { setupEventListeners } from './eventHandlers.js';
import { loadHandler } from './saveLoadHandler.js';
import { initialLoadJSON } from './domInit.js';
import { fetchLoadingImages } from './loadingImage.js';



document.addEventListener('DOMContentLoaded', async function () {
    // Initialize DOM elements
    const elements = initializeDOMElements();
    if (!elements) {
        console.error('DOM initialization failed.');
        return;
    }

    // Set up initial state
    const state = getState();
    fetchLoadingImages();
    setupEventListeners(elements); // Set up event listeners after DOM initialization
    //     extractBlocks(elements);
    try {
        // Wait for the JSON to load into the state
        await initialLoadJSON();  // Ensure JSON is loaded into the state before proceeding

        // Call loadHandler after JSON is loaded
        loadHandler(elements);
    } catch (error) {
        console.error('Error loading JSON:', error);
    }

});
