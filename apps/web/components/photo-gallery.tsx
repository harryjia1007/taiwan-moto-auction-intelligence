"use client";

import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";

type PhotoGalleryProps = {
  images: string[];
  name: string;
  source: string;
  organization: string;
  plateNumber: string | null;
  sourceAuid: string;
  mediaNote?: string;
  href?: string;
  variant: "card" | "detail";
};

function PhotoAbsence({
  failed,
  source,
  organization,
  plateNumber,
  sourceAuid,
  mediaNote,
}: Omit<PhotoGalleryProps, "images" | "name" | "href" | "variant"> & { failed: boolean }) {
  const judicialCopy = "法院公告目前沒有可辨識的車輛影像";
  const defaultCopy = "官方來源頁未提供可供本站快取的車輛照片";

  return <div className={`photo-absence ${failed ? "photo-unavailable" : ""}`} role="img" aria-label={failed ? "官方照片暫時無法載入" : "官方未提供照片"}>
    <span>{failed ? "PHOTO CACHE UNAVAILABLE" : "NO ATTACHMENT"}</span>
    <strong>{failed ? "官方照片暫時無法載入" : "官方未提供照片"}</strong>
    <small>{failed ? "照片記錄存在，但簽名連結或快取目前無法讀取。" : mediaNote ?? (source === "judicial" ? judicialCopy : defaultCopy)}</small>
    <dl>
      <div><dt>來源</dt><dd>{organization}</dd></div>
      <div><dt>{plateNumber ? "車牌" : "來源編號"}</dt><dd>{plateNumber ?? sourceAuid}</dd></div>
    </dl>
  </div>;
}

export function PhotoGallery(props: PhotoGalleryProps) {
  const normalized = useMemo(() => [...new Set(props.images.filter(Boolean))], [props.images]);
  const [failed, setFailed] = useState<string[]>([]);
  const [active, setActive] = useState(0);
  const available = normalized.filter((url) => !failed.includes(url));
  const index = available.length ? Math.min(active, available.length - 1) : 0;
  const current = available[index];

  const move = (delta: number) => {
    if (available.length < 2) return;
    setActive((value) => (value + delta + available.length) % available.length);
  };

  const markFailed = (url: string) => {
    setFailed((urls) => urls.includes(url) ? urls : [...urls, url]);
    setActive(0);
  };

  if (!current) {
    return <PhotoAbsence
      failed={normalized.length > 0}
      source={props.source}
      organization={props.organization}
      plateNumber={props.plateNumber}
      sourceAuid={props.sourceAuid}
      mediaNote={props.mediaNote}
    />;
  }

  const image = <img
    src={current}
    alt={`${props.name} 官方照片 ${index + 1}／${available.length}`}
    loading={props.variant === "card" ? "lazy" : "eager"}
    decoding="async"
    onError={() => markFailed(current)}
  />;

  return <div
    className={`photo-gallery photo-gallery-${props.variant}`}
    aria-label={`共 ${available.length} 張官方照片`}
    tabIndex={available.length > 1 ? 0 : undefined}
    onKeyDown={(event) => {
      if (event.key === "ArrowLeft") { event.preventDefault(); move(-1); }
      if (event.key === "ArrowRight") { event.preventDefault(); move(1); }
    }}
  >
    {props.href ? <Link className="photo-main" href={props.href} aria-label={`查看 ${props.name} 詳細資料`}>{image}</Link> : <div className="photo-main">{image}</div>}
    {available.length > 1 && <>
      <button className="photo-arrow photo-arrow-prev" type="button" aria-label="上一張照片" onClick={() => move(-1)}><ChevronLeft aria-hidden="true"/></button>
      <button className="photo-arrow photo-arrow-next" type="button" aria-label="下一張照片" onClick={() => move(1)}><ChevronRight aria-hidden="true"/></button>
      <span className="photo-position" aria-live="polite">{index + 1} / {available.length}</span>
    </>}
    {props.variant === "detail" && available.length > 1 && <div className="photo-thumbnails" aria-label="選擇官方照片">
      {available.map((url, photoIndex) => <button
        type="button"
        key={url}
        className={photoIndex === index ? "active" : ""}
        aria-label={`顯示第 ${photoIndex + 1} 張官方照片`}
        aria-pressed={photoIndex === index}
        onClick={() => setActive(photoIndex)}
      ><img src={url} alt="" loading="lazy" decoding="async" onError={() => markFailed(url)}/></button>)}
    </div>}
  </div>;
}
