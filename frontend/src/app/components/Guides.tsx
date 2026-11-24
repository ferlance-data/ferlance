// The guide video player and the one-time welcome tour (shown on the first visit to the app).

import { useState } from 'react';
import { GUIDES, TOUR_KEY, type Guide } from '../../lib/guides';
import { Link } from '../../lib/router';
import { Modal } from './ui';

export function GuideVideo({ guide, autoPlay = false }: { guide: Guide; autoPlay?: boolean }) {
  return (
    <video
      className="guide-video"
      controls
      playsInline
      muted={autoPlay}
      autoPlay={autoPlay}
      preload={autoPlay ? 'auto' : 'none'}
      poster={guide.poster}
      aria-label={`Video: ${guide.title}`}
    >
      <source src={guide.video} type="video/mp4" />
      Your browser cannot play this video.
    </video>
  );
}

export function tourSeen(): boolean {
  try {
    return localStorage.getItem(TOUR_KEY) === '1';
  } catch {
    return true; // storage blocked: never nag
  }
}

/** Offered once per browser, on the first visit after signing up or in. */
export function WelcomeTour() {
  const [open, setOpen] = useState(() => !tourSeen());
  if (!open) return null;
  const close = () => {
    try {
      localStorage.setItem(TOUR_KEY, '1');
    } catch {
      // ignore: the tour simply shows again next time
    }
    setOpen(false);
  };
  const first = GUIDES[0]!;
  return (
    <Modal label="Welcome to Ferlance" onClose={close}>
      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="card-title">Welcome to Ferlance</h2>
            <p className="card-subtitle">
              A one-minute tour of how the app helps you each day. You can find all the guides later under Help &amp; guides.
            </p>
          </div>
        </div>
        <div className="card-body form-grid">
          <GuideVideo guide={first} autoPlay />
          <div className="button-row">
            <Link className="btn btn-primary" to="/app/help" onClick={close}>
              See all guides
            </Link>
            <button className="btn btn-ghost" type="button" onClick={close}>
              Not now
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
