import React from "react";
import { Checkbox } from "./ui/checkbox";

const PartsSidebar = ({
  parts,
  activePart,
  qualityStatus,
  onPartSelect,
  onStartAnnotation,
  onSetCorrectStatus,
  onTogglePoorQuality,
  onToggleIncomplete
}) => {
  const getPartStatus = (partName) => {
    const status = qualityStatus[partName];
    if (!status) return null;
    if (status.is_correct === true) return "correct";
    if (status.is_correct === false) return "incorrect";
    return null;
  };

  return (
    <div className="bg-gray-50 p-4 rounded-md">
      <h3 className="font-medium text-gray-700 mb-3">Parts</h3>
      <div className="space-y-6 max-h-[60vh] overflow-y-auto p-2">
        {Object.entries(parts).map(([partName, part]) => {
          const status = getPartStatus(partName);
          const hasAnnotations = part.rles && part.rles.length > 0;
          const isActive = activePart === partName;

          return (
            <div
              key={partName}
              className={`rounded-md border m-1 ${!hasAnnotations ? 'border-dashed border-gray-300' : 'border-gray-200'} ${isActive ? 'ring-2 ring-blue-300 ring-offset-2' : ''}`}
            >
              <div
                onClick={() => onPartSelect(partName)}
                onDoubleClick={() => {
                  onPartSelect(partName);
                  onStartAnnotation();
                }}
                className={`p-3 cursor-pointer ${isActive ? 'bg-blue-50' : 'hover:bg-gray-100'} ${status === "correct" ? 'bg-green-50' : ''} ${status === "incorrect" ? 'bg-red-50' : ''}`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium truncate">
                      {partName.split("--part:")[1] || partName}
                    </span>
                    {!hasAnnotations && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">
                        No annotations
                      </span>
                    )}
                  </div>

                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onPartSelect(partName);
                      onStartAnnotation();
                    }}
                    className="p-1 text-xs text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50 rounded"
                  >
                    {hasAnnotations ? "Edit" : "Add"}
                  </button>
                </div>
              </div>

              {isActive && (
                <div className="p-3 bg-white border-t border-gray-200">
                  <div className="grid grid-cols-2 gap-2 mb-2">
                    <button
                      onClick={() => onSetCorrectStatus(partName, true)}
                      className={`px-2 py-1.5 text-xs rounded-md border ${qualityStatus[partName]?.is_correct === true
                        ? "bg-green-50 border-green-500 text-green-700"
                        : "border-gray-200 hover:bg-gray-50"}`}
                    >
                      ✓ Correct
                    </button>
                    <button
                      onClick={() => onSetCorrectStatus(partName, false)}
                      className={`px-2 py-1.5 text-xs rounded-md border ${qualityStatus[partName]?.is_correct === false
                        ? "bg-red-50 border-red-500 text-red-700"
                        : "border-gray-200 hover:bg-gray-50"}`}
                    >
                      ✗ Incorrect
                    </button>
                  </div>

                  <div className="flex items-center gap-2 text-xs mb-1">
                    <label className="flex items-center cursor-pointer hover:bg-gray-50 py-1 px-2 rounded w-full">
                      <Checkbox
                        className="h-3 w-3 mr-1"
                        checked={qualityStatus[partName]?.is_poor_quality || false}
                        onCheckedChange={() => onTogglePoorQuality(partName)}
                      />
                      <span>Poor Quality</span>
                    </label>
                  </div>

                  <div className="flex items-center gap-2 text-xs">
                    <label className="flex items-center cursor-pointer hover:bg-gray-50 py-1 px-2 rounded w-full">
                      <Checkbox
                        className="h-3 w-3 mr-1"
                        checked={!qualityStatus[partName]?.is_complete || false}
                        onCheckedChange={() => onToggleIncomplete(partName)}
                      />
                      <span>Incomplete</span>
                    </label>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default PartsSidebar;