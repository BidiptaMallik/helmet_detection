import DetectionPage from "../components/DetectionPage.jsx";

export default function Traffic() {
  return (
    <DetectionPage
      feature="traffic"
      title="Traffic Congestion Detection"
      description="Review cars, bikes, and rickshaws in a photo, video, webcam, or network camera feed, with an estimate of traffic density."
      accent="safe"
    />
  );
}