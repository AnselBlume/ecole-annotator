import React from "react";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import * as apiService from "../services/api";

const ImageDisplay = ({
  imageData,
  objectLabel,
  activePart,
  onSkip,
  onSave,
  onStartAnnotation,
}) => {
  const fileName = imageData?.image_path ? imageData.image_path.split('/').pop() : '';
  const showMask = activePart && imageData?.parts[activePart]?.rles?.length > 0;

  return (
    <div className="flex flex-col items-center">
      <div className="mb-4 w-full">
        {objectLabel && (
          <h2 className="text-lg font-medium text-gray-900 mb-2">
            Object Label: <span className="font-semibold text-blue-600">{objectLabel}</span>
          </h2>
        )}
        <h2 className="text-lg font-medium text-gray-900">
          Current Image: <span className="font-mono text-sm bg-gray-100 px-2 py-1 rounded">{fileName}</span>
        </h2>
      </div>

      {showMask ? (
        <div className="relative">
          <img
            src={apiService.getMaskImageUrl(imageData.image_path, activePart)}
            alt="Selected mask"
            className="max-w-full max-h-[60vh] object-contain border-2 border-gray-200 rounded-lg shadow-md"
            onError={(e) => {
              console.error("Error loading mask image");
              e.target.style.display = 'none';
              const parent = e.target.parentElement;
              if (parent) {
                // Create an error message element
                const errorDiv = document.createElement('div');
                errorDiv.className = "flex items-center justify-center h-[60vh] w-full text-red-400 bg-red-50 rounded-lg";
                errorDiv.innerHTML = `
                  <div class="text-center">
                    <div class="text-lg font-medium mb-2">Failed to load mask</div>
                    <div class="text-sm">There was an error rendering the mask for ${activePart.split("--part:")[1] || activePart}</div>
                    <div class="mt-4">
                      <button class="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600">
                        Try Again
                      </button>
                    </div>
                  </div>
                `;
                parent.appendChild(errorDiv);

                // Add click handler to the try again button
                const tryAgainButton = errorDiv.querySelector('button');
                if (tryAgainButton) {
                  tryAgainButton.addEventListener('click', () => {
                    // Force reload the image with a cache-busting parameter
                    const newImg = document.createElement('img');
                    newImg.src = apiService.getMaskImageUrl(imageData.image_path, activePart, Date.now());
                    newImg.alt = "Selected mask";
                    newImg.className = "max-w-full max-h-[60vh] object-contain border-2 border-gray-200 rounded-lg shadow-md";

                    // Replace the error message with the new image
                    parent.replaceChild(newImg, errorDiv);
                  });
                }
              }
            }}
          />
          <div className="absolute top-2 left-2">
            <Badge variant="secondary" className="bg-white/90 shadow-sm border border-gray-200">
              {activePart.split("--part:")[1] || activePart}
            </Badge>
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center">
          <div className="relative mb-4">
            {/* Display original image without overlay */}
            <img
              src={apiService.getOriginalImageUrl(imageData.image_path)}
              alt="Original image"
              className="max-w-full max-h-[60vh] object-contain border-2 border-gray-200 rounded-lg shadow-md"
            />

            <div className="absolute top-2 left-2">
              <Badge variant="secondary" className="bg-white/90 shadow-sm border border-gray-200">
                {activePart.split("--part:")[1] || activePart}
              </Badge>
            </div>
          </div>

          {/* Add Annotation button below the image instead of as an overlay */}
          <div className="mt-2 mb-4">
            <Button
              onClick={onStartAnnotation}
              className="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
            >
              <svg className="-ml-1 mr-2 h-5 w-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" clipRule="evenodd" />
              </svg>
              Add Annotation
            </Button>
          </div>
        </div>
      )}

      {/* Action buttons below image */}
      <div className="mt-6 grid grid-cols-2 gap-3 max-w-md w-full">
        <Button
          onClick={onSkip}
          variant="outline"
          className="bg-gray-50 hover:bg-gray-100 border-gray-300 text-gray-700 font-medium shadow-sm"
        >
          Skip
        </Button>
        <Button
          onClick={onSave}
          className="bg-indigo-600 hover:bg-indigo-700 text-white font-medium shadow-md transition-all duration-200 ease-in-out border border-indigo-700 hover:shadow-lg"
        >
          Save and Next
        </Button>
      </div>
    </div>
  );
};

export default ImageDisplay;