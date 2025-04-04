import { useState, useEffect } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"

export default function SegmentationReviewApp() {
  const [imageData, setImageData] = useState(null)
  const [selectedParts, setSelectedParts] = useState(new Set())
  const [partStatus, setPartStatus] = useState({})

  useEffect(() => {
    fetchNextImage()
  }, [])

  const fetchNextImage = async () => {
    const res = await fetch("/api/next-image")
    const data = await res.json()
    setImageData(data)
    setPartStatus(
      Object.fromEntries(data.parts.map((p) => [p.label, false]))
    )
    setSelectedParts(new Set())
  }

  const handleSave = async () => {
    await fetch("/api/save-annotation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        imagePath: imageData.imagePath,
        partStatus,
      }),
    })
    fetchNextImage()
  }

  const togglePartStatus = (partLabel) => {
    setPartStatus((prev) => ({
      ...prev,
      [partLabel]: !prev[partLabel],
    }))
  }

  const togglePartSelection = (partLabel) => {
    setSelectedParts(prev => {
      const newSet = new Set(prev)
      if (newSet.has(partLabel)) {
        newSet.delete(partLabel)
      } else {
        newSet.add(partLabel)
      }
      return newSet
    })
  }

  if (!imageData) return <div>Loading...</div>

  const hasSelectedMasks = Array.from(selectedParts).some(partLabel =>
    imageData.parts.find(p => p.label === partLabel)?.masks.length > 0
  )

  return (
    <div className="p-4 space-y-4">
      <Card>
        <CardContent className="flex flex-col items-center space-y-4">
          <img src={imageData.imagePath} alt="To annotate" className="max-w-full" />
          <div className="flex flex-wrap gap-2">
            {imageData.parts.map((part) => (
              <Button
                key={part.label}
                variant={selectedParts.has(part.label) ? "default" : "outline"}
                onClick={() => togglePartSelection(part.label)}
              >
                {part.label}
              </Button>
            ))}
          </div>
          <div className="flex flex-col gap-2">
            {imageData.parts.map((part) => (
              <label key={part.label} className="flex items-center gap-2">
                <Checkbox
                  checked={partStatus[part.label]}
                  onCheckedChange={() => togglePartStatus(part.label)}
                />
                <span>
                  {part.label} {partStatus[part.label] ? "✅" : "❌"}
                </span>
              </label>
            ))}
          </div>
          {hasSelectedMasks && (
            <div className="relative">
              <img
                src={`/api/render-mask?image_path=${encodeURIComponent(imageData.imagePath)}&parts=${encodeURIComponent(Array.from(selectedParts).join(','))}`}
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