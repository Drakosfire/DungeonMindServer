import { getState } from './state.js';

let currentBlockContainerLoadingImageIndex = 0;
let preloadedImages = [];

// Preload images into memory
function preloadImages(imageUrls) {
    preloadedImages = imageUrls.map((url) => {
        const img = new Image();
        img.src = url;
        return img; // Return the Image object
    });
}

export function changeImage() {
    let state = getState();
    const loadingImage = document.getElementById('loadingImage');

    // Use the preloaded image objects directly
    const currentImage = preloadedImages[currentBlockContainerLoadingImageIndex];
    loadingImage.src = currentImage.src; // Use the fully-loaded image src

    currentBlockContainerLoadingImageIndex = (currentBlockContainerLoadingImageIndex + 1) % preloadedImages.length;
}

// Change the image every 500ms (0.5 seconds)
let animationInterval;

export function startLoadingAnimation() {
    console.log('Starting loading animation'); // Debug line
    document.getElementById('loadingAnimation').style.display = 'flex';
    animationInterval = setInterval(changeImage, 500);
}

export function stopLoadingAnimation() {
    console.log('Stopping loading animation'); // Debug line
    clearInterval(animationInterval);
    document.getElementById('loadingAnimation').style.display = 'none';
}

// Fetch the list of loading images from the server and preload them
export async function fetchLoadingImages() {
    try {
        const response = await fetch('/storegenerator/list-loading-images');
        if (response.ok) {
            const data = await response.json();

            // Preload images to cache
            preloadImages(data.images);
        } else {
            console.error('Failed to load loading images');
        }
    } catch (error) {
        console.error('Error fetching loading images:', error);
    }
}
