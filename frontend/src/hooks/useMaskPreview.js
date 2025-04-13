import { useState, useCallback, useMemo } from "react";

/**
 * Custom hook for handling mask preview generation and URL management
 */
export default function useMaskPreview(baseURL, imageData) {
  const [previewMask, setPreviewMask] = useState(null);
  const [previewBase64Image, setPreviewBase64Image] = useState(null);
  const [isGenerating, setIsGenerating] = useState(false);

  // Generate base64 preview from RLE data
  const generateBase64Preview = useCallback(async (rleData) => {
    if (!rleData) {
      console.warn("Cannot generate base64 preview: No RLE data provided");
      return;
    }

    try {
      console.log("Generating base64 preview for mask");

      // Ensure rleData is properly formatted
      if (!rleData.counts || !rleData.size) {
        console.warn("RLE data is missing counts or size, creating valid placeholder");
        rleData = {
          counts: "0",
          size: [imageData.height || 600, imageData.width || 800]
        };
      }

      const previewResponse = await fetch(`${baseURL}/mask/render-preview-base64`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          image_path: imageData.image_path,
          rle_data: rleData,
          overlay: true
        })
      });

      if (previewResponse.ok) {
        const previewResult = await previewResponse.json();
        if (previewResult.success && previewResult.base64_image) {
          console.log("Received base64 preview image");
          setPreviewBase64Image(previewResult.base64_image);
        } else {
          console.error("Base64 preview failed:", previewResult.error || "Unknown error");

          // If we got an error response but with a fallback image, use it
          if (previewResult.base64_image) {
            console.log("Using fallback base64 image from error response");
            setPreviewBase64Image(previewResult.base64_image);
          }
        }
      } else {
        console.error("Base64 preview request failed:", previewResponse.statusText);

        // Try the debug endpoint as fallback
        const debugResponse = await fetch(`${baseURL}/mask/debug-render-test?image_path=${encodeURIComponent(imageData.image_path)}&t=${Date.now()}`);
        if (debugResponse.ok) {
          const debugResult = await debugResponse.json();
          if (debugResult.base64_image) {
            console.log("Using debug fallback image");
            setPreviewBase64Image(debugResult.base64_image);
          }
        }
      }
    } catch (previewErr) {
      console.error("Error getting base64 preview:", previewErr);
    }
  }, [baseURL, imageData]);

  // Create a debounced version of generateBase64Preview to avoid excessive API calls
  const debouncedGeneratePreview = useCallback((rleData) => {
    // Clear any pending timeouts
    if (window.previewTimeoutId) {
      clearTimeout(window.previewTimeoutId);
    }

    // Set a new timeout
    window.previewTimeoutId = setTimeout(() => {
      generateBase64Preview(rleData);
    }, 500); // 500ms debounce time
  }, [generateBase64Preview]);

  // URL for preview mask with proper encoding
  const previewMaskUrl = useMemo(() => {
    // Only generate URL when there is valid data and not during active generation
    if (!previewMask || !previewMask.rleData || isGenerating) {
      return null;
    }

    // Ensure proper URL encoding
    const encodedPath = encodeURIComponent(imageData.image_path);
    const encodedRle = encodeURIComponent(previewMask.rleData);
    const url = `${baseURL}/mask/render-preview?overlay=true&image_path=${encodedPath}&rle_data=${encodedRle}&t=${previewMask.timestamp || Date.now()}`;

    console.log("Generated preview mask URL");
    return url;
  }, [baseURL, imageData?.image_path, previewMask, isGenerating]);

  // Add a backup preview URL that uses our debug endpoint
  const debugPreviewUrl = useMemo(() => {
    // Only generate when needed and not excessively
    if (!imageData || previewMaskUrl) return null;

    const url = `${baseURL}/mask/debug-render-test?image_path=${encodeURIComponent(imageData.image_path)}&t=${Date.now()}`;
    return url;
  }, [baseURL, imageData, previewMaskUrl]);

  // Create URL for viewing masks
  const getMaskUrl = useCallback((masks, activeMaskIndex, activePart) => {
    if (activeMaskIndex === null || activeMaskIndex === undefined || !masks[activeMaskIndex]?.rle) {
      return null;
    }

    // Generate URL for the mask
    let url = `${baseURL}/mask/render-mask?image_path=${encodeURIComponent(imageData.image_path)}`;

    // Always use activePart for the parts parameter
    url += `&parts=${encodeURIComponent(activePart)}`;

    // Add timestamp to prevent caching
    const timestamp = masks[activeMaskIndex].timestamp || Date.now();
    url += `&t=${timestamp}`;

    return url;
  }, [baseURL, imageData?.image_path]);

  // Function to update the preview with a new RLE
  const updateMaskPreview = useCallback((rle) => {
    if (!rle) {
      setPreviewMask(null);
      setPreviewBase64Image(null);
      return;
    }

    // Validate the RLE data to ensure it's properly formatted
    if (!rle.counts || !rle.size) {
      console.warn("Invalid RLE data received - missing counts or size", rle);
      // Don't attempt to preview invalid RLE data
      return;
    }

    const timestamp = Date.now();

    // Make a clean copy of the RLE data without any extra fields
    const cleanRle = {
      counts: rle.counts,
      size: rle.size
    };

    setPreviewMask({
      rleData: JSON.stringify(cleanRle),
      timestamp,
      requestId: timestamp
    });

    debouncedGeneratePreview(cleanRle);
  }, [debouncedGeneratePreview]);

  // Function to clear the preview
  const clearPreview = useCallback(() => {
    setPreviewMask(null);
    setPreviewBase64Image(null);
  }, []);

  return {
    previewMask,
    previewBase64Image,
    previewMaskUrl,
    debugPreviewUrl,
    isGenerating,
    setIsGenerating,
    generateBase64Preview,
    debouncedGeneratePreview,
    getMaskUrl,
    updateMaskPreview,
    clearPreview,
    setPreviewMask
  };
}