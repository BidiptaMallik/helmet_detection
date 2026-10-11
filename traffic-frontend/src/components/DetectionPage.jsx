import { useEffect, useRef, useState } from "react";
import Loader from "./Loader.jsx";
import {
  detectFeatureImage,
  detectFeatureVideo,
  getFeatureCctvWsUrl,
} from "../api/client.js";

const MODES = [
  {
    id: "video",
    label: "Video",
    icon: "▶",
  },
  {
    id: "webcam",
    label: "Webcam",
    icon: "●",
  },
  {
    id: "cctv",
    label: "Network Camera",
    icon: "◉",
  },
];

export default function DetectionPage({
  feature,
  title,
  description,
  accent = "safe",
}) {
  const [mode, setMode] = useState("video");

  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);

  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  const [rtspUrl, setRtspUrl] = useState("");
  const [cctvStatus, setCctvStatus] = useState("idle");
  const [currentFrame, setCurrentFrame] = useState(null);
  const [frameCount, setFrameCount] = useState(0);

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const webcamTimer = useRef(null);
  const wsRef = useRef(null);
  const streamRef = useRef(null);

  /* ---------------------------------
     CLEANUP
  --------------------------------- */

  useEffect(() => {
    return () => {
      stopWebcam();
      wsRef.current?.close();
    };
  }, []);

  /* ---------------------------------
     CHANGE MODE
  --------------------------------- */

  const changeMode = (newMode) => {
    stopWebcam();

    wsRef.current?.close();

    setMode(newMode);
    setFile(null);
    setPreview(null);
    setResult(null);
    setError("");
    setCurrentFrame(null);
    setFrameCount(0);
    setCctvStatus("idle");
    setRunning(false);
  };

  /* ---------------------------------
     FILE
  --------------------------------- */

  const handleFile = (selectedFile) => {
    if (!selectedFile) return;

    setFile(selectedFile);
    setPreview(URL.createObjectURL(selectedFile));
    setResult(null);
    setError("");
  };

    /* ---------------------------------
      VIDEO
    --------------------------------- */

  const runFileDetection = async () => {
    if (!file) return;

    setRunning(true);
    setError("");
    setResult(null);

    try {
      const response = await detectFeatureVideo(feature, file);

      setResult(response.data);
    } catch (e) {
      setError(
        e?.response?.data?.detail ||
          "We couldn't analyze this file. Please try again."
      );
    } finally {
      setRunning(false);
    }
  };

  /* ---------------------------------
     WEBCAM
  --------------------------------- */

  const startWebcam = async () => {
    try {
      setError("");

      const stream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: false,
      });

      streamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }

      setCctvStatus("streaming");

      webcamTimer.current = setInterval(
        captureWebcamFrame,
        1000
      );
    } catch (e) {
      setError(
        "The webcam isn't available. Check your browser's camera permission and try again."
      );
      setCctvStatus("error");
    }
  };

  const captureWebcamFrame = async () => {
    if (
      !videoRef.current ||
      !canvasRef.current ||
      videoRef.current.readyState < 2
    ) {
      return;
    }

    const video = videoRef.current;
    const canvas = canvasRef.current;

    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;

    const ctx = canvas.getContext("2d");

    ctx.drawImage(
      video,
      0,
      0,
      canvas.width,
      canvas.height
    );

    canvas.toBlob(async (blob) => {
      if (!blob) return;

      try {
        const webcamFile = new File(
          [blob],
          `${feature}-webcam.jpg`,
          {
            type: "image/jpeg",
          }
        );

        const response = await detectFeatureImage(
          feature,
          webcamFile
        );

        if (response.data?.annotated_image_base64) {
          setCurrentFrame(
            response.data.annotated_image_base64
          );
        }

        setResult(response.data);
      } catch (e) {
        console.error("Webcam detection error:", e);
      }
    }, "image/jpeg");
  };

  const stopWebcam = () => {
    if (webcamTimer.current) {
      clearInterval(webcamTimer.current);
      webcamTimer.current = null;
    }

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => {
        track.stop();
      });

      streamRef.current = null;
    }

    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }

    setCctvStatus("idle");
  };

  /* ---------------------------------
     CCTV
  --------------------------------- */

  const connectCctv = () => {
    if (!rtspUrl.trim()) return;

    setError("");
    setCurrentFrame(null);
    setFrameCount(0);
    setCctvStatus("connecting");

    const ws = new WebSocket(
      getFeatureCctvWsUrl(
        feature,
        rtspUrl.trim()
      )
    );

    wsRef.current = ws;

    ws.onopen = () => {
      setCctvStatus("streaming");
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);

        if (msg.type === "frame") {
          setCurrentFrame(
            msg.annotated_image_base64
          );

          setFrameCount(
            msg.frame_number || 0
          );

          if (msg.result) {
            setResult(msg.result);
          }
        }

        if (msg.type === "done") {
          setCctvStatus("done");
        }

        if (msg.type === "error") {
          setError(msg.message);
          setCctvStatus("error");
        }
      } catch (e) {
        console.error(e);
      }
    };

    ws.onerror = () => {
      setError(
        "We couldn't connect to this camera. Check its RTSP address and try again."
      );

      setCctvStatus("error");
    };

    ws.onclose = () => {
      if (cctvStatus === "streaming") {
        setCctvStatus("done");
      }
    };
  };

  const disconnectCctv = () => {
    wsRef.current?.close();
    setCctvStatus("done");
  };

  /* ---------------------------------
     RESULTS
  --------------------------------- */

  const getDetectionCount = () => {
    if (!result) return 0;

    if (typeof result.detections_found === "number") {
      return result.detections_found;
    }

    if (Array.isArray(result.detections)) {
      return result.detections.length;
    }

    return 0;
  };

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">

      {/* HEADER */}
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-3">
          <span
            className={`h-2 w-2 rounded-full ${
              accent === "alert"
                ? "bg-alert"
                : accent === "scan"
                ? "bg-scan"
                : "bg-safe"
            }`}
          />

          <span className="font-mono text-xs uppercase tracking-widest text-muted">
            DETECTION TOOLS
          </span>
        </div>

        <h1 className="font-display text-4xl font-semibold">
          {title}
        </h1>

        <p className="text-muted text-sm mt-2 max-w-2xl">
          {description}
        </p>
      </div>

      {/* MODE BUTTONS */}
      <div className="flex flex-wrap gap-2 mb-8">

        {MODES.map((item) => (
          <button
            key={item.id}
            onClick={() => changeMode(item.id)}
            className={`flex items-center gap-2 px-5 py-2.5 rounded-full border font-medium text-sm transition-all ${
              mode === item.id
                ? "bg-safe text-base border-safe"
                : "border-line bg-panel text-muted hover:text-ink"
            }`}
          >
            <span>{item.icon}</span>
            {item.label}
          </button>
        ))}

      </div>

      {/* ERROR */}
      {error && (
        <div className="mb-6 rounded-lg border border-alert/30 bg-alert/5 px-4 py-3 text-sm text-alert font-mono">
          {error}
        </div>
      )}

      {/* =========================================
          VIDEO
      ========================================= */}

      {mode === "video" && (
        <div className="grid lg:grid-cols-2 gap-6">

          <div className="rounded-xl border border-line bg-panel p-5">

            <h2 className="font-display text-lg font-semibold mb-4">
              Video analysis
            </h2>

            <p className="text-sm text-muted mb-4">
              Choose a recorded clip to review.
            </p>

            <input
              type="file"
              accept="video/*"
              onChange={(e) =>
                handleFile(e.target.files?.[0])
              }
              className="mb-5"
            />

            {preview && (
              <video
                src={preview}
                controls
                className="w-full rounded-lg border border-line"
              />
            )}

            <button
              onClick={runFileDetection}
              disabled={!file || running}
              className="mt-5 w-full rounded-full bg-safe text-base font-semibold py-3 disabled:opacity-40"
            >
              {running
                ? "Analyzing video..."
                : "Analyze video"}
            </button>

          </div>

          <ResultPanel
            running={running}
            result={result}
            getDetectionCount={getDetectionCount}
          />

        </div>
      )}

      {/* =========================================
          WEBCAM
      ========================================= */}

      {mode === "webcam" && (
        <div className="grid lg:grid-cols-2 gap-6">

          <div className="rounded-xl border border-line bg-panel p-5">

            <div className="flex items-center justify-between mb-4">

              <h2 className="font-display text-lg font-semibold">
                Webcam detection
              </h2>

              <span className="font-mono text-xs text-muted">
                {cctvStatus.toUpperCase()}
              </span>

            </div>

            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className="w-full rounded-lg border border-line bg-black"
            />

            <canvas
              ref={canvasRef}
              className="hidden"
            />

            <div className="flex gap-3 mt-5">

              {cctvStatus !== "streaming" ? (
                <button
                  onClick={startWebcam}
                  className="flex-1 rounded-full bg-safe text-base font-semibold py-3"
                >
                  Start webcam
                </button>
              ) : (
                <button
                  onClick={stopWebcam}
                  className="flex-1 rounded-full border border-alert text-alert py-3 font-semibold"
                >
                  Stop webcam
                </button>
              )}

            </div>

          </div>

          <ResultPanel
            running={false}
            result={result}
            currentFrame={currentFrame}
            getDetectionCount={getDetectionCount}
          />

        </div>
      )}

      {/* =========================================
          CCTV
      ========================================= */}

      {mode === "cctv" && (
        <div className="grid lg:grid-cols-2 gap-6">

          <div className="rounded-xl border border-line bg-panel p-5">

            <h2 className="font-display text-lg font-semibold mb-2">
              Network camera
            </h2>

            <p className="text-muted text-sm mb-5">
              Enter the RTSP address for the camera you want to review.
            </p>

            <input
              type="text"
              value={rtspUrl}
              onChange={(e) =>
                setRtspUrl(e.target.value)
              }
              placeholder="rtsp://username:password@camera-ip:554/stream"
              disabled={
                cctvStatus === "streaming" ||
                cctvStatus === "connecting"
              }
              className="w-full bg-panel2 border border-line rounded-full px-4 py-3 text-sm font-mono focus:outline-none focus:border-safe/50"
            />

            {cctvStatus !== "streaming" &&
            cctvStatus !== "connecting" ? (
              <button
                onClick={connectCctv}
                disabled={!rtspUrl.trim()}
                className="mt-4 w-full rounded-full bg-safe text-base font-semibold py-3 disabled:opacity-40"
              >
                Connect to camera
              </button>
            ) : (
              <button
                onClick={disconnectCctv}
                className="mt-4 w-full rounded-full border border-alert text-alert py-3 font-semibold"
              >
                End camera session
              </button>
            )}

          </div>

          <div className="rounded-xl border border-line bg-panel p-5">

            <div className="flex items-center justify-between mb-4">
              <span className="font-mono text-xs text-muted">
                CAMERA FEED
              </span>

              <span className="font-mono text-xs text-muted">
                {cctvStatus === "streaming"
                  ? `FRAME ${frameCount}`
                  : cctvStatus.toUpperCase()}
              </span>
            </div>

            {currentFrame ? (
              <img
                src={`data:image/jpeg;base64,${currentFrame}`}
                alt="CCTV detection"
                className="w-full rounded-lg border border-line"
              />
            ) : (
              <div className="h-64 flex items-center justify-center text-sm text-muted font-mono">
                The camera feed will appear here after you connect.
              </div>
            )}

          </div>

        </div>
      )}

    </div>
  );
}


/* =========================================
   RESULT PANEL
========================================= */

function ResultPanel({
  running,
  result,
  currentFrame,
  getDetectionCount,
}) {
  return (
    <div className="rounded-xl border border-line bg-panel p-5">

      {running && (
        <Loader label="Analyzing your file..." />
      )}

      {!running && currentFrame && (
        <img
          src={`data:image/jpeg;base64,${currentFrame}`}
          alt="detection result"
          className="w-full rounded-lg border border-line mb-4"
        />
      )}

      {!running &&
        !currentFrame &&
        result?.annotated_image_base64 && (
          <img
            src={`data:image/jpeg;base64,${result.annotated_image_base64}`}
            alt="detection result"
            className="w-full rounded-lg border border-line mb-4"
          />
        )}

      {!running && !result && !currentFrame && (
        <div className="h-48 flex items-center justify-center text-sm text-muted font-mono">
          Detection results will appear here once analysis is complete.
        </div>
      )}

      {!running && result && (
        <div className="mt-4">

          <div className="grid grid-cols-2 gap-3">

            <div className="rounded-lg bg-panel2 border border-line p-4">
              <div className="text-xs text-muted font-mono uppercase">
                Detections
              </div>

              <div className="text-2xl font-display font-semibold mt-1">
                {getDetectionCount()}
              </div>
            </div>

            {result.density && (
              <div className="rounded-lg bg-panel2 border border-line p-4">
                <div className="text-xs text-muted font-mono uppercase">
                  Density
                </div>

                <div className="text-2xl font-display font-semibold mt-1">
                  {result.density}
                </div>
              </div>
            )}

          </div>

          {result.saved?.length > 0 && (
            <div className="mt-4">

              <div className="font-mono text-xs text-muted mb-2">
                RECORDED EVENTS
              </div>

              <div className="flex flex-wrap gap-2">
                {result.saved.map((item) => (
                  <span
                    key={item.id || item.plate_number}
                    className="px-3 py-1.5 rounded border border-line bg-panel2 text-sm font-mono"
                  >
                    {item.plate_number}
                  </span>
                ))}
              </div>

            </div>
          )}

        </div>
      )}

    </div>
  );
}