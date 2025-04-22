export function Header({ stats, userStats }) {
  return (
    <div className="bg-gradient-to-r from-blue-600 to-indigo-700 py-4 px-6 shadow-md">
      <div className="flex justify-between items-center max-w-7xl mx-auto">
        <h1 className="text-2xl font-bold text-white">Segmentation Annotator</h1>

        {stats && (
          <div className="bg-white rounded-lg px-4 py-2 shadow-sm">
            <div className="text-sm font-medium">
              Progress: <span className="font-bold">{stats.checked_images} / {stats.total_images}</span> images
              <span className="ml-2 px-2 py-1 bg-blue-100 text-blue-800 rounded-full text-xs font-bold">
                {stats.progress_percentage}%
              </span>
            </div>

            {userStats && (
              <div className="text-xs text-gray-600 mt-1">
                Your contributions: <span className="font-semibold">{userStats.user_count}</span> images
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}