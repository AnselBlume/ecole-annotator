import { useCallback } from "react";
import { Button } from "./ui/button";

/**
 * MaskSelector component handles the selection and management of masks
 * in the annotation interface.
 */
export default function MaskSelector({
  masks,
  activeMaskIndex,
  setActiveMaskIndex,
  setMasks,
  onPreviewMask,
  clearPreview,
  activePart
}) {
  // Handle switching between different masks
  const handleMaskChange = useCallback((index, mask) => {
    console.log(`Switching to mask ${index + 1}`);
    setActiveMaskIndex(index);

    // If the mask has RLE data, update the UI to show it
    if (mask.rle) {
      console.log(`Mask ${index + 1} has RLE data, displaying it`);

      // Use debouncing to prevent multiple calls
      if (window.maskSwitchTimeoutId) {
        clearTimeout(window.maskSwitchTimeoutId);
      }

      window.maskSwitchTimeoutId = setTimeout(() => {
        onPreviewMask(mask.rle);
      }, 300);
    } else {
      console.log(`Mask ${index + 1} has no RLE data`);
      clearPreview();
    }
  }, [setActiveMaskIndex, onPreviewMask, clearPreview]);

  // Add a new empty mask
  const handleAddMask = useCallback(() => {
    // Clear previews first
    clearPreview();

    console.log("Adding new mask");
    const newMaskIndex = masks.length;

    // Create new mask without triggering preview
    setMasks([...masks, {
      id: `new-${newMaskIndex}`,
      isExisting: false,
      timestamp: Date.now(),
      partName: activePart,
      name: `${activePart} ${newMaskIndex + 1}`,
      rle: null // Ensure it's empty
    }]);

    // Change active index after a short delay to prevent race conditions
    setTimeout(() => {
      setActiveMaskIndex(newMaskIndex);
    }, 50);
  }, [masks, setMasks, setActiveMaskIndex, clearPreview, activePart]);

  // Delete the current mask
  const handleDeleteMask = useCallback(() => {
    if (masks.length <= 1) {
      // Create a single empty mask to replace the current one
      // (instead of just clearing the existing one)
      clearPreview();
      setMasks([{
        id: `new-${Date.now()}`,
        rle: null,
        isExisting: false,
        partName: activePart
      }]);
      setActiveMaskIndex(0);
      return;
    }

    console.log(`Deleting mask ${activeMaskIndex + 1}`);
    const newMasks = [...masks];
    newMasks.splice(activeMaskIndex, 1);

    const newIndex = Math.min(activeMaskIndex, newMasks.length - 1);
    setMasks(newMasks);

    // Clear preview first to avoid flashing
    clearPreview();

    // Change active index
    setActiveMaskIndex(newIndex);

    // Update preview if necessary after a short delay
    setTimeout(() => {
      if (newMasks[newIndex]?.rle) {
        console.log(`Switching to mask ${newIndex + 1} after deletion`);
        onPreviewMask(newMasks[newIndex].rle);
      }
    }, 50);
  }, [masks, activeMaskIndex, setMasks, setActiveMaskIndex, clearPreview, onPreviewMask, activePart]);

  // Clear the current mask data
  const handleClearMask = useCallback(() => {
    console.log(`Clearing mask ${activeMaskIndex + 1}`);
    const newMasks = [...masks];
    // Keep the part name but remove RLE data
    newMasks[activeMaskIndex] = {
      ...newMasks[activeMaskIndex],
      rle: null,
      timestamp: Date.now()
    };
    setMasks(newMasks);
    clearPreview();
  }, [masks, activeMaskIndex, setMasks, clearPreview]);

  return (
    <div className="flex items-center gap-2 mb-4">
      <div className="flex-1">
        <div className="text-sm font-medium mb-1">Active Mask: {activeMaskIndex + 1}</div>
        <div className="flex gap-2 overflow-x-auto pb-1 mask-selector">
          {masks.map((mask, index) => (
            <Button
              key={index}
              variant={activeMaskIndex === index ? "default" : "outline"}
              size="sm"
              className={`min-w-fit ${mask.isExisting ? "border-blue-500" : ""} ${
                activeMaskIndex === index ? "bg-blue-600 text-white" : ""
              }`}
              onClick={() => handleMaskChange(index, mask)}
            >
              {mask.isExisting && "📌"} Mask {index + 1}
            </Button>
          ))}
          <Button
            variant="secondary"
            size="sm"
            onClick={handleAddMask}
          >
            + Add Mask
          </Button>
        </div>
      </div>

      {/* Action buttons for the current mask */}
      <div className="flex flex-col gap-1">
        <Button
          variant="outline"
          size="sm"
          onClick={handleDeleteMask}
          className="text-red-500 border-red-300 hover:bg-red-50 hover:text-red-600"
        >
          Delete Mask
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={handleClearMask}
        >
          Clear Mask
        </Button>
      </div>
    </div>
  );
}