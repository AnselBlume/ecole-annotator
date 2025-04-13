/**
 * MaskPreview component handles displaying the mask preview in the annotation interface
 */
export default function MaskPreview({
  isLoading,
  masks,
  activeMaskIndex,
  previewMask,
  previewBase64Image,
  previewMaskUrl,
  debugPreviewUrl,
  activeTab,
  getMaskUrl
}) {
  // Container and image styles
  const previewContainerStyle = {
    position: 'relative',
    width: '100%',
    height: '100%',
    border: '1px solid #ccc',
    overflow: 'hidden',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#f5f5f5'
  };

  const previewImageStyle = {
    position: 'absolute',
    top: 0,
    left: 0,
    width: '100%',
    height: '100%',
    objectFit: 'contain',
    opacity: 1,
    zIndex: 10
  };

  // Determine what content to show in the preview
  const renderPreviewContent = () => {
    if (isLoading) {
      return (
        <div className="absolute inset-0 flex items-center justify-center">
          <p className="text-muted-foreground">Generating preview...</p>
        </div>
      );
    }

    // Show existing mask
    if (masks[activeMaskIndex]?.rle && !previewMask) {
      return (
        <div style={previewContainerStyle}>
          <img
            key={`mask-${activeMaskIndex}-${masks[activeMaskIndex].timestamp || 'default'}`}
            src={getMaskUrl(activeMaskIndex)}
            alt={`Mask ${activeMaskIndex + 1}`}
            style={previewImageStyle}
            onLoad={() => console.log(`Loaded existing mask ${activeMaskIndex + 1}`)}
            onError={(e) => console.error(`Failed to load mask ${activeMaskIndex + 1}:`, e)}
          />
          {masks[activeMaskIndex].isExisting && (
            <div className="absolute top-2 left-2 bg-blue-500 text-white text-xs px-2 py-1 rounded-full">
              Existing Mask
            </div>
          )}
        </div>
      );
    }

    // Show base64 preview image
    if (previewBase64Image) {
      return (
        <div style={previewContainerStyle}>
          <img
            key={previewMask?.timestamp || 'no-preview'}
            src={previewBase64Image}
            alt="Mask Preview"
            style={previewImageStyle}
            onLoad={() => console.log("Base64 preview image loaded successfully!")}
          />
        </div>
      );
    }

    // Show URL-based preview
    if (previewMaskUrl) {
      return (
        <div style={previewContainerStyle}>
          <img
            key={previewMask?.timestamp || 'no-preview'}
            src={previewMaskUrl}
            alt="Mask Preview"
            style={previewImageStyle}
            onError={(e) => {
              console.error("Failed to load preview image:", e);
              e.target.style.display = 'none';

              // If the main preview fails, try to show the debug one
              const debugImg = document.createElement('img');
              debugImg.src = debugPreviewUrl;
              debugImg.alt = "Debug Mask Preview";
              debugImg.style.position = 'absolute';
              debugImg.style.top = '0';
              debugImg.style.left = '0';
              debugImg.style.width = '100%';
              debugImg.style.height = '100%';
              debugImg.style.objectFit = 'contain';
              const parent = e.target.parentNode;
              if (parent) {
                parent.appendChild(debugImg);

                // Add a notice that we're using debug mode
                const notice = document.createElement('div');
                notice.className = "absolute bottom-0 left-0 right-0 bg-yellow-500 text-white text-xs p-1 text-center";
                notice.textContent = "Using debug preview mode";
                parent.appendChild(notice);
              }
            }}
            onLoad={() => console.log("URL-based preview image loaded successfully!")}
          />
        </div>
      );
    }

    // Default state - no preview
    return (
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <p className="text-muted-foreground">
          {(activeTab === "sam2" && !previewMask) ? "Add positive points to see preview" :
           (activeTab === "polygon" && !previewMask) ? "Complete polygon to see preview" :
           "No preview available"}
        </p>
      </div>
    );
  };

  return (
    <div className="flex flex-col space-y-4">
      <h3 className="text-lg font-semibold">Mask Preview</h3>
      <div className="relative w-full h-72 border rounded-md overflow-hidden bg-muted">
        {renderPreviewContent()}
      </div>

      {/* Information about editing multiple masks */}
      <div className="mt-2 text-sm text-gray-600 bg-blue-50 p-3 rounded-md">
        <p className="font-medium mb-1">Working with multiple masks:</p>
        <ul className="list-disc list-inside text-xs">
          <li>Use the mask selector above to switch between different masks</li>
          <li>Each mask can be edited individually</li>
          <li>Existing masks are marked with 📌</li>
          <li>Use "Add Mask" to create additional annotations for this part</li>
        </ul>
      </div>
    </div>
  );
}