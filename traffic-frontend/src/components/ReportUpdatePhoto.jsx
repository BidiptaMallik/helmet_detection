import { useEffect, useState } from "react";
import {
  getAdminReportUpdatePhoto,
  getMyReportUpdatePhoto,
} from "../api/client.js";

export default function ReportUpdatePhoto({ reportId, updateId, admin = false }) {
  const [source, setSource] = useState("");

  useEffect(() => {
    let active = true;
    let objectUrl = "";
    const loadPhoto = admin
      ? getAdminReportUpdatePhoto
      : getMyReportUpdatePhoto;

    loadPhoto(reportId, updateId)
      .then(({ data }) => {
        objectUrl = URL.createObjectURL(data);
        if (active) setSource(objectUrl);
      })
      .catch(() => {
        if (active) setSource("");
      });

    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [admin, reportId, updateId]);

  if (!source) return null;

  return (
    <img
      src={source}
      alt="Photo attached to this report update"
      className="mt-3 max-h-72 w-auto max-w-full rounded-lg border border-line object-contain"
    />
  );
}