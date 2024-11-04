// main.js

import { initializeDOMElements, initialLoadJSON } from './domInit.js';
import { getState, updateState } from './state.js';
import { setupEventListeners } from './eventHandlers.js';
import { loadHandler } from './saveLoadHandler.js';
import { fetchLoadingImages } from './loadingImage.js';
import { loadConfig, getConfig } from './config.js';

let config;

// Function to check authentication status and update UI
async function checkAuthAndUpdateUI() {
    // console.log('Checking authentication status');
    console.log('DUNGEONMIND_API_URL:', config.DUNGEONMIND_API_URL);
    try {
        const response = await fetch(`${config.DUNGEONMIND_API_URL}/auth/current-user`, {
            credentials: 'include'
        });
        if (response.ok) {
            // User is authenticated
            const userData = await response.json();
            // console.log('Response:', response);
            // console.log('User authenticated:', userData);
            document.getElementById('loginButton').style.display = 'none';
            document.getElementById('logoutButton').style.display = 'inline-block';
            document.getElementById('saveButton').style.display = 'inline-block';
            document.getElementById('loadButton').style.display = 'inline-block';
            document.getElementById('savedStoresDropdown').style.display = 'inline-block';
            // Optionally, update UI with user info (e.g., display user's name)
        } else {
            // User is not authenticated
            // console.log('Response:', response);
            console.log('User not authenticated');
            document.getElementById('loginButton').style.display = 'inline-block';
            document.getElementById('logoutButton').style.display = 'none';
            document.getElementById('saveButton').style.display = 'none';
            document.getElementById('loadButton').style.display = 'none';
            document.getElementById('savedStoresDropdown').style.display = 'none';
        }
    } catch (error) {
        console.error('Error checking authentication status:', error);
    }
}
document.addEventListener('DOMContentLoaded', async function () {
    // Initialize DOM elements
    config = getConfig();
    checkAuthAndUpdateUI();
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
        loadHandler();
    } catch (error) {
        console.error('Error loading JSON:', error);
    }


});

