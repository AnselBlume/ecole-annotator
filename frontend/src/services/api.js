const BASE_URL = process.env.REACT_APP_BACKEND;

/**
 * Fetch the next image to annotate
 */
export const fetchNextImage = async () => {
  const res = await fetch(
    `${BASE_URL}/queue/next-image`,
    {
      credentials: 'include',
    }
  );
  const data = await res.json();
  return data;
};

/**
 * Fetch annotation statistics
 */
export const fetchStats = async () => {
  const res = await fetch(
    `${BASE_URL}/annotate/annotation-stats`,
    {
      credentials: 'include',
    }
  );
  return await res.json();
};

/**
 * Fetch user annotation count based on session cookie
 */
export const fetchUserStats = async () => {
  const res = await fetch(
    `${BASE_URL}/annotate/user-annotation-count`,
    {
      credentials: 'include',
    }
  );
  return await res.json();
};

/**
 * Fetch the object label for an image
 */
export const fetchObjectLabel = async (imagePath) => {
  const res = await fetch(
    `${BASE_URL}/annotate/object-label?image_path=${encodeURIComponent(imagePath)}`,
    {
      credentials: 'include',
    }
  );
  if (!res.ok) {
    throw new Error(`Failed to fetch object label: ${res.status} ${res.statusText}`);
  }
  return await res.json();
};

/**
 * Save annotation data
 */
export const saveAnnotation = async (payload) => {
  const response = await fetch(`${BASE_URL}/annotate/save-annotation`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: 'include',
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Error saving annotation: ${response.status} ${response.statusText} - ${errorText}`);
  }

  return response;
};

/**
 * Get mask image URL for specified image path and parts
 */
export const getMaskImageUrl = (imagePath, parts, maskColor = 'aqua', timestamp = Date.now()) => {
  return `${BASE_URL}/mask/render-mask?image_path=${encodeURIComponent(
    imagePath
  )}&parts=${encodeURIComponent(parts)}&mask_color=${encodeURIComponent(maskColor)}&timestamp=${timestamp}`;
};

/**
 * Get original image URL
 */
export const getOriginalImageUrl = (imagePath) => {
  return `${BASE_URL}/images/${encodeURIComponent(imagePath)}`;
};

// Export BASE_URL as a named export
export { BASE_URL };

export default {
  fetchNextImage,
  fetchStats,
  fetchUserStats,
  fetchObjectLabel,
  saveAnnotation,
  getMaskImageUrl,
  getOriginalImageUrl,
  BASE_URL
};