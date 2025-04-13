import { useState, useEffect } from "react"
import { Card, CardContent } from "./components/ui/card"
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
        is_complete: part.is_complete || true,
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

    const updatedParts = {}
    Object.entries(imageData.parts).forEach(([name, part]) => {
      const status = qualityStatus[name] || {}
      updatedParts[name] = {
        ...part,
        was_checked: true,
        is_poor_quality: status.is_poor_quality,
        is_correct: status.is_correct,
        is_complete: status.is_complete,
      }
    })

    const payload = {
      image_path: imageData.image_path,
      parts: updatedParts,
    }

    await fetch(`${baseURL}/annotate/save-annotation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })

    fetchNextImage()
    fetchStats()
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
                    )}&parts=${encodeURIComponent(activePart)}`}
                    alt="Selected mask"
                    className="max-w-full max-h-[60vh] object-contain border-2 border-gray-200 rounded-lg shadow-md"
                  />
                  <div className="absolute top-2 left-2">
                    <Badge variant="secondary" className="bg-white/90 shadow-sm border border-gray-200">
                      {activePart.split("--part:")[1] || activePart}
                    </Badge>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-center h-[60vh] w-full text-gray-400 bg-gray-100 rounded-lg">
                  No mask available for {activePart}
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
                    variant="outline"
                    className="w-full border-indigo-200 text-indigo-700 bg-indigo-50 hover:bg-indigo-100"
                    onClick={handleStartAnnotation}
                  >
                    {showMask ? "Re-annotate Part" : "Annotate Part"}
                  </Button>
                </div>
              </div>
            </div>

            {/* Part selection sidebar */}
            <div className="bg-gray-50 p-4 rounded-md">
              <h3 className="font-medium text-gray-700 mb-3">Parts</h3>
              <div className="space-y-2 max-h-[60vh] overflow-y-auto pr-2">
                {Object.keys(imageData.parts).map((partName) => {
                  const status = getPartStatus(partName);
                  return (
                    <button
                      key={partName}
                      onClick={() => setActivePart(partName)}
                      className={`w-full text-left px-3 py-3 rounded-md border flex items-center justify-between group hover:bg-gray-100 transition-colors
                        ${activePart === partName ? 'bg-blue-50 border-blue-300' : 'border-gray-200'}
                        ${status === "correct" ? 'bg-green-50 border-green-200' : ''}
                        ${status === "incorrect" ? 'bg-red-50 border-red-200' : ''}
                      `}
                    >
                      <span className="text-sm font-medium truncate">
                        {partName.split("--part:")[1] || partName}
                      </span>

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
                  onClick={handleSave}
                  className="w-full bg-blue-600 hover:bg-blue-700"
                >
                  Save and Next
                </Button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}