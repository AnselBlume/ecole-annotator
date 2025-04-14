import { useState, useEffect, useCallback } from "react"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "./ui/tabs"
import AnnotationCanvas from "./AnnotationCanvas"
import { Button } from "./ui/button"
import MaskSelector from "./MaskSelector"
import MaskPreview from "./MaskPreview"
import useMaskPreview from "../hooks/useMaskPreview"

/**
 * ModularAnnotationMode - A refactored version of AnnotationMode that uses
 * modular components to fix issues with excessive API calls and ESLint errors
 */
export default function ModularAnnotationMode({
  imageData,
  activePart,
  baseURL,
  onUpdateAnnotation,
  onCancel
}) {
  // Local state
  const [activeTab, setActiveTab] = useState("sam2")
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [masks, setMasks] = useState([])
  const [activeMaskIndex, setActiveMaskIndex] = useState(0)
  const [pointsForMasks, setPointsForMasks] = useState({})

  // Use custom hook for preview handling
  const {
    previewMask,
    previewBase64Image,
    previewMaskUrl,
    debugPreviewUrl,
    isGenerating,
    setIsGenerating,
    updateMaskPreview,
    clearPreview,
    getMaskUrl: getUrlForMask
  } = useMaskPreview(baseURL, imageData)

  // Helper function to get mask URL with the correct parameters
  const getMaskUrl = useCallback((maskIndex) => {
    return getUrlForMask(masks, maskIndex, activePart);
  }, [getUrlForMask, masks, activePart]);

  // Load existing masks on component mount - with proper dependencies
  useEffect(() => {
    // Prevent infinite re-renders with a simple check
    const alreadyLoaded = masks.length > 0 &&
      masks.some(m => m.partName === activePart);

    if (alreadyLoaded) {
      return; // Skip if we've already loaded masks for this part
    }

    if (imageData?.parts?.[activePart]?.rles?.length > 0) {
      console.log(`Loading ${imageData.parts[activePart].rles.length} existing masks for ${activePart}`);

      const existingMasks = imageData.parts[activePart].rles.map((rle, index) => ({
        id: `existing-${index}`,
        rle: rle,
        isExisting: true,
        timestamp: Date.now(),
        partName: activePart
      }));

      setMasks(existingMasks);
      setActiveMaskIndex(0);

      // Show the first mask after a brief delay to ensure state is updated
      const initialRle = existingMasks[0]?.rle;
      if (initialRle) {
        // Use timeout to avoid render loop
        const timer = setTimeout(() => {
          updateMaskPreview(initialRle);
        }, 100);

        return () => clearTimeout(timer);
      }
    } else {
      console.log(`No existing masks for ${activePart}, creating empty mask`);
      setMasks([{
        id: 'new-0',
        rle: null,
        isExisting: false,
        partName: activePart
      }]);
    }
  }, [imageData, activePart, updateMaskPreview]);

  // Handle point prompts
  const handleSavePoints = async (points) => {
    setIsLoading(true);
    setError(null);

    try {
      // Validate that we have at least one point
      if (!points.positivePoints || points.positivePoints.length === 0) {
        throw new Error("Please add at least one positive point");
      }

      console.log("Sending points to backend:", {
        positive: points.positivePoints,
        negative: points.negativePoints
      });

      const response = await fetch(`${baseURL}/annotate/generate-mask-from-points`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          image_path: imageData.image_path,
          part_name: activePart,
          positive_points: points.positivePoints,
          negative_points: points.negativePoints
        })
      });

      if (!response.ok) {
        const errorText = await response.text();
        console.error("Backend error response:", errorText);
        throw new Error(`Failed to generate mask: ${response.status} ${response.statusText}`);
      }

      const result = await response.json();
      console.log("Received result from backend:", result);

      // Validate the RLE data
      if (!result.rle) {
        console.error("Missing RLE data in server response");
        throw new Error("Server response missing RLE data");
      }

      // Log the RLE data structure for debugging
      console.log("RLE data structure:", {
        hasRle: !!result.rle,
        hasCounts: !!result.rle?.counts,
        hasSize: !!result.rle?.size,
        countsType: typeof result.rle?.counts,
        sizeType: typeof result.rle?.size,
        size: result.rle?.size
      });

      if (!result.rle.counts || !result.rle.size) {
        console.error("Invalid RLE data received from server:", result.rle);

        // Check if we have image dimensions to create a fallback
        if (imageData && imageData.width && imageData.height) {
          console.log("Creating fallback empty mask with correct dimensions");

          // Create an empty mask with the correct dimensions
          const fallbackRle = {
            counts: "0", // Empty mask RLE
            size: [imageData.height, imageData.width]
          };

          // Update the UI with this fallback
          const newMasks = [...masks];
          newMasks[activeMaskIndex] = {
            ...newMasks[activeMaskIndex],
            rle: fallbackRle,
            isExisting: false,
            timestamp: Date.now(),
            isFallback: true // Mark as fallback for reference
          };

          setMasks(newMasks);
          clearPreview();

          // Show fallback preview
          setTimeout(() => {
            updateMaskPreview(fallbackRle);
          }, 100);

          // Show a more informative error
          setError("Could not generate mask from selected points. Try different points or adding more points.");
          setIsLoading(false);
          return;
        } else {
          throw new Error("Server returned invalid mask data and no fallback could be created");
        }
      }

      // Create a clean RLE object with only the required fields
      const cleanRle = {
        counts: result.rle.counts,
        size: Array.isArray(result.rle.size) ? result.rle.size : [result.rle.size[0], result.rle.size[1]]
      };

      console.log("Created clean RLE object:", cleanRle);

      // Save points for this mask
      setPointsForMasks(prev => ({
        ...prev,
        [activeMaskIndex]: {
          positivePoints: points.positivePoints,
          negativePoints: points.negativePoints
        }
      }));

      // Update the active mask
      const newMasks = [...masks];
      newMasks[activeMaskIndex] = {
        ...newMasks[activeMaskIndex],
        rle: cleanRle,
        isExisting: false,
        timestamp: Date.now()
      };

      setMasks(newMasks);
      clearPreview();

      // Show the new preview
      setTimeout(() => {
        updateMaskPreview(cleanRle);
      }, 100);
    } catch (err) {
      console.error("Error generating mask from points:", err);
      setError(err.message || "Failed to generate mask");
    } finally {
      setIsLoading(false);
    }
  };

  // Handle polygon mask generation
  const handleSavePolygon = async (polygon) => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(`${baseURL}/annotate/generate-mask-from-polygon`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          image_path: imageData.image_path,
          part_name: activePart,
          polygon_points: polygon.polygonPoints
        })
      });

      if (!response.ok) {
        throw new Error(`Failed to generate mask: ${response.statusText}`);
      }

      const result = await response.json();

      // Validate the RLE data
      if (!result.rle || !result.rle.counts || !result.rle.size) {
        console.error("Invalid RLE data received from server:", result.rle);
        throw new Error("Server returned invalid mask data");
      }

      // Create a clean RLE object with only the required fields
      const cleanRle = {
        counts: result.rle.counts,
        size: result.rle.size
      };

      // Save points for this mask
      setPointsForMasks(prev => ({
        ...prev,
        [activeMaskIndex]: {
          polygonPoints: polygon.polygonPoints
        }
      }));

      // Update the mask list
      const newMasks = [...masks];
      newMasks[activeMaskIndex] = {
        ...newMasks[activeMaskIndex],
        rle: cleanRle,
        isExisting: false,
        timestamp: Date.now()
      };

      setMasks(newMasks);
      clearPreview();

      // Show the updated mask
      setTimeout(() => {
        updateMaskPreview(cleanRle);
      }, 100);
    } catch (err) {
      console.error("Error generating mask from polygon:", err);
      setError(err.message || "Failed to generate mask");
    } finally {
      setIsLoading(false);
    }
  };

  // Generate polygon mask for preview
  const generatePolygonMask = async (points) => {
    if (points.length < 3 || isGenerating) {
      console.log("Not enough points or already generating");
      return null;
    }

    try {
      setIsGenerating(true);
      console.log("Generating polygon mask preview");

      // Format points for the backend
      const formattedPoints = points.map(p => [Math.round(p.x), Math.round(p.y)]);

      const response = await fetch(`${baseURL}/mask/generate-from-polygon`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image_path: imageData.image_path,
          points: formattedPoints
        })
      });

      if (!response.ok) {
        throw new Error(`Polygon mask generation failed: ${response.status}`);
      }

      const result = await response.json();

      if (result.success && result.rle) {
        console.log("Received RLE data from polygon API");

        // Validate RLE structure
        if (!result.rle.counts || !result.rle.size) {
          console.warn("Invalid RLE data received from polygon API, creating placeholder");

          // Create a valid placeholder RLE with empty mask
          return {
            counts: "0",
            size: [imageData.height || 315, imageData.width || 474]
          };
        }

        // Return a clean RLE object with only the essential fields
        return {
          counts: result.rle.counts,
          size: result.rle.size
        };
      } else {
        console.error("Invalid response from polygon API");
        setError("Failed to generate polygon mask");
        return null;
      }
    } catch (error) {
      console.error("Error generating polygon mask:", error);
      setError(`Error generating polygon mask: ${error.message}`);
      return null;
    } finally {
      setIsGenerating(false);
    }
  };

  // Handle preview mask generation
  const handlePreviewMask = async (data) => {
    try {
      let rle = null;

      if (data.polygonPoints && data.polygonPoints.length >= 3) {
        rle = await generatePolygonMask(data.polygonPoints);
      } else if (data.positivePoints && data.positivePoints.length > 0) {
        // Handle point prompts from SAM2
        console.log("Sending SAM2 point prompt for preview");

        // Prepare the request payload
        const payload = {
          image_path: imageData.image_path,
          part_name: activePart,
          positive_points: data.positivePoints,
          negative_points: data.negativePoints || []
        };

        // Add existing mask for improved prediction if available
        if (masks[activeMaskIndex]?.rle) {
          console.log("Including existing mask for improved prediction");
          payload.mask_input = masks[activeMaskIndex].rle;
        }

        const promptResult = await fetch(`${baseURL}/annotate/generate-mask-from-points`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        if (promptResult.ok) {
          const result = await promptResult.json();
          if (result.rle) {
            rle = result.rle;
          }
        }
      } else {
        console.log("No points provided for preview");
      }

      if (rle) {
        // Validate the RLE data
        if (!rle.counts || !rle.size) {
          console.warn("Invalid RLE data for preview:", rle);
          return;
        }

        // Create a clean RLE object with only the required fields
        const cleanRle = {
          counts: rle.counts,
          size: rle.size
        };

        // Update the masks array
        const updatedMasks = [...masks];
        updatedMasks[activeMaskIndex] = {
          ...updatedMasks[activeMaskIndex],
          rle: cleanRle,
          timestamp: Date.now()
        };

        setMasks(updatedMasks);

        // Update the preview
        updateMaskPreview(cleanRle);
      }
    } catch (err) {
      console.error("Error in handlePreviewMask:", err);
      setError(`Failed to generate preview: ${err.message}`);
    }
  };

  // Handle mask selection change - load points for the selected mask
  const handleMaskIndexChange = (newIndex) => {
    setActiveMaskIndex(newIndex);

    // Update the preview for the selected mask
    if (masks[newIndex]?.rle) {
      updateMaskPreview(masks[newIndex].rle);
    } else {
      clearPreview();
    }
  };

  // Save all masks to the backend
  const handleSaveAllMasks = async () => {
    setIsLoading(true);
    setError(null);

    try {
      // Get all valid masks
      const masksToSave = masks
        .filter(mask => mask.rle !== null)
        .map(mask => {
          // Ensure each RLE has counts and size
          if (!mask.rle.counts || !mask.rle.size) {
            console.warn("Skipping invalid RLE in save:", mask.rle);
            return null;
          }

          // Return an RLE object with all required fields according to the backend's RLEAnnotation type
          return {
            counts: mask.rle.counts,
            size: mask.rle.size,
            image_path: imageData.image_path,
            is_root_concept: activePart.includes("root"),
            mask_path: null
          };
        })
        .filter(rle => rle !== null); // Remove any null entries from invalid RLEs

      // We'll still proceed even if no valid masks exist, because this means the part has no annotations
      // which is a valid state we want to save

      // Create URL with query parameters for image_path and part_name
      const url = new URL(`${baseURL}/annotate/update-part-annotation`);
      url.searchParams.append('image_path', imageData.image_path);
      url.searchParams.append('part_name', activePart);

      // Log the exact data we're sending for debugging
      const requestBody = { rles: masksToSave };
      console.log("Saving part annotation with payload:", JSON.stringify(requestBody, null, 2));

      // Send the rles array in the request body as expected by the backend
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody)
      });

      if (!response.ok) {
        let errorDetail = "";
        try {
          const errorData = await response.json();
          errorDetail = errorData.detail || JSON.stringify(errorData);
        } catch (e) {
          errorDetail = response.statusText;
        }

        throw new Error(`Failed to save annotation: ${response.status} ${errorDetail}`);
      }

      await response.json();
      onUpdateAnnotation(activePart, { rles: masksToSave });
      onCancel();
    } catch (err) {
      console.error("Error saving masks:", err);
      setError(err.message || "Failed to save masks");
      setIsLoading(false);
    }
  };

  // Original image URL
  const originalImageUrl = `${baseURL}/images/${encodeURIComponent(imageData.image_path)}`;

  return (
    <div className="bg-white p-6 rounded-lg shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold">
          Annotating: <span className="text-blue-600">{activePart.split("--part:")[1] || activePart}</span>
        </h2>

        <div className="flex items-center gap-3">
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4">
          {error}
        </div>
      )}

      {/* Use MaskSelector component */}
      <MaskSelector
        masks={masks}
        activeMaskIndex={activeMaskIndex}
        setActiveMaskIndex={handleMaskIndexChange}
        setMasks={setMasks}
        onPreviewMask={updateMaskPreview}
        clearPreview={clearPreview}
        activePart={activePart}
      />

      <Tabs>
        <TabsList>
          <TabsTrigger
            value="sam2"
            activeValue={activeTab}
            onSelect={setActiveTab}
          >
            SAM2 Point Prompts
          </TabsTrigger>
          <TabsTrigger
            value="polygon"
            activeValue={activeTab}
            onSelect={setActiveTab}
          >
            Polygon Annotation
          </TabsTrigger>
        </TabsList>

        <TabsContent value="sam2" activeValue={activeTab}>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="w-full">
              <h3 className="text-sm font-medium mb-2">SAM2 Point Prompts</h3>
              <AnnotationCanvas
                imageUrl={originalImageUrl}
                mode="point_prompt"
                onSavePoints={handleSavePoints}
                onPreviewMask={handlePreviewMask}
                initialPositivePoints={pointsForMasks[activeMaskIndex]?.positivePoints || []}
                initialNegativePoints={pointsForMasks[activeMaskIndex]?.negativePoints || []}
                className="w-full"
              />
              <div className="mt-4 text-xs text-gray-500">
                <p>Add positive points (green) by left-clicking where the object is located.</p>
                <p>Add negative points (red) by right-clicking where the object is not located.</p>
              </div>
            </div>

            {/* Use MaskPreview component */}
            <MaskPreview
              isLoading={isLoading}
              masks={masks}
              activeMaskIndex={activeMaskIndex}
              previewMask={previewMask}
              previewBase64Image={previewBase64Image}
              previewMaskUrl={previewMaskUrl}
              debugPreviewUrl={debugPreviewUrl}
              activeTab={activeTab}
              getMaskUrl={getMaskUrl}
            />
          </div>
        </TabsContent>

        <TabsContent value="polygon" activeValue={activeTab}>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="w-full">
              <h3 className="text-sm font-medium mb-2">Polygon Annotation</h3>
              <AnnotationCanvas
                imageUrl={originalImageUrl}
                mode="polygon"
                onSavePolygon={handleSavePolygon}
                onPreviewMask={handlePreviewMask}
                initialPolygonPoints={pointsForMasks[activeMaskIndex]?.polygonPoints || []}
                className="w-full"
              />
            </div>

            {/* Use MaskPreview component */}
            <MaskPreview
              isLoading={isLoading}
              masks={masks}
              activeMaskIndex={activeMaskIndex}
              previewMask={previewMask}
              previewBase64Image={previewBase64Image}
              previewMaskUrl={previewMaskUrl}
              debugPreviewUrl={debugPreviewUrl}
              activeTab={activeTab}
              getMaskUrl={getMaskUrl}
            />
          </div>
        </TabsContent>
      </Tabs>

      <div className="mt-6 flex justify-end">
        <Button
          onClick={handleSaveAllMasks}
          disabled={isLoading || !masks.some(mask => mask.rle !== null)}
          className="bg-blue-600 hover:bg-blue-700 text-white"
        >
          {isLoading ? "Saving..." : "Save All Masks"}
        </Button>
      </div>
    </div>
  );
}