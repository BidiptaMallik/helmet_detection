import axios from "axios";

const API_BASE =
  import.meta.env.VITE_API_URL ||
  "http://localhost:8000";

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 120000,
  withCredentials: true,
});

export const loginUser = (credentials) =>
  api.post("/api/auth/login", credentials);

export const registerUser = (details) =>
  api.post("/api/auth/register", details);

export const setupInitialAdmin = (details) =>
  api.post("/api/auth/admin-setup", details);

export const getCurrentUser = () =>
  api.get("/api/auth/me");

export const logoutUser = () =>
  api.post("/api/auth/logout");

export const createIssueReport = (details) =>
  api.post("/api/reports", details, {
    headers: { "Content-Type": "multipart/form-data" },
  });

export const getAdminReports = (params) =>
  api.get("/api/admin/reports", { params });

export const deleteAdminReport = (reportId) =>
  api.delete(`/api/admin/reports/${reportId}`);

export const createAdminReportUpdate = (reportId, details) =>
  api.post(`/api/admin/reports/${reportId}/updates`, details, {
    headers: { "Content-Type": "multipart/form-data" },
  });

export const getAdminReportUpdates = (reportId) =>
  api.get(`/api/admin/reports/${reportId}/updates`);

export const getAdminReportUpdatePhoto = (reportId, updateId) =>
  api.get(`/api/admin/reports/${reportId}/updates/${updateId}/photo`, {
    responseType: "blob",
  });

export const getMyReports = () =>
  api.get("/api/reports/mine");

export const deleteMyReport = (reportId) =>
  api.delete(`/api/reports/${reportId}`);

export const getMyReportUpdates = (reportId) =>
  api.get(`/api/reports/${reportId}/updates`);

export const getMyReportUpdatePhoto = (reportId, updateId) =>
  api.get(`/api/reports/${reportId}/updates/${updateId}/photo`, {
    responseType: "blob",
  });

export const rateResolvedReport = (reportId, rating, comment) =>
  api.post(`/api/reports/${reportId}/rating`, { rating, comment });

export const getMyReportPhoto = (reportId, photoKind) =>
  api.get(`/api/reports/${reportId}/photos/${photoKind}`, {
    responseType: "blob",
  });

export const getAdminReportPhoto = (reportId, photoKind = "original") =>
  api.get(
    photoKind === "original"
      ? `/api/admin/reports/${reportId}/photo`
      : `/api/admin/reports/${reportId}/photos/${photoKind}`,
    {
    responseType: "blob",
    }
  );

/* =========================================
   GENERAL
========================================= */

export const resolveImageUrl = (path) => {
  if (!path) return "";

  if (path.startsWith("http")) {
    return path;
  }

  return `${API_BASE}${path}`;
};

/* =========================================
   DASHBOARD
========================================= */

export const getViolations = (params) =>
  api.get("/api/violations", { params });

export const getStats = () =>
  api.get("/api/stats");

export const getDetectionEvents = (params) =>
  api.get("/api/admin/detection-events", { params });

export const deleteDetectionEvent = (feature, eventId) =>
  api.delete(`/api/admin/detection-events/${feature}/${eventId}`);

export const getHealth = () =>
  api.get("/api/health");

/* =========================================
   FEATURE IMAGE
========================================= */

export const detectFeatureImage = (
  feature,
  file
) => {
  const form = new FormData();

  form.append("file", file);

  return api.post(
    `/api/${feature}/image`,
    form,
    {
      headers: {
        "Content-Type":
          "multipart/form-data",
      },
    }
  );
};

/* =========================================
   FEATURE VIDEO
========================================= */

export const detectFeatureVideo = (
  feature,
  file
) => {
  const form = new FormData();

  form.append("file", file);

  return api.post(
    `/api/${feature}/video`,
    form,
    {
      headers: {
        "Content-Type":
          "multipart/form-data",
      },
    }
  );
};

/* =========================================
   FEATURE WEBCAM
========================================= */

export const detectFeatureWebcam = (
  feature,
  cameraIndex = 0,
  numFrames = 30,
  signal
) => {
  return api.post(
    `/api/${feature}/webcam`,
    null,
    {
      params: {
        camera_index: cameraIndex,
        num_frames: numFrames,
      },
      signal,
    }
  );
};

/* =========================================
   FEATURE CCTV
========================================= */

export const getFeatureCctvWsUrl = (
  feature,
  rtspUrl
) => {
  const wsBase =
    API_BASE.replace(/^http/, "ws");

  return (
    `${wsBase}/ws/${feature}/cctv` +
    `?rtsp_url=${encodeURIComponent(
      rtspUrl
    )}`
  );
};

/* =========================================
   OLD HELMET COMPATIBILITY
========================================= */

export const detectImage = (file) => {
  const form = new FormData();

  form.append("file", file);

  return api.post(
    "/api/detect/image",
    form,
    {
      headers: {
        "Content-Type":
          "multipart/form-data",
      },
    }
  );
};

export const detectVideo = (
  file,
  sampleEvery = 5
) => {
  const form = new FormData();

  form.append("file", file);

  return api.post(
    `/api/detect/video?sample_every=${sampleEvery}`,
    form,
    {
      headers: {
        "Content-Type":
          "multipart/form-data",
      },
    }
  );
};

/* =========================================
   VIDEO UPLOAD
========================================= */

export const uploadVideo = (file) => {
  const form = new FormData();

  form.append("file", file);

  return api.post(
    "/api/upload/video",
    form,
    {
      headers: {
        "Content-Type":
          "multipart/form-data",
      },
    }
  );
};

/* =========================================
   MULTISTREAM WEBSOCKET
========================================= */

export const getMultistreamWsUrl = (
  feature,
  filename,
  sampleEvery = 5
) => {
  const wsBase =
    API_BASE.replace(/^http/, "ws");

  return (
    `${wsBase}/ws/multistream/${feature}/${encodeURIComponent(
      filename
    )}` +
    `?sample_every=${sampleEvery}`
  );
};

/* =========================================
   OLD HELMET VIDEO WEBSOCKET
========================================= */

export const getWsUrl = (
  filename
) => {
  const wsBase =
    API_BASE.replace(/^http/, "ws");

  return (
    `${wsBase}/ws/detect/${encodeURIComponent(
      filename
    )}` +
    "?sample_every=5"
  );
};

/* =========================================
   OLD HELMET CCTV
========================================= */

export const getCctvWsUrl = (
  rtspUrl,
  sampleEvery = 5
) => {
  const wsBase =
    API_BASE.replace(/^http/, "ws");

  return (
    `${wsBase}/ws/detect/cctv` +
    `?rtsp_url=${encodeURIComponent(
      rtspUrl
    )}` +
    `&sample_every=${sampleEvery}`
  );
};