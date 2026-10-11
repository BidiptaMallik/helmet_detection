
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  detectFeatureWebcam,
  uploadVideo,
  getMultistreamWsUrl,
  getFeatureCctvWsUrl,
} from "../api/client.js";
import { AlertTriangle, Plus, Trash2 } from "lucide-react";

const FEATURES = [
  {
    key: "traffic",
    label: "Traffic",
    description: "Cars, bikes, rickshaws and congestion",
  },
  {
    key: "helmet",
    label: "Helmet",
    description: "Helmet and number plate detection",
  },
  {
    key: "garbage",
    label: "Garbage",
    description: "Garbage and waste detection",
  },
  {
    key: "pothole",
    label: "Pothole",
    description: "Road damage and pothole detection",
  },
];

const SOURCES = [
  { id: "video", label: "Video" },
  { id: "webcam", label: "Webcam" },
  { id: "cctv", label: "CCTV" },
];

const createStream = (id, source = "video") => ({
  id,
  source,
  cameraIndex: Math.max(0, id - 1),
  rtspUrl: "",
  file: null,
  filename: "",
  image: "",
  detections: [],
  vehicleCounts: {},
  congestion: "WAITING",
  running: false,
  error: "",
  frame: 0,
});

export default function MultiStream() {
  const [searchParams] = useSearchParams();
  const initialFeature = searchParams.get("feature");
  const [feature, setFeature] = useState(
    FEATURES.some((item) => item.key === initialFeature)
      ? initialFeature
      : "traffic"
  );

  const [streams, setStreams] = useState([
    createStream(1),
    createStream(2),
    createStream(3),
    createStream(4),
  ]);

  const sockets = useRef({});
  const webcamRequests = useRef({});
  const nextStreamId = useRef(5);
  const removedStreams = useRef(new Set());

  const selectedFeature =
    FEATURES.find((item) => item.key === feature) ||
    FEATURES[0];

  const highCongestionStreams =
    feature === "traffic"
      ? streams.filter(
          (stream) =>
            (stream.running || stream.source === "webcam") &&
            stream.congestion === "HIGH"
        )
      : [];

  const detectionAlertStreams =
    feature === "garbage" || feature === "pothole"
      ? streams.filter(
          (stream) =>
            (stream.running || (stream.source === "webcam" && stream.frame > 0)) &&
            stream.detections.length > 0
        )
      : [];

  /* =========================================
     UPDATE ONE CAMERA
  ========================================= */

  const updateStream = (id, changes) => {
    setStreams((current) =>
      current.map((stream) =>
        stream.id === id
          ? {
              ...stream,
              ...changes,
            }
          : stream
      )
    );
  };

  /* =========================================
     CLOSE ALL STREAMS
  ========================================= */

  const closeAllStreams = () => {
    Object.values(sockets.current).forEach((socket) => {
      try {
        socket.close();
      } catch (error) {
        console.log(error);
      }
    });

    sockets.current = {};

    Object.values(webcamRequests.current).forEach((request) => request.abort());
    webcamRequests.current = {};
  };

  /* =========================================
     RESET
  ========================================= */

  const resetStreams = () => {
    closeAllStreams();

    setStreams((current) =>
      current.map((stream) => createStream(stream.id))
    );
  };

  /* =========================================
     CHANGE MODEL
  ========================================= */

  const changeFeature = (nextFeature) => {
    closeAllStreams();

    setFeature(nextFeature);

    setStreams((current) =>
      current.map((stream) => createStream(stream.id))
    );
  };

  const addStream = () => {
    const id = nextStreamId.current++;
    setStreams((current) => [...current, createStream(id)]);
  };

  const removeStream = (id) => {
    removedStreams.current.add(id);

    const socket = sockets.current[id];
    if (socket) {
      socket.close();
      delete sockets.current[id];
    }

    webcamRequests.current[id]?.abort();
    delete webcamRequests.current[id];

    setStreams((current) =>
      current.filter((stream) => stream.id !== id)
    );
  };

  /* =========================================
     CLEANUP
  ========================================= */

  useEffect(() => {
    return () => {
      closeAllStreams();
    };
  }, []);

  /* =========================================
     SELECT VIDEO
  ========================================= */

  const chooseFile = (id, file) => {
    updateStream(id, {
      file,
      filename: "",
      image: "",
      detections: [],
      vehicleCounts: {},
      congestion: file ? "READY" : "WAITING",
      running: false,
      error: "",
      frame: 0,
    });
  };

  const changeSource = (id, source) => {
    stopStream(id);
    updateStream(id, {
      source,
      file: null,
      filename: "",
      image: "",
      detections: [],
      vehicleCounts: {},
      congestion: "WAITING",
      running: false,
      error: "",
      frame: 0,
    });
  };

  const applyFrameMessage = (id, message) => {
    updateStream(id, {
      image: message.annotated_image_base64
        ? `data:image/jpeg;base64,${message.annotated_image_base64}`
        : "",
      detections: message.detections || [],
      vehicleCounts: message.vehicle_counts || {},
      congestion: message.congestion_level || "RUNNING",
      frame: message.frame_number || 0,
      running: true,
      error: "",
    });
  };

  const connectCctv = (stream) => {
    if (!stream.rtspUrl.trim()) {
      updateStream(stream.id, { error: "Enter the camera's RTSP address first." });
      return;
    }

    updateStream(stream.id, {
      running: true,
      error: "",
      congestion: "CONNECTING",
      image: "",
      detections: [],
      vehicleCounts: {},
      frame: 0,
    });

    const ws = new WebSocket(
      getFeatureCctvWsUrl(feature, stream.rtspUrl.trim())
    );
    sockets.current[stream.id] = ws;

    ws.onopen = () => {
      updateStream(stream.id, { running: true, congestion: "RUNNING" });
    };
    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.type === "frame") applyFrameMessage(stream.id, message);
        if (message.type === "done") {
          updateStream(stream.id, { running: false, congestion: "FINISHED" });
        }
        if (message.type === "error") {
          updateStream(stream.id, {
            running: false,
            congestion: "ERROR",
            error: message.message || "Camera stream error.",
          });
        }
      } catch (error) {
        console.error(error);
        updateStream(stream.id, { error: "Invalid response from camera." });
      }
    };
    ws.onerror = () => updateStream(stream.id, {
      running: false,
      congestion: "ERROR",
      error: "Could not connect to this camera.",
    });
    ws.onclose = () => {
      if (sockets.current[stream.id] === ws) delete sockets.current[stream.id];
      updateStream(stream.id, { running: false });
    };
  };

  const captureWebcam = async (stream) => {
    const controller = new AbortController();
    webcamRequests.current[stream.id] = controller;
    updateStream(stream.id, {
      running: true,
      error: "",
      congestion: "CAPTURING",
      image: "",
      detections: [],
      vehicleCounts: {},
      frame: 0,
    });

    try {
      const { data } = await detectFeatureWebcam(
        feature,
        stream.cameraIndex,
        30,
        controller.signal
      );
      if (controller.signal.aborted) return;

      updateStream(stream.id, {
        image: data.annotated_image_base64
          ? `data:image/jpeg;base64,${data.annotated_image_base64}`
          : "",
        detections: data.detections || [],
        vehicleCounts: data.vehicle_counts || {},
        congestion: data.congestion_level || "FINISHED",
        frame: data.last_frame_number || data.frames_processed || 30,
        running: false,
        error: "",
      });
    } catch (error) {
      if (!controller.signal.aborted) {
        updateStream(stream.id, {
          running: false,
          congestion: "ERROR",
          error: error?.response?.data?.detail || "Could not capture this webcam.",
        });
      }
    } finally {
      if (webcamRequests.current[stream.id] === controller) {
        delete webcamRequests.current[stream.id];
      }
    }
  };

  /* =========================================
     START STREAM
  ========================================= */

  const startStream = async (id) => {
    const stream = streams.find(
      (item) => item.id === id
    );

    if (!stream?.file) {
      updateStream(id, {
        error: "Please select a video first.",
      });

      return;
    }

    if (stream.running) {
      return;
    }

    if (stream.source === "webcam") {
      captureWebcam(stream);
      return;
    }

    if (stream.source === "cctv") {
      connectCctv(stream);
      return;
    }

    try {
      updateStream(id, {
        running: true,
        error: "",
        congestion: "UPLOADING",
      });

      /* Upload video */

      const response = await uploadVideo(
        stream.file
      );

      const filename =
        response.data.filename;

      if (removedStreams.current.has(id)) {
        return;
      }

      updateStream(id, {
        filename,
        congestion: "CONNECTING",
      });

      /* Create separate WebSocket */

      const ws = new WebSocket(
        getMultistreamWsUrl(
          feature,
          filename,
          5
        )
      );

      sockets.current[id] = ws;

      /* =====================================
         WEBSOCKET OPEN
      ===================================== */

      ws.onopen = () => {
        updateStream(id, {
          running: true,
          congestion: "RUNNING",
        });
      };

      /* =====================================
         RECEIVE FRAME
      ===================================== */

      ws.onmessage = (event) => {
        try {
          const message =
            JSON.parse(event.data);

          /* FRAME */

          if (message.type === "frame") {
            applyFrameMessage(id, message);
          }

          /* FINISHED */

          if (message.type === "done") {
            updateStream(id, {
              running: false,
              congestion: "FINISHED",
            });
          }

          /* ERROR */

          if (message.type === "error") {
            updateStream(id, {
              running: false,
              congestion: "ERROR",
              error:
                message.message ||
                "Stream error",
            });
          }
        } catch (error) {
          console.error(error);

          updateStream(id, {
            error:
              "Invalid response from backend.",
          });
        }
      };

      /* =====================================
         WEBSOCKET ERROR
      ===================================== */

      ws.onerror = () => {
        updateStream(id, {
          running: false,
          congestion: "ERROR",
          error:
            "WebSocket connection failed.",
        });
      };

      /* =====================================
         WEBSOCKET CLOSE
      ===================================== */

      ws.onclose = () => {
        updateStream(id, {
          running: false,
        });

        if (
          sockets.current[id] === ws
        ) {
          delete sockets.current[id];
        }
      };
    } catch (error) {
      console.error(error);

      updateStream(id, {
        running: false,
        congestion: "ERROR",
        error:
          error?.response?.data?.detail ||
          "Could not start this stream.",
      });
    }
  };

  /* =========================================
     STOP STREAM
  ========================================= */

  const stopStream = (id) => {
    const socket =
      sockets.current[id];

    if (socket) {
      try {
        socket.close();
      } catch (error) {
        console.log(error);
      }

      delete sockets.current[id];
    }

    webcamRequests.current[id]?.abort();
    delete webcamRequests.current[id];

    updateStream(id, {
      running: false,
      congestion: "STOPPED",
    });
  };

  /* =========================================
     DETECTION COUNT
  ========================================= */

  const getDetectionCount = (stream) => {
    /* Traffic */

    if (feature === "traffic") {
      return Object.values(
        stream.vehicleCounts || {}
      ).reduce(
        (total, value) =>
          total + Number(value || 0),
        0
      );
    }

    /* Other models */

    return (
      stream.detections?.length || 0
    );
  };

  /* =========================================
     UI
  ========================================= */

  return (
    <div className="max-w-7xl mx-auto px-6 py-10">

      {/* HEADER */}

      <div className="mb-8">

        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-line bg-panel font-mono text-[10px] text-scan mb-4">

          <span className="h-1.5 w-1.5 rounded-full bg-scan animate-blink" />

          MULTI-VIDEO REVIEW

        </div>

        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-5">

          <div>

            <h1 className="font-display text-3xl sm:text-4xl font-semibold">
              Analyze multiple sources at once
            </h1>

            <p className="text-muted text-sm mt-2 max-w-2xl">
              Choose a video, webcam, or CCTV feed for each panel and select what to detect.
            </p>

          </div>

          <button
            onClick={resetStreams}
            className="rounded-full border border-line px-4 py-2 text-sm hover:bg-panel"
          >
            Reset panels
          </button>

        </div>

      </div>

      {/* MODEL SELECTOR */}

      <div className="rounded-xl border border-line bg-panel p-5 mb-8">

        <div className="text-xs uppercase tracking-widest text-muted font-mono mb-4">
          Choose what to look for
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">

          {FEATURES.map((item) => {

            const active =
              feature === item.key;

            return (
              <button
                key={item.key}
                onClick={() =>
                  changeFeature(item.key)
                }
                className={`text-left rounded-xl border p-4 transition-all ${
                  active
                    ? "border-safe bg-safe/10"
                    : "border-line bg-panel2 hover:border-ink/30"
                }`}
              >

                <div className="font-display font-semibold text-sm">
                  {item.label}
                </div>

                <div className="text-xs text-muted mt-1 leading-relaxed">
                  {item.description}
                </div>

              </button>
            );
          })}

        </div>

      </div>

      {/* CURRENT MODEL */}

      <div className="flex items-center justify-between mb-4">

        <div>

          <div className="font-display text-xl font-semibold">
            {selectedFeature.label}
          </div>

          <div className="text-xs text-muted font-mono mt-1">
            {streams.length} CAMERA PANEL{streams.length === 1 ? "" : "S"}
          </div>

        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={addStream}
            className="inline-flex items-center gap-2 rounded-full bg-safe px-4 py-2 text-sm font-semibold text-base"
          >
            <Plus size={16} aria-hidden="true" />
            Add another camera
          </button>

          <div className="rounded-full border border-safe/30 bg-safe/5 px-3 py-1 text-xs font-mono text-safe">
            MODEL: {feature.toUpperCase()}
          </div>
        </div>

      </div>

      {feature === "traffic" && (
        <section
          aria-live="polite"
          aria-label="High congestion alerts"
          className="mb-6 rounded-xl border border-alert/30 bg-alert/5 p-4"
        >
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <AlertTriangle
                size={18}
                className="text-alert"
                aria-hidden="true"
              />
              <h2 className="font-display font-semibold">
                High congestion alerts
              </h2>
            </div>
            <span className="rounded-full border border-alert/30 px-2.5 py-1 text-xs font-mono text-alert">
              {highCongestionStreams.length} active
            </span>
          </div>

          {highCongestionStreams.length > 0 ? (
            <ul className="mt-3 divide-y divide-alert/15">
              {highCongestionStreams.map((stream) => (
                <li
                  key={stream.id}
                  className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 py-2 text-sm"
                >
                  <span className="font-semibold">
                    Camera {stream.id} is reporting high congestion
                  </span>
                  <span className="font-mono text-xs text-muted">
                    {getDetectionCount(stream)} vehicles · frame {stream.frame}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-muted">
              No active cameras are reporting high congestion.
            </p>
          )}
        </section>
      )}

      {(feature === "garbage" || feature === "pothole") && (
        <section
          aria-live="polite"
          aria-label={`${selectedFeature.label} alerts`}
          className="mb-6 rounded-xl border border-alert/30 bg-alert/5 p-4"
        >
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <AlertTriangle
                size={18}
                className="text-alert"
                aria-hidden="true"
              />
              <h2 className="font-display font-semibold">
                {selectedFeature.label} alerts
              </h2>
            </div>
            <span className="rounded-full border border-alert/30 px-2.5 py-1 text-xs font-mono text-alert">
              {detectionAlertStreams.length} active
            </span>
          </div>

          {detectionAlertStreams.length > 0 ? (
            <ul className="mt-3 divide-y divide-alert/15">
              {detectionAlertStreams.map((stream) => {
                const labels = [
                  ...new Set(
                    stream.detections.map((detection) => detection.label)
                  ),
                ].join(", ");

                return (
                  <li
                    key={stream.id}
                    className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 py-2 text-sm"
                  >
                    <span className="font-semibold">
                      Camera {stream.id} has {feature === "garbage" ? "garbage" : "road damage"} detected
                    </span>
                    <span className="font-mono text-xs text-muted">
                      {stream.detections.length} detection{stream.detections.length === 1 ? "" : "s"}
                      {labels ? ` · ${labels}` : ""} · frame {stream.frame}
                    </span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-muted">
              No active cameras are reporting {feature === "garbage" ? "garbage" : "road damage"}.
            </p>
          )}
        </section>
      )}

      {/* CAMERA GRID */}

      <div className="grid md:grid-cols-2 gap-5">

        {streams.map((stream) => (

          <div
            key={stream.id}
            className="rounded-xl border border-line bg-panel overflow-hidden"
          >

            {/* CAMERA HEADER */}

            <div className="flex items-center justify-between px-4 py-3 border-b border-line">

              <div>

                <div className="font-display font-semibold">
                  Camera {stream.id}
                </div>

                <div className="text-[10px] text-muted font-mono uppercase tracking-widest">
                  {SOURCES.find((source) => source.id === stream.source)?.label} {stream.id}
                </div>

              </div>

              <div className="flex items-center gap-2">
                <div
                  className={`text-[10px] font-mono px-2 py-1 rounded-full border ${
                    stream.running
                      ? "text-safe border-safe/30 bg-safe/5"
                      : "text-muted border-line"
                  }`}
                >
                  {stream.running
                    ? "LIVE"
                    : stream.congestion}
                </div>

                <button
                  onClick={() => removeStream(stream.id)}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-line text-muted transition-colors hover:border-alert/40 hover:text-alert focus-visible:outline focus-visible:outline-2 focus-visible:outline-alert"
                  aria-label={`Delete Camera ${stream.id} video stream`}
                  title="Delete video stream"
                >
                  <Trash2 size={15} aria-hidden="true" />
                </button>
              </div>

            </div>

            <div className="flex gap-1 border-b border-line p-2">
              {SOURCES.map((source) => (
                <button
                  key={source.id}
                  type="button"
                  onClick={() => changeSource(stream.id, source.id)}
                  aria-pressed={stream.source === source.id}
                  className={`flex-1 rounded-lg px-3 py-2 text-sm transition-colors ${
                    stream.source === source.id
                      ? "bg-safe/10 text-safe"
                      : "text-muted hover:bg-panel2 hover:text-ink"
                  }`}
                >
                  {source.label}
                </button>
              ))}
            </div>

            {/* VIDEO */}

            <div className="aspect-video bg-black flex items-center justify-center">

              {stream.image ? (

                <img
                  src={stream.image}
                  alt={`Camera ${stream.id}`}
                  className="w-full h-full object-contain"
                />

              ) : (

                <div className="text-center text-muted">

                  <div className="text-sm font-display">
                    {stream.source === "video"
                      ? "Choose a video for this panel"
                      : stream.source === "webcam"
                        ? "Capture from a connected webcam"
                        : "Connect a CCTV camera"}
                  </div>

                  <div className="text-[10px] font-mono mt-1">
                    {stream.source === "video"
                      ? "Select a video file below to begin."
                      : stream.source === "webcam"
                        ? "Choose the camera index, then capture 30 frames."
                        : "Enter an RTSP address below to begin."}
                  </div>

                </div>

              )}

            </div>

            {/* CONTROLS */}

            <div className="p-4">

              {stream.source === "video" && (
                <>
                  <input
                    type="file"
                    accept="video/*"
                    className="block w-full text-xs text-muted file:mr-3 file:rounded-full file:border-0 file:bg-panel2 file:px-4 file:py-2 file:text-xs file:text-ink"
                    onChange={(event) =>
                      chooseFile(stream.id, event.target.files?.[0] || null)
                    }
                  />
                  {stream.file && (
                    <div className="mt-2 truncate text-[11px] font-mono text-muted">
                      {stream.file.name}
                    </div>
                  )}
                </>
              )}

              {stream.source === "webcam" && (
                <label className="block text-sm text-muted">
                  Camera index
                  <input
                    type="number"
                    min="0"
                    max="32"
                    value={stream.cameraIndex}
                    disabled={stream.running}
                    onChange={(event) => updateStream(stream.id, {
                      cameraIndex: Math.max(0, Number(event.target.value) || 0),
                    })}
                    className="ml-3 w-24 rounded-lg border border-line bg-panel2 px-3 py-2 text-ink"
                  />
                </label>
              )}

              {stream.source === "cctv" && (
                <label className="block text-sm text-muted">
                  RTSP address
                  <input
                    type="text"
                    value={stream.rtspUrl}
                    disabled={stream.running}
                    onChange={(event) => updateStream(stream.id, { rtspUrl: event.target.value })}
                    placeholder="rtsp://camera-address/stream"
                    className="mt-1.5 w-full rounded-lg border border-line bg-panel2 px-3 py-2.5 font-mono text-xs text-ink"
                  />
                </label>
              )}

              {/* STATS */}

              <div className="grid grid-cols-2 gap-3 mt-4">

                <div className="rounded-lg border border-line bg-panel2 p-3">

                  <div className="text-[10px] uppercase tracking-widest text-muted font-mono">
                    Detections
                  </div>

                  <div className="text-xl font-display font-semibold mt-1">
                    {getDetectionCount(
                      stream
                    )}
                  </div>

                </div>

                <div className="rounded-lg border border-line bg-panel2 p-3">

                  <div className="text-[10px] uppercase tracking-widest text-muted font-mono">
                    Frame
                  </div>

                  <div className="text-xl font-display font-semibold mt-1">
                    {stream.frame}
                  </div>

                </div>

              </div>

              {/* TRAFFIC COUNTS */}

              {feature === "traffic" &&
                Object.keys(
                  stream.vehicleCounts || {}
                ).length > 0 && (

                  <div className="mt-3 rounded-lg border border-line bg-panel2 p-3">

                    <div className="text-[10px] uppercase tracking-widest text-muted font-mono mb-2">
                      Vehicles
                    </div>

                    <div className="flex flex-wrap gap-2">

                      {Object.entries(
                        stream.vehicleCounts
                      ).map(
                        ([label, count]) => (

                          <span
                            key={label}
                            className="text-xs font-mono rounded-full border border-line px-2 py-1"
                          >
                            {label}: {count}
                          </span>

                        )
                      )}

                    </div>

                  </div>

                )}

              {/* ERROR */}

              {stream.error && (

                <div className="mt-3 rounded-lg border border-alert/30 bg-alert/5 px-3 py-2 text-xs text-alert font-mono">
                  {stream.error}
                </div>

              )}

              {/* BUTTON */}

              <div className="flex gap-2 mt-4">

                {!stream.running ? (

                  <button
                    onClick={() =>
                      startStream(stream.id)
                    }
                    className="flex-1 rounded-full bg-safe text-base font-semibold px-4 py-2.5"
                  >
                    {stream.source === "video"
                      ? "Analyze video"
                      : stream.source === "webcam"
                        ? "Capture webcam"
                        : "Connect to CCTV"}
                  </button>

                ) : (

                  <button
                    onClick={() =>
                      stopStream(
                        stream.id
                      )
                    }
                    className="flex-1 rounded-full bg-alert text-base font-semibold px-4 py-2.5"
                  >
                    Stop analysis
                  </button>

                )}

              </div>

            </div>

          </div>

        ))}

      </div>

      {/* INFORMATION */}

      <div className="mt-6 rounded-xl border border-line bg-panel px-5 py-4">

        <div className="text-xs font-mono text-muted leading-relaxed">

          <span className="text-safe">
            Getting started:
          </span>{" "}

          Choose a detection type, add a video to each panel, and start the
          analysis. Each video is processed separately.

        </div>

      </div>

    </div>
  );
}

