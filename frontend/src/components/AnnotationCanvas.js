import { useRef, useEffect, useState } from "react"
import { Button } from "./ui/button"

const POINT_RADIUS = 3
const POINT_HIGHLIGHT_RADIUS = 5

export default function AnnotationCanvas({
  imageUrl,
  mode,
  onSavePoints,
  onSavePolygon,
  onPreviewMask,
  initialPositivePoints = [],
  initialNegativePoints = [],
  initialPolygonPoints = [],
  className
}) {
  const canvasRef = useRef(null)
  const containerRef = useRef(null)
  const [positivePoints, setPositivePoints] = useState(initialPositivePoints)
  const [negativePoints, setNegativePoints] = useState(initialNegativePoints)
  const [polygonPoints, setPolygonPoints] = useState(initialPolygonPoints)
  const [isDrawing, setIsDrawing] = useState(false)
  const [originalImageSize, setOriginalImageSize] = useState({ width: 0, height: 0 })
  const [scale, setScale] = useState(1)
  const [selectedPoint, setSelectedPoint] = useState(null)
  const [previewRequestId, setPreviewRequestId] = useState(0)
  const [lastClickTime, setLastClickTime] = useState(0)
  const [lastClickedPoint, setLastClickedPoint] = useState(null)

  // Mode is either "point_prompt" or "polygon"
  const isPointPromptMode = mode === "point_prompt"

  // Load image onto canvas
  useEffect(() => {
    if (!imageUrl) return

    const canvas = canvasRef.current
    const ctx = canvas.getContext("2d")
    const container = containerRef.current

    const img = new Image()
    img.src = imageUrl

    img.onload = () => {
      // Save original image dimensions
      setOriginalImageSize({ width: img.width, height: img.height })

      // Get container dimensions
      const containerWidth = container.clientWidth
      const containerHeight = container.clientHeight

      // Calculate scale to fit image within container
      const scaleX = containerWidth / img.width
      const scaleY = containerHeight / img.height
      const newScale = Math.min(scaleX, scaleY, 0.99) // Don't upscale, only downscale to 99% max

      // Set canvas dimensions
      canvas.width = img.width * newScale
      canvas.height = img.height * newScale

      // Save scale for coordinate conversion
      setScale(newScale)

      // Draw image
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    }
  }, [imageUrl])

  // Handle canvas click
  const handleCanvasClick = (e) => {
    if (!canvasRef.current) return

    const canvas = canvasRef.current
    const rect = canvas.getBoundingClientRect()

    // Get click coordinates relative to canvas and convert to original image coordinates
    // Ensure these are integers since the backend expects integer coordinates
    const x = Math.round((e.clientX - rect.left) / scale)
    const y = Math.round((e.clientY - rect.top) / scale)

    console.log(`Click coordinates: x=${x}, y=${y}`)

    // Check if a point was clicked
    const clickedPoint = findClickedPoint(x, y)

    // Get the current time
    const currentTime = new Date().getTime()

    // Check for double click on a point (300ms threshold)
    if (clickedPoint &&
        lastClickedPoint &&
        clickedPoint.type === lastClickedPoint.type &&
        clickedPoint.index === lastClickedPoint.index &&
        currentTime - lastClickTime < 300) {

      // Delete the point on double click
      if (clickedPoint.type === 'positive') {
        setPositivePoints(positivePoints.filter((_, i) => i !== clickedPoint.index))
      } else if (clickedPoint.type === 'negative') {
        setNegativePoints(negativePoints.filter((_, i) => i !== clickedPoint.index))
      } else if (clickedPoint.type === 'polygon') {
        setPolygonPoints(polygonPoints.filter((_, i) => i !== clickedPoint.index))
      }

      // Reset selection and double click tracking
      setSelectedPoint(null)
      setLastClickedPoint(null)
      setLastClickTime(0)
      return
    }

    // Store info for double click detection
    setLastClickTime(currentTime)
    setLastClickedPoint(clickedPoint)

    if (clickedPoint) {
      // Select/deselect point
      setSelectedPoint(selectedPoint &&
                       selectedPoint.type === clickedPoint.type &&
                       selectedPoint.index === clickedPoint.index ? null : clickedPoint)
      return
    }

    // If no point was clicked, add a new point
    if (isPointPromptMode) {
      // Left click = positive point, right click = negative point
      let updatedPositivePoints = [...positivePoints];
      let updatedNegativePoints = [...negativePoints];

      if (e.button === 0) {
        // Create a new point with integer coordinates
        const newPoint = { x: Math.round(x), y: Math.round(y) };
        updatedPositivePoints = [...positivePoints, newPoint];
        setPositivePoints(updatedPositivePoints);
        console.log(`Added positive point: x=${newPoint.x}, y=${newPoint.y}`);
      } else if (e.button === 2) {
        // Create a new point with integer coordinates
        const newPoint = { x: Math.round(x), y: Math.round(y) };
        updatedNegativePoints = [...negativePoints, newPoint];
        setNegativePoints(updatedNegativePoints);
        console.log(`Added negative point: x=${newPoint.x}, y=${newPoint.y}`);
      }

      // Immediately request a preview after adding a point
      if (onPreviewMask && (e.button === 0 || e.button === 2)) {
        const newRequestId = previewRequestId + 1;
        setPreviewRequestId(newRequestId);

        // Use a short timeout to ensure state updates have completed
        setTimeout(() => {
          console.log("Directly triggering preview after point add");
          console.log(`Positive points: ${JSON.stringify(updatedPositivePoints)}`);
          console.log(`Negative points: ${JSON.stringify(updatedNegativePoints)}`);
          onPreviewMask({
            positivePoints: updatedPositivePoints,
            negativePoints: updatedNegativePoints,
            requestId: newRequestId
          });
        }, 50);
      }
    } else {
      // Add point to polygon with integer coordinates
      const newPoint = { x: Math.round(x), y: Math.round(y) };
      const updatedPolygonPoints = [...polygonPoints, newPoint];
      setPolygonPoints(updatedPolygonPoints);
      console.log(`Added polygon point: x=${newPoint.x}, y=${newPoint.y}`);

      // Immediately request a preview if we have a polygon with 3+ points
      if (onPreviewMask && updatedPolygonPoints.length >= 3) {
        const newRequestId = previewRequestId + 1;
        setPreviewRequestId(newRequestId);

        // Use a short timeout to ensure state updates have completed
        setTimeout(() => {
          console.log("Directly triggering preview after polygon point add");
          console.log(`Polygon points: ${JSON.stringify(updatedPolygonPoints)}`);
          onPreviewMask({
            polygonPoints: updatedPolygonPoints,
            requestId: newRequestId
          });
        }, 50);
      }
    }

    // Clear selection
    setSelectedPoint(null)
  }

  // Generate mask preview when points change (as a backup to the direct triggers)
  useEffect(() => {
    const requestPreview = () => {
      if (!onPreviewMask) return

      const hasEnoughPoints =
        (isPointPromptMode && positivePoints.length > 0) ||
        (!isPointPromptMode && polygonPoints.length > 2)

      if (hasEnoughPoints) {
        // Use request ID to avoid race conditions with multiple previews
        const currentRequestId = previewRequestId + 1
        setPreviewRequestId(currentRequestId)

        console.log("useEffect triggering preview, has enough points:", hasEnoughPoints);

        if (isPointPromptMode) {
          onPreviewMask({
            positivePoints,
            negativePoints,
            requestId: currentRequestId
          })
        } else {
          onPreviewMask({
            polygonPoints,
            requestId: currentRequestId
          })
        }
      }
    }

    // Create a cache key to detect actual changes in points
    const cacheKey = JSON.stringify({
      mode: isPointPromptMode,
      positive: positivePoints,
      negative: negativePoints,
      polygon: polygonPoints
    })

    // Store the previous cache key in a ref
    if (!requestPreview.prevCacheKey) {
      requestPreview.prevCacheKey = cacheKey
    }

    // Only request a preview if the points have actually changed
    if (requestPreview.prevCacheKey !== cacheKey) {
      requestPreview.prevCacheKey = cacheKey

      // Use debounce with a shorter delay to be more responsive
      const timerId = setTimeout(requestPreview, 300)
      return () => clearTimeout(timerId)
    }

    return undefined
  }, [positivePoints, negativePoints, polygonPoints, isPointPromptMode, onPreviewMask, previewRequestId])

  // Redraw canvas when points change
  useEffect(() => {
    if (!canvasRef.current || !imageUrl) return

    const canvas = canvasRef.current
    const ctx = canvas.getContext("2d")

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    // Redraw image
    const img = new Image()
    img.src = imageUrl
    img.onload = () => {
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height)

      // Draw points
      if (isPointPromptMode) {
        // Draw positive points
        ctx.fillStyle = '#00FF00'
        ctx.strokeStyle = '#005500'
        positivePoints.forEach((point, index) => {
          const isSelected = selectedPoint && selectedPoint.type === 'positive' && selectedPoint.index === index

          ctx.beginPath()
          ctx.arc(point.x * scale, point.y * scale, POINT_RADIUS, 0, 2 * Math.PI)
          ctx.fill()

          // Draw outline
          ctx.lineWidth = 1.5
          ctx.stroke()

          // Draw highlight for selected point
          if (isSelected) {
            ctx.beginPath()
            ctx.arc(point.x * scale, point.y * scale, POINT_HIGHLIGHT_RADIUS, 0, 2 * Math.PI)
            ctx.strokeStyle = '#00FF00'
            ctx.lineWidth = 2
            ctx.stroke()
          }

          // Draw index number
          ctx.fillStyle = '#FFFFFF'
          ctx.font = '10px Arial'
          ctx.textAlign = 'center'
          ctx.textBaseline = 'middle'
          ctx.fillText(index + 1, point.x * scale, point.y * scale)
        })

        // Draw negative points
        ctx.fillStyle = '#FF0000'
        ctx.strokeStyle = '#550000'
        negativePoints.forEach((point, index) => {
          const isSelected = selectedPoint && selectedPoint.type === 'negative' && selectedPoint.index === index

          ctx.beginPath()
          ctx.arc(point.x * scale, point.y * scale, POINT_RADIUS, 0, 2 * Math.PI)
          ctx.fill()

          // Draw outline
          ctx.lineWidth = 1.5
          ctx.stroke()

          // Draw highlight for selected point
          if (isSelected) {
            ctx.beginPath()
            ctx.arc(point.x * scale, point.y * scale, POINT_HIGHLIGHT_RADIUS, 0, 2 * Math.PI)
            ctx.strokeStyle = '#FF0000'
            ctx.lineWidth = 2
            ctx.stroke()
          }

          // Draw index number
          ctx.fillStyle = '#FFFFFF'
          ctx.font = '10px Arial'
          ctx.textAlign = 'center'
          ctx.textBaseline = 'middle'
          ctx.fillText(index + 1, point.x * scale, point.y * scale)
        })
      } else {
        // Draw polygon
        if (polygonPoints.length > 0) {
          // Draw lines connecting points
          ctx.beginPath()
          ctx.strokeStyle = '#0066FF'
          ctx.lineWidth = 2

          ctx.moveTo(polygonPoints[0].x * scale, polygonPoints[0].y * scale)
          polygonPoints.slice(1).forEach(point => {
            ctx.lineTo(point.x * scale, point.y * scale)
          })

          // Close the polygon if more than 2 points
          if (polygonPoints.length > 2) {
            ctx.lineTo(polygonPoints[0].x * scale, polygonPoints[0].y * scale)
          }

          ctx.stroke()

          // Draw points
          ctx.fillStyle = '#0066FF'
          ctx.strokeStyle = '#003399'

          polygonPoints.forEach((point, index) => {
            const isSelected = selectedPoint && selectedPoint.type === 'polygon' && selectedPoint.index === index

            ctx.beginPath()
            ctx.arc(point.x * scale, point.y * scale, POINT_RADIUS, 0, 2 * Math.PI)
            ctx.fill()

            // Draw outline
            ctx.lineWidth = 1.5
            ctx.stroke()

            // Draw highlight for selected point
            if (isSelected) {
              ctx.beginPath()
              ctx.arc(point.x * scale, point.y * scale, POINT_HIGHLIGHT_RADIUS, 0, 2 * Math.PI)
              ctx.strokeStyle = '#0066FF'
              ctx.lineWidth = 2
              ctx.stroke()
            }

            // Draw index number
            ctx.fillStyle = '#FFFFFF'
            ctx.font = '10px Arial'
            ctx.textAlign = 'center'
            ctx.textBaseline = 'middle'
            ctx.fillText(index + 1, point.x * scale, point.y * scale)
          })
        }
      }
    }
  }, [imageUrl, positivePoints, negativePoints, polygonPoints, scale, isPointPromptMode, selectedPoint])

  // Find if a point is clicked
  const findClickedPoint = (x, y) => {
    const threshold = 15 / scale // Threshold in original image coordinates

    if (isPointPromptMode) {
      // Check positive points
      for (let i = 0; i < positivePoints.length; i++) {
        const point = positivePoints[i]
        const distance = Math.hypot(point.x - x, point.y - y)
        if (distance < threshold) {
          return { type: 'positive', index: i }
        }
      }

      // Check negative points
      for (let i = 0; i < negativePoints.length; i++) {
        const point = negativePoints[i]
        const distance = Math.hypot(point.x - x, point.y - y)
        if (distance < threshold) {
          return { type: 'negative', index: i }
        }
      }
    } else {
      // Check polygon points
      for (let i = 0; i < polygonPoints.length; i++) {
        const point = polygonPoints[i]
        const distance = Math.hypot(point.x - x, point.y - y)
        if (distance < threshold) {
          return { type: 'polygon', index: i }
        }
      }
    }

    return null
  }

  // Prevent context menu on right-click
  const handleContextMenu = (e) => {
    e.preventDefault()
  }

  // Handle delete key press
  const handleKeyDown = (e) => {
    if (e.key === 'Delete' || e.key === 'Backspace') {
      if (selectedPoint) {
        if (selectedPoint.type === 'positive') {
          setPositivePoints(positivePoints.filter((_, i) => i !== selectedPoint.index))
        } else if (selectedPoint.type === 'negative') {
          setNegativePoints(negativePoints.filter((_, i) => i !== selectedPoint.index))
        } else if (selectedPoint.type === 'polygon') {
          setPolygonPoints(polygonPoints.filter((_, i) => i !== selectedPoint.index))
        }
        setSelectedPoint(null)
      }
    }
  }

  // Delete selected point
  const handleDeletePoint = () => {
    if (selectedPoint) {
      if (selectedPoint.type === 'positive') {
        setPositivePoints(positivePoints.filter((_, i) => i !== selectedPoint.index))
      } else if (selectedPoint.type === 'negative') {
        setNegativePoints(negativePoints.filter((_, i) => i !== selectedPoint.index))
      } else if (selectedPoint.type === 'polygon') {
        setPolygonPoints(polygonPoints.filter((_, i) => i !== selectedPoint.index))
      }
      setSelectedPoint(null)
    }
  }

  // Handle reset
  const handleReset = () => {
    if (isPointPromptMode) {
      setPositivePoints([])
      setNegativePoints([])
    } else {
      setPolygonPoints([])
    }
    setSelectedPoint(null)
  }

  // Handle save
  const handleSave = () => {
    if (isPointPromptMode && positivePoints.length > 0) {
      console.log("Saving points:", {
        positivePoints: positivePoints.map(p => ({ x: Math.round(p.x), y: Math.round(p.y) })),
        negativePoints: negativePoints.map(p => ({ x: Math.round(p.x), y: Math.round(p.y) }))
      });

      onSavePoints({
        positivePoints: positivePoints.map(p => ({ x: Math.round(p.x), y: Math.round(p.y) })),
        negativePoints: negativePoints.map(p => ({ x: Math.round(p.x), y: Math.round(p.y) }))
      })
    } else if (!isPointPromptMode && polygonPoints.length > 2) {
      console.log("Saving polygon:", {
        polygonPoints: polygonPoints.map(p => ({ x: Math.round(p.x), y: Math.round(p.y) }))
      });

      onSavePolygon({
        polygonPoints: polygonPoints.map(p => ({ x: Math.round(p.x), y: Math.round(p.y) }))
      })
    }
  }

  // Set up keyboard event listeners
  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [selectedPoint, positivePoints, negativePoints, polygonPoints])

  return (
    <div className={`flex flex-col ${className}`} tabIndex="0">
      <div className="mb-3">
        {isPointPromptMode ? (
          <div className="flex flex-col space-y-1 text-sm">
            <div className="flex items-center space-x-2">
              <span className="w-3 h-3 bg-green-500 rounded-full"></span>
              <span><strong>Left Click:</strong> Add Positive Point ({positivePoints.length})</span>
            </div>
            <div className="flex items-center space-x-2">
              <span className="w-3 h-3 bg-red-500 rounded-full"></span>
              <span><strong>Right Click:</strong> Add Negative Point ({negativePoints.length})</span>
            </div>
          </div>
        ) : (
          <div className="flex items-center space-x-2 text-sm">
            <span className="w-3 h-3 bg-blue-500 rounded-full"></span>
            <span><strong>Click:</strong> Add polygon point ({polygonPoints.length})</span>
          </div>
        )}
      </div>

      <div className="flex justify-end items-center mb-2 space-x-2">
        <Button
          variant="outline"
          size="sm"
          onClick={handleDeletePoint}
          disabled={!selectedPoint}
          className={!selectedPoint ? "opacity-50" : ""}
        >
          Delete Point
        </Button>
        <Button variant="outline" size="sm" onClick={handleReset}>
          Reset
        </Button>
        <Button
          size="sm"
          onClick={handleSave}
          disabled={(isPointPromptMode && positivePoints.length === 0) ||
                   (!isPointPromptMode && polygonPoints.length < 3)}
        >
          Generate Mask
        </Button>
      </div>

      <div className="mb-2 text-xs text-gray-500">
        {selectedPoint ? (
          <span>
            Selected: {selectedPoint.type} point #{selectedPoint.index + 1}
            (press Delete to remove, or double-click on the point)
          </span>
        ) : (
          <span>Click on a point to select it, or double-click to delete it</span>
        )}
      </div>

      <div
        ref={containerRef}
        className="relative w-full h-[60vh] bg-gray-100 flex items-center justify-center overflow-hidden"
      >
        <canvas
          ref={canvasRef}
          className="max-w-full max-h-full cursor-crosshair"
          onClick={handleCanvasClick}
          onMouseDown={(e) => {
            if (e.button === 2) { // Handle right mouse button
              // Use a small timeout to ensure the right click is properly captured
              // before the context menu would normally appear
              setTimeout(() => {
                handleCanvasClick(e);
              }, 10);
            }
          }}
          onContextMenu={handleContextMenu}
        />
      </div>

      <div className="mt-2 text-xs text-right text-gray-500">
        Original image size: {originalImageSize.width}×{originalImageSize.height}
      </div>
    </div>
  )
}