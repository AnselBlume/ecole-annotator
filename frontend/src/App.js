import { useState, useEffect } from "react"
import { Header } from "./components/ui/header"
import ModularAnnotationMode from "./components/ModularAnnotationMode"
import ImageDisplay from "./components/ImageDisplay"
import PartsSidebar from "./components/PartsSidebar"
import LoadingState from "./components/LoadingState"
import EmptyState from "./components/EmptyState"
import * as apiService from "./services/api"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "./components/ui/alert-dialog"

export default function SegmentationReviewApp() {
  const [imageData, setImageData] = useState(null)
  const [activePart, setActivePart] = useState(null)
  const [qualityStatus, setQualityStatus] = useState({})
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [isAnnotating, setIsAnnotating] = useState(false)
  const [showSaveConfirm, setShowSaveConfirm] = useState(false)

  useEffect(() => {
    fetchNextImage()
    fetchStats()
  }, [])

  const fetchStats = async () => {
    try {
      const data = await apiService.fetchStats()
      setStats(data)
    } catch (error) {
      console.error("Failed to fetch stats:", error)
    }
  }

  const fetchNextImage = async () => {
    setLoading(true)
    try {
      const data = await apiService.fetchNextImage()

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
    } catch (error) {
      console.error("Failed to fetch next image:", error)
    } finally {
      setLoading(false)
    }
  }

  const setCorrectStatus = (partName, isCorrect) => {
    setQualityStatus((prev) => ({
      ...prev,
      [partName]: {
        ...prev[partName],
        is_correct: isCorrect,
      },
    }))

    // If marked as correct, move to the next part
    if (isCorrect) {
      const partNames = Object.keys(imageData.parts)
      const currentIndex = partNames.indexOf(partName)

      // If there's a next part, switch to it
      if (currentIndex < partNames.length - 1) {
        const nextPart = partNames[currentIndex + 1]
        setActivePart(nextPart)
      }
    }
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

    // Check if all parts have been marked as correct or incorrect
    const unmarkedParts = Object.entries(qualityStatus).filter(
      ([_, status]) => status.is_correct === null
    )

    if (unmarkedParts.length > 0) {
      setShowSaveConfirm(true)
      return
    }

    // If all parts are marked, proceed with saving
    saveAnnotations()
  }

  const saveAnnotations = async () => {
    setLoading(true)

    try {
      const updatedParts = {}
      Object.entries(imageData.parts).forEach(([name, part]) => {
        const status = qualityStatus[name] || {}

        // Create a copy of the part
        const updatedPart = {
          name: name,
          rles: Array.isArray(part.rles) ? part.rles : [],
          was_checked: true,
          is_poor_quality: status.is_poor_quality || false,
          is_correct: status.is_correct === null ? true : status.is_correct,
          is_complete: status.is_complete === undefined ? true : status.is_complete,
          has_existing_annotations: part.has_existing_annotations !== false
        }

        updatedParts[name] = updatedPart
      })

      const payload = {
        image_path: imageData.image_path,
        parts: updatedParts,
      }

      await apiService.saveAnnotation(payload)

      // Only fetch next image and stats if save was successful
      fetchNextImage()
      fetchStats()
    } catch (error) {
      console.error("Failed to save annotation:", error)
    } finally {
      setLoading(false)
    }
  }

  // Skip the current image without saving
  const handleSkip = async () => {
    if (!imageData) return
    await fetchNextImage()
    await fetchStats()
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
            ...(annotationData.rles && {
              rles: annotationData.rles,
              has_existing_annotations: annotationData.rles.length > 0
            })
          }
        }
        return {
          ...prevData,
          parts: updatedParts
        }
      })
    }
  }

  if (loading) {
    return <LoadingState stats={stats} />
  }

  if (!imageData) {
    return <EmptyState stats={stats} />
  }

  // If in annotation mode, show the annotation interface
  if (isAnnotating && activePart) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Header stats={stats} />
        <main className="max-w-7xl mx-auto py-8 px-4 sm:px-6">
          <div className="mb-4">
            <h2 className="text-lg font-medium text-gray-900">Current Image: <span className="font-mono text-sm bg-gray-100 px-2 py-1 rounded">{imageData.image_path ? imageData.image_path.split('/').pop() : ''}</span></h2>
          </div>
          <ModularAnnotationMode
            imageData={imageData}
            activePart={activePart}
            baseURL={apiService.BASE_URL}
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
        <div className="bg-white rounded-lg shadow-sm">
          <div className="grid grid-cols-1 lg:grid-cols-[1fr,400px] gap-6 p-6">
            {/* Main image display area */}
            <ImageDisplay
              imageData={imageData}
              activePart={activePart}
              onSkip={handleSkip}
              onSave={handleSave}
              onStartAnnotation={handleStartAnnotation}
            />

            {/* Part selection sidebar */}
            <PartsSidebar
              parts={imageData.parts}
              activePart={activePart}
              qualityStatus={qualityStatus}
              onPartSelect={setActivePart}
              onStartAnnotation={handleStartAnnotation}
              onSetCorrectStatus={setCorrectStatus}
              onTogglePoorQuality={togglePoorQuality}
              onToggleIncomplete={toggleIncomplete}
            />
          </div>
        </div>
      </main>

      {/* Confirmation Dialog */}
      <AlertDialog open={showSaveConfirm} onOpenChange={setShowSaveConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirm Save</AlertDialogTitle>
            <AlertDialogDescription>
              Some parts haven't been marked as correct or incorrect. Do you want to save anyway?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={saveAnnotations}>Save Anyway</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}