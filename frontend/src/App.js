import { useState, useEffect } from "react"
import { Card, CardContent } from "./components/ui/card"
import { Button } from "./components/ui/button"
import { Checkbox } from "./components/ui/checkbox"

export default function SegmentationReviewApp() {
  const [imageData, setImageData] = useState(null)
  const [activePart, setActivePart] = useState(null)
  const [qualityStatus, setQualityStatus] = useState({})
  const [stats, setStats] = useState(null)

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
    const res = await fetch(`${baseURL}/queue/next-image`)
    const data = await res.json()

    if (!data?.image_path) {
      setImageData(null)
      return
    }

    setImageData(data)
    setActivePart(Object.keys(data.parts)[0] || null)

    const statusMap = {}
    Object.entries(data.parts).forEach(([name, part]) => {
      statusMap[name] = {
        is_poor_quality: part.is_poor_quality || false,
        is_incorrect: part.is_incorrect || false,
      }
    })
    setQualityStatus(statusMap)
  }

  const toggleIncorrect = (partName) => {
    setQualityStatus((prev) => ({
      ...prev,
      [partName]: {
        ...prev[partName],
        is_incorrect: !prev[partName].is_incorrect,
      },
    }))
  }

  const togglePoorQuality = (partName) => {
    setQualityStatus((prev) => ({
      ...prev,
      [partName]: {
        ...prev[partName],
        is_poor_quality: !prev[partName].is_poor_quality,
      },
    }))
  }

  const handleSave = async () => {
    if (!imageData) return

    const updatedParts = {}
    Object.entries(imageData.parts).forEach(([name, part]) => {
      const status = qualityStatus[name] || {}
      updatedParts[name] = {
        ...part,
        was_checked: true,
        is_poor_quality: status.is_poor_quality,
        is_incorrect: status.is_incorrect,
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

  if (!imageData) return <div className="p-4 text-lg">🎉 No more images to annotate.</div>

  const showMask =
    activePart && imageData.parts[activePart]?.rles?.length > 0

  return (
    <div className="p-4 space-y-4">
      {stats && (
        <Card>
          <CardContent className="p-4 text-sm">
            Progress: {stats.checked_images} / {stats.total_images} images (
            {stats.progress_percentage}%)
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="flex flex-col md:flex-row gap-6">
          {/* Sidebar: Part List */}
          <div className="flex flex-col gap-2 w-full md:w-64">
            {Object.keys(imageData.parts).map((partName) => (
              <div
                key={partName}
                onClick={() => setActivePart(partName)}
                className={`cursor-pointer px-3 py-2 rounded border text-sm ${
                  activePart === partName
                    ? "bg-accent text-accent-foreground"
                    : "hover:bg-muted"
                }`}
              >
                {partName}
              </div>
            ))}
          </div>

          {/* Image + Controls */}
          <div className="flex flex-col items-center gap-4 flex-1">
            <img
              src={imageData.image_path}
              alt="To annotate"
              className="max-w-full border rounded"
            />

            {showMask && (
              <img
                src={`${baseURL}/mask/render-mask?image_path=${encodeURIComponent(
                  imageData.image_path
                )}&parts=${encodeURIComponent(activePart)}`}
                alt="Selected mask"
                className="max-w-full border rounded"
              />
            )}

            {activePart && (
              <div className="flex flex-col gap-2 items-start w-full max-w-md">
                <div className="text-lg font-semibold">{activePart}</div>

                <div className="flex gap-3 flex-wrap">
                  <Button
                    variant={
                      qualityStatus[activePart]?.is_incorrect
                        ? "default"
                        : "outline"
                    }
                    onClick={() => toggleIncorrect(activePart)}
                  >
                    Incorrect
                  </Button>

                  <Button
                    variant={
                      !qualityStatus[activePart]?.is_incorrect
                        ? "default"
                        : "outline"
                    }
                    onClick={() => toggleIncorrect(activePart)}
                  >
                    Correct
                  </Button>

                  <label className="flex items-center gap-2">
                    <Checkbox
                      checked={
                        qualityStatus[activePart]?.is_poor_quality || false
                      }
                      onCheckedChange={() => togglePoorQuality(activePart)}
                    />
                    <span>Poor Quality</span>
                  </label>
                </div>
              </div>
            )}

            <Button onClick={handleSave} className="mt-4">
              Save and Next
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}