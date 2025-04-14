import { useState, useEffect } from "react"
import { Button } from "./components/ui/button"
import { Checkbox } from "./components/ui/checkbox"
import { Header } from "./components/ui/header"
import { Badge } from "./components/ui/badge"
import ModularAnnotationMode from "./components/ModularAnnotationMode"

export default function SegmentationReviewApp() {
  const [imageData, setImageData] = useState(null)
  const [activePart, setActivePart] = useState(null)
  const [qualityStatus, setQualityStatus] = useState({})
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [isAnnotating, setIsAnnotating] = useState(false)

  const baseURL = process.env.REACT_APP_BACKEND

  useEffect(() => {
    fetchNextImage()
    fetchStats()
  }, [])

  const fetchStats = async () => {
    const res = await fetch(`${baseURL}/annotate/annotation-stats`)
    const data = await res.json()
    setStats(data)
  }

  const fetchNextImage = async () => {
    setLoading(true)
    const res = await fetch(`${baseURL}/queue/next-image`)
    const data = await res.json()

    if (!data?.image_path) {
      setImageData(null)
      setLoading(false)
      return
    }

    setImageData(data)
    setActivePart(Object.keys(data.parts)[0] || null)

    const statusMap = {}
    Object.entries(data.parts).forEach(([name, part]) => {
      statusMap[name] = {
        is_poor_quality: part.is_poor_quality || false,
        is_correct: null,
        is_complete: part.is_complete !== false,
        has_existing_annotations: part.has_existing_annotations !== false
      }
    })
    setQualityStatus(statusMap)
    setLoading(false)
  }

  const setCorrectStatus = (partName, isCorrect) => {
    setQualityStatus((prev) => ({
      ...prev,
      [partName]: {
        ...prev[partName],
        is_correct: isCorrect,
      },
    }))
  }

  const togglePoorQuality = (partName) => {
    setQualityStatus((prev) => ({
      ...prev,
      [partName]: {
        ...prev[partName],
        is_poor_quality: !prev[partName].is_poor_quality,
        is_complete: prev[partName].is_complete,
      },
    }))
  }

  const toggleIncomplete = (partName) => {
    setQualityStatus((prev) => ({
      ...prev,
      [partName]: {
        ...prev[partName],
        is_complete: !prev[partName].is_complete
      },
    }))
  }

  const handleSave = async () => {
    if (!imageData) return
    setLoading(true)

    // Log the original data for debugging
    console.log("Original imageData:", JSON.stringify(imageData, null, 2));
    console.log("Quality status:", JSON.stringify(qualityStatus, null, 2));

    const updatedParts = {}
    Object.entries(imageData.parts).forEach(([name, part]) => {
      const status = qualityStatus[name] || {}
      console.log(`Part ${name}:`, part);

      // Create a copy of the part to avoid modifying the original
      const updatedPart = {
        name: name,  // Make sure name is included
        // Use existing RLEs or provide an empty array
        rles: Array.isArray(part.rles) ? part.rles : [],
        was_checked: true,
        is_poor_quality: status.is_poor_quality || false,
        is_correct: status.is_correct === null ? true : status.is_correct, // Default to true if null
        is_complete: status.is_complete === undefined ? true : status.is_complete,
        has_existing_annotations: part.has_existing_annotations !== false // Preserve the flag
      };

      updatedParts[name] = updatedPart;
    })

    const payload = {
      image_path: imageData.image_path,
      parts: updatedParts,
    }

    try {
      const response = await fetch(`${baseURL}/annotate/save-annotation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        console.error(`Error saving annotation: ${response.status} ${response.statusText}`);
        const errorText = await response.text();
        console.error(`Error details: ${errorText}`);
        return;
      }

      // Only fetch next image and stats if save was successful
      fetchNextImage();
      fetchStats();
    } catch (error) {
      console.error("Failed to save annotation:", error);
    } finally {
      setLoading(false);
    }
  }

  // Get current part status
  const getPartStatus = (partName) => {
    const status = qualityStatus[partName];
    if (!status) return null;
    if (status.is_correct === true) return "correct";
    if (status.is_correct === false) return "incorrect";
    return null;
  }

  // Start annotation mode
  const handleStartAnnotation = () => {
    if (activePart) {
      setIsAnnotating(true)
    }
  }

  // Handle updated annotation
  const handleUpdateAnnotation = (partName, annotationData) => {
    // Update the image data with new RLEs
    if (imageData && partName) {
      setImageData(prevData => {
        const updatedParts = { ...prevData.parts }
        if (partName in updatedParts) {
          updatedParts[partName] = {
            ...updatedParts[partName],
            ...(annotationData.rles && { rles: annotationData.rles })
          }
        }
        return {
          ...prevData,
          parts: updatedParts
        }
      })
    }
  }

  const showMask = activePart && imageData?.parts[activePart]?.rles?.length > 0
  const fileName = imageData?.image_path ? imageData.image_path.split('/').pop() : '';

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Header stats={stats} />
        <div className="flex items-center justify-center h-[80vh]">
          <div className="text-xl font-medium text-gray-700">
            Loading...
          </div>
        </div>
      </div>
    )
  }

  if (!imageData) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Header stats={stats} />
        <div className="max-w-2xl mx-auto mt-20 text-center p-10 bg-white rounded-lg shadow-sm">
          <div className="text-5xl mb-4">🎉</div>
          <h2 className="text-2xl font-bold text-gray-800 mb-2">All Done!</h2>
          <p className="text-gray-600">No more images to annotate.</p>
        </div>
      </div>
    )
  }

  // If in annotation mode, show the annotation interface
  if (isAnnotating && activePart) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Header stats={stats} />
        <main className="max-w-7xl mx-auto py-8 px-4 sm:px-6">
          <div className="mb-4">
            <h2 className="text-lg font-medium text-gray-900">Current Image: <span className="font-mono text-sm bg-gray-100 px-2 py-1 rounded">{fileName}</span></h2>
          </div>
          <ModularAnnotationMode
            imageData={imageData}
            activePart={activePart}
            baseURL={baseURL}
            onUpdateAnnotation={handleUpdateAnnotation}
            onCancel={() => setIsAnnotating(false)}
          />
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Header stats={stats} />

      <main className="max-w-7xl mx-auto py-8 px-4 sm:px-6">
        <div className="mb-4">
          <h2 className="text-lg font-medium text-gray-900">Current Image: <span className="font-mono text-sm bg-gray-100 px-2 py-1 rounded">{fileName}</span></h2>
        </div>

        <div className="bg-white rounded-lg shadow-sm">
          <div className="grid grid-cols-1 lg:grid-cols-[1fr,300px] gap-6 p-6">
            {/* Main image display area */}
            <div className="flex flex-col items-center">
              {showMask ? (
                <div className="relative">
                  <img
                    src={`${baseURL}/mask/render-mask?image_path=${encodeURIComponent(
                      imageData.image_path
                    )}&parts=${encodeURIComponent(activePart)}&timestamp=${Date.now()}`}
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
                            newImg.src = `${baseURL}/mask/render-mask?image_path=${encodeURIComponent(
                              imageData.image_path
                            )}&parts=${encodeURIComponent(activePart)}&t=${Date.now()}`;
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
                <div className="flex flex-col items-center justify-center h-[60vh] w-full text-gray-500 bg-gray-100 rounded-lg">
                  <div className="text-center p-6">
                    <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 13h6m-3-3v6m-9 1V7a2 2 0 012-2h6l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
                    </svg>
                    <h3 className="mt-2 text-sm font-medium">No annotations for {activePart.split("--part:")[1] || activePart}</h3>
                    <p className="mt-1 text-sm text-gray-500">
                      Click the "Annotate Part" button below to create annotations for this part.
                    </p>
                    <div className="mt-6">
                      <button
                        type="button"
                        className="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                        onClick={handleStartAnnotation}
                      >
                        <svg className="-ml-1 mr-2 h-5 w-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                          <path fillRule="evenodd" d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" clipRule="evenodd" />
                        </svg>
                        Add Annotation
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Annotation controls */}
              <div className="mt-6 w-full max-w-md">
                <div className="grid grid-cols-2 gap-3 mb-4">
                  <Button
                    onClick={() => setCorrectStatus(activePart, true)}
                    variant="outline"
                    className={`h-12 ${qualityStatus[activePart]?.is_correct === true
                      ? "bg-green-50 border-green-500 text-green-700"
                      : ""}`}
                  >
                    ✓ Correct
                  </Button>
                  <Button
                    onClick={() => setCorrectStatus(activePart, false)}
                    variant="outline"
                    className={`h-12 ${qualityStatus[activePart]?.is_correct === false
                      ? "bg-red-50 border-red-500 text-red-700"
                      : ""}`}
                  >
                    ✗ Incorrect
                  </Button>
                </div>

                <div className="bg-gray-50 p-3 rounded-md space-y-2">
                  <label className="flex items-center gap-2 cursor-pointer p-2 hover:bg-gray-100 rounded">
                    <Checkbox
                      checked={qualityStatus[activePart]?.is_poor_quality || false}
                      onCheckedChange={() => togglePoorQuality(activePart)}
                    />
                    <span>Poor Quality</span>
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer p-2 hover:bg-gray-100 rounded">
                    <Checkbox
                      checked={!qualityStatus[activePart]?.is_complete || false}
                      onCheckedChange={() => toggleIncomplete(activePart)}
                    />
                    <span>Incomplete</span>
                  </label>
                </div>

                <div className="mt-4">
                  <Button
                    onClick={handleSave}
                    className="w-full bg-blue-600 hover:bg-blue-700"
                  >
                    Save and Next
                  </Button>
                </div>
              </div>
            </div>

            {/* Part selection sidebar */}
            <div className="bg-gray-50 p-4 rounded-md">
              <h3 className="font-medium text-gray-700 mb-3">Parts</h3>
              <div className="space-y-2 max-h-[60vh] overflow-y-auto pr-2">
                {Object.entries(imageData.parts).map(([partName, part]) => {
                  const status = getPartStatus(partName);
                  const hasExistingAnnotations = part.has_existing_annotations !== false;

                  return (
                    <button
                      key={partName}
                      onClick={() => setActivePart(partName)}
                      onDoubleClick={() => {
                        setActivePart(partName);
                        handleStartAnnotation();
                      }}
                      className={`w-full text-left px-3 py-3 rounded-md border flex items-center justify-between group hover:bg-gray-100 transition-colors
                        ${activePart === partName ? 'bg-blue-50 border-blue-300' : 'border-gray-200'}
                        ${status === "correct" ? 'bg-green-50 border-green-200' : ''}
                        ${status === "incorrect" ? 'bg-red-50 border-red-200' : ''}
                        ${!hasExistingAnnotations ? 'border-dashed border-gray-300' : ''}
                      `}
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium truncate">
                          {partName.split("--part:")[1] || partName}
                        </span>
                        {!hasExistingAnnotations && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">
                            No annotations
                          </span>
                        )}
                      </div>

                      {status && (
                        <span className={`${status === "correct" ? 'text-green-600' : 'text-red-600'}`}>
                          {status === "correct" ? "✓" : "✗"}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>

              <div className="mt-6">
                <Button
                  variant="outline"
                  className="w-full border-indigo-200 text-indigo-700 bg-indigo-50 hover:bg-indigo-100"
                  onClick={handleStartAnnotation}
                >
                  {showMask ? "Re-annotate Part" : "Annotate Part"}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}