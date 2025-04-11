import { useState, useEffect } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"

export default function SegmentationReviewApp() {
  const [imageData, setImageData] = useState(null)
  const [selectedParts, setSelectedParts] = useState(new Set())
  const [qualityStatus, setQualityStatus] = useState({}) // Maps part name -> { is_poor_quality, is_incorrect }

  useEffect(() => {
    fetchNextImage()
  }, [])

  const fetchNextImage = async () => {
    const res = await fetch("/api/next-image")
    const data = await res.json()

    // Fallback in case no image is returned
    if (!data?.image_path) {
      setImageData(null)
      return
    }

    setImageData(data)
    setSelectedParts(new Set())
    const statusMap = {}
    data.parts.forEach((p) => {
      statusMap[p.name] = { is_poor_quality: false, is_incorrect: false }
    })
    setQualityStatus(statusMap)
  }

  const togglePartSelection = (partName) => {
    setSelectedParts((prev) => {
      const newSet = new Set(prev)
      if (newSet.has(partName)) newSet.delete(partName)
      else newSet.add(partName)
      return newSet
    })
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

  const toggleIncorrect = (partName) => {
    setQualityStatus((prev) => ({
      ...prev,
      [partName]: {
        ...prev[partName],
        is_incorrect: !prev[partName].is_incorrect,
      },
    }))
  }

  const handleSave = async () => {
    if (!imageData) return

    const updatedParts = imageData.parts.map((part) => {
      const name = part.name
      const status = qualityStatus[name] || {}

      return {
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

    await fetch("/api/save-annotation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })

    fetchNextImage()
  }

  if (!imageData) return <div>No more images to annotate. 🎉</div>

  const hasSelectedMasks = Array.from(selectedParts).some((partName) =>
    imageData.parts.find((p) => p.name === partName)?.rles?.length > 0
  )

  return (
    <div className="p-4 space-y-4">
      <Card>
        <CardContent className="flex flex-col items-center space-y-4">
          <img
            src={imageData.image_path}
            alt="To annotate"
            className="max-w-full"
          />

          {/* Part selection */}
          <div className="flex flex-wrap gap-2">
            {imageData.parts.map((part) => (
              <Button
                key={part.name}
                variant={selectedParts.has(part.name) ? "default" : "outline"}
                onClick={() => togglePartSelection(part.name)}
              >
                {part.name}
              </Button>
            ))}
          </div>

          {/* Quality toggles */}
          <div className="grid grid-cols-2 gap-2">
            {imageData.parts.map((part) => (
              <div key={part.name} className="flex flex-col items-start">
                <span className="font-medium">{part.name}</span>
                <label className="flex items-center gap-2">
                  <Checkbox
                    checked={qualityStatus[part.name]?.is_poor_quality}
                    onCheckedChange={() => togglePoorQuality(part.name)}
                  />
                  <span>Poor Quality</span>
                </label>
                <label className="flex items-center gap-2">
                  <Checkbox
                    checked={qualityStatus[part.name]?.is_incorrect}
                    onCheckedChange={() => toggleIncorrect(part.name)}
                  />
                  <span>Incorrect</span>
                </label>
              </div>
            ))}
          </div>

          {/* Mask overlay */}
          {hasSelectedMasks && (
            <div className="relative">
              <img
                src={`/api/render-mask?image_path=${encodeURIComponent(
                  imageData.image_path
                )}&parts=${encodeURIComponent(Array.from(selectedParts).join(","))}`}
                alt="Selected masks"
                className="max-w-full"
              />
            </div>
          )}

          <Button onClick={handleSave}>Save and Next</Button>
        </CardContent>
      </Card>
    </div>
  )
}
