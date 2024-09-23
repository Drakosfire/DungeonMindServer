export async function uploadImages(imagesToUpload, sanitizedTitle) {
    console.log('Images to upload:', imagesToUpload);
    const uploadPromises = imagesToUpload.map(async (image) => {
        try {
            console.log('Uploading image:', image.imgUrl);
            if (!image.imgUrl) {  // Check if imgUrl is defined
                throw new Error('imgUrl is undefined for block ID: ' + image.blockId);
            }
            const formData = new FormData();
            const response = await fetch(image.imgUrl);

            if (!response.ok) {
                throw new Error(`Failed to fetch image: ${response.statusText}`);
            }

            const blob = await response.blob();
            console.log('Blob size:', blob.size);
            console.log('Blob type:', blob.type);

            // Set a proper file name with extension based on blob type
            let extension = blob.type.split('/')[1];
            if (!extension) {
                extension = 'png'; // Default to png if type not found
            }

            formData.append('image', blob, `image.${extension}`);
            formData.append('directoryName', sanitizedTitle);
            formData.append('blockId', image.blockId);

            console.log('FormData for upload:', Array.from(formData.entries()));

            return fetch('/storegenerator/upload-image', {
                method: 'POST',
                body: formData
            })
                .then(response => {
                    if (!response.ok) {
                        throw new Error('Image upload failed');
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.fileUrl) {
                        console.log('Image uploaded successfully. Url:', data.fileUrl);
                        return { blockId: image.blockId, fileUrl: data.fileUrl };
                    } else {
                        throw new Error('Error uploading image: ' + data.error);
                    }
                });
        } catch (error) {
            console.error('Error during image upload:', error);
            throw error;
        }
    });

    // Execute all uploads and return the results
    return Promise.all(uploadPromises);
}
