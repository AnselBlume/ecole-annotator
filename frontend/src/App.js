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
        is_correct: null,
        is_complete: part.is_complete || true,
      }
    })
    setQualityStatus(statusMap)
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

  if (!imageData) return <div className="p-4 text-lg">🎉 No more images to annotate.</div>

  const showMask =
    activePart && imageData.parts[activePart]?.rles?.length > 0

  return (
    <div className="p-4 space-y-4">
      {stats && (
        <Card>
          <CardContent className="p-4 text-lg font-bold text-center">
            Progress: {stats.checked_images} / {stats.total_images} images (
            {stats.progress_percentage}%)
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="grid md:grid-cols-[1fr,300px] gap-8 items-start flex flex-col justify-center items-center">
          {/* 🖼️ Image on the left */}
          <div className="flex flex-col gap-4 w-full max-w-[50%] p-4">
            <div className="flex flex-row gap-10 w-full justify-center">
              <div className="flex flex-col gap-6 max-w-[70%]">
                {showMask && (
                  <img
                    src={`${baseURL}/mask/render-mask?image_path=${encodeURIComponent(
                      imageData.image_path
                    )}&parts=${encodeURIComponent(activePart)}`}
                    alt="Selected mask"
                    className="max-w-full max-h-[500px] object-contain outline outline-5 outline-black"
                  />
                )}

                <div className="text-lg font-semibold text-center">{activePart}</div>

                <div className="flex flex-row gap-3 flex-wrap justify-center items-center">
                  <Button
                    data-active={qualityStatus[activePart]?.is_correct === true}
                    variant="outline"
                    onClick={() => setCorrectStatus(activePart, true)}
                    className="data-[active=true]:bg-green-100 data-[active=true]:border-green-600"
                  >
                    Correct
                  </Button>

                  <Button
                    data-active={qualityStatus[activePart]?.is_correct === false}
                    variant="outline"
                    onClick={() => setCorrectStatus(activePart, false)}
                    className="data-[active=true]:bg-red-100 data-[active=true]:border-red-600"
                  >
                    Incorrect
                  </Button>

                  <div className="flex flex-col gap-2">
                    <label className="flex items-center gap-2">
                      <Checkbox
                        checked={qualityStatus[activePart]?.is_poor_quality || false}
                        onCheckedChange={() => togglePoorQuality(activePart)}
                      />
                      <span>Poor Quality</span>
                    </label>

                    <label className="flex items-center gap-2">
                      <Checkbox
                        checked={!qualityStatus[activePart]?.is_complete || false}
                        onCheckedChange={() =>
                          toggleIncomplete(activePart)
                        }
                      />
                      <span>Incomplete</span>
                    </label>
                  </div>
                </div>
              </div>

              {/* 🧩 Part buttons on the right */}
              <div className="flex flex-col gap-2 max-w-[30%]">
                {Object.keys(imageData.parts).map((partName) => (
                  <button
                    key={partName}
                    onClick={() => setActivePart(partName)}
                    data-active={activePart === partName}
                    className="cursor-pointer text-left px-3 py-2 rounded border text-sm flex justify-between items-center data-[active=true]:bg-blue-100 data-[active=true]:border-blue-500 hover:bg-muted"
                  >
                    <span>{partName.split("--part:")[1]}</span>
                    {qualityStatus[partName]?.is_correct !== null && (
                      <span className="text-lg text-green-500 font-bold">✓</span>
                    )}
                  </button>
                ))}
              </div>
            </div>

            {activePart && (
              <div className="flex flex-col gap-2 w-full items-center">
                <div className="flex w-full justify-end">
                  <Button onClick={handleSave} className="mt-4">
                    Save and Next
                  </Button>
                </div>
              </div>
            )}
          </div>

        </CardContent>
      </Card>
    </div>
  )
}