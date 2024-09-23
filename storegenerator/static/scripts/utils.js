import { getState } from './state.js';
import { addPage } from './pageHandler.js';
import { initializeTextareaResizing } from './handleTextareas.js';
import { loadHandler } from './saveLoadHandler.js';

export function handleReset(elements) {
    console.log('Reset button clicked');
    const state = getState();
    // Clear blockContainer before reinserting blocks
    let blockPage = document.getElementById('block-page');
    console.log('blockPage:', blockPage);
    blockPage.innerHTML = '';
    console.log('Current initial positions:', state.initialPositions);
    loadHandler();

    // Remove all pages except the first one
    let pageContainer = document.getElementById('pages');
    let pages = pageContainer.querySelectorAll('.page');
    console.log('Pages:', pages);
    pages.forEach(page => {
        page.remove();
    }
    );
    let currentPage = pageContainer.querySelector('.page');
    console.log('Current page:', currentPage);
    // If no existing page is found, create the first page
    if (!currentPage) {
        currentPage = addPage(elements);
        currentPage.setAttribute('data-page-id', 'page-0');
        console.log('No existing pages found. Created the first page:', currentPage.id);
    }
    // 


    console.log('Reset complete, all blocks moved back to block-container');
    initializeTextareaResizing();
}

export function printScreen() {
    window.print()
}
// function to clear all blocks to prepare for a load
export function clearBlocks() {
    let blockPage = document.getElementById('block-page');
    blockPage.innerHTML = '';
    console.log('Block page cleared');
    // Remove all pages except the first one
    let pageContainer = document.getElementById('pages');
    let pages = pageContainer.querySelectorAll('.page');
    console.log('Pages:', pages);
    pages.forEach(page => {
        page.remove();
    }
    );
    let currentPage = pageContainer.querySelector('.page');
    console.log('Current page:', currentPage);
    // If no existing page is found, create the first page
    const elements = buildElements();
    if (!currentPage) {
        currentPage = addPage(elements);
        currentPage.setAttribute('data-page-id', 'page-0');
        console.log('No existing pages found. Created the first page:', currentPage.id);
    }
}

export function buildElements() {
    const elements = {};
    elements.blockContainer = document.getElementById('blockContainer');
    elements.blockContainerPage = document.getElementById('block-page');
    elements.pageContainer = document.getElementById('pages');
    elements.trashArea = document.getElementById('trashArea');
    elements.currentPage = elements.pageContainer ? elements.pageContainer.querySelector('.block.monster.frame.wide') : null;
    elements.modal = document.getElementById('imageModal');
    elements.modalImg = document.getElementById('modalImage');
    elements.captionText = document.getElementById('caption');
    elements.closeModal = document.getElementsByClassName('close')[0];
    elements.loadingImage = document.getElementById('loadingImage');
    return elements;
}


