import { Card, CardContent } from "./card"

export function Header({ stats }) {
  return (
    <div className="bg-gradient-to-r from-blue-600 to-indigo-700 py-4 px-6 shadow-md">
      <div className="flex justify-between items-center max-w-7xl mx-auto">
        <h1 className="text-2xl font-bold text-white">Segmentation Annotator</h1>

        {stats && (
          <div className="bg-white rounded-full px-4 py-2 shadow-sm">
            <div className="text-sm font-medium">
              Progress: <span className="font-bold">{stats.checked_images} / {stats.total_images}</span> images
              <span className="ml-2 px-2 py-1 bg-blue-100 text-blue-800 rounded-full text-xs font-bold">
                {stats.progress_percentage}%
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}