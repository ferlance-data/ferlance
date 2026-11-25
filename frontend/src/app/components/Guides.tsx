// The guide video player and the one-time welcome tour (shown on the first visit to the app).

import { useState } from 'react';
import {
  GUIDE_LANGS,
  GUIDES,
  LANG_KEY,
  TOUR_KEY,
  guideScript,
  guideVideo,
  isGuideLang,
  type Guide,
  type GuideLang,
} from '../../lib/guides';
import { Link } from '../../lib/router';
import { Modal, Segmented } from './ui';

function savedLang(): GuideLang {
  try {
    const saved = localStorage.getItem(LANG_KEY);
    return isGuideLang(saved) ? saved : 'en';
  } catch {
    return 'en';
  }
}

/** The viewer's narration language, remembered in this browser. */
export function useGuideLang(): [GuideLang, (lang: GuideLang) => void] {
  const [lang, setLang] = useState<GuideLang>(savedLang);
  const choose = (next: GuideLang) => {
    setLang(next);
    try {
      localStorage.setItem(LANG_KEY, next);
    } catch {
      // storage blocked: the choice lasts until the page closes
    }
  };
  return [lang, choose];
}

export function LangPicker({ lang, onChange }: { lang: GuideLang; onChange: (lang: GuideLang) => void }) {
  return (
    <Segmented
      label="Narration language"
      value={lang}
      onChange={onChange}
      options={GUIDE_LANGS.map((item) => ({ value: item.code, label: item.label }))}
    />
  );
}

export function GuideVideo({ guide, lang }: { guide: Guide; lang: GuideLang }) {
  const draft = GUIDE_LANGS.find((item) => item.code === lang)?.draft;
  return (
    <div className="guide-player">
      {/* Keyed by language so switching swaps the narrated file. */}
      <video
        key={lang}
        className="guide-video"
        controls
        playsInline
        preload="none"
        poster={guide.poster}
        aria-label={`Video: ${guide.title}`}
      >
        <source src={guideVideo(guide.slug, lang)} type="video/mp4" />
        Your browser cannot play this video.
      </video>
      <details className="guide-script">
        <summary>What the voice says{draft ? ' (draft translation)' : ''}</summary>
        <p lang={lang === 'fat' ? 'fat' : lang}>{guideScript(guide.slug, lang)}</p>
      </details>
    </div>
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
  const [lang, setLang] = useGuideLang();
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
              A one-minute tour of how the app helps you each day, with a voice in your language. Press play. You can find all the guides
              later under Help &amp; guides.
            </p>
          </div>
        </div>
        <div className="card-body form-grid">
          <LangPicker lang={lang} onChange={setLang} />
          <GuideVideo guide={first} lang={lang} />
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
