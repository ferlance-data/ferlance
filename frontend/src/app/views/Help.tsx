// Help & guides: a short video and the steps for each everyday situation. Reachable from the menu
// at any time; the first-visit tour lives in components/Guides.tsx.

import { useEffect } from 'react';
import { GUIDES, TOUR_KEY, type Guide } from '../../lib/guides';
import { Link } from '../../lib/router';
import { GuideVideo } from '../components/Guides';

function GuideCard({ guide }: { guide: Guide }) {
  return (
    <article className="card guide-card" id={`guide-${guide.slug}`}>
      <GuideVideo guide={guide} />
      <div className="guide-text">
        <h2 className="card-title">{guide.title}</h2>
        <p>
          <strong>When: </strong>
          {guide.when}
        </p>
        <p className="muted">
          <strong>Why: </strong>
          {guide.why}
        </p>
        <ol className="guide-steps">
          {guide.steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
        <Link className="btn btn-secondary btn-sm" to={`/app/${guide.page}`}>
          Go there
        </Link>
      </div>
    </article>
  );
}

export default function Help() {
  useEffect(() => {
    try {
      localStorage.setItem(TOUR_KEY, '1'); // already here: no need for the welcome tour
    } catch {
      // storage blocked
    }
  }, []);
  return (
    <div className="stack" id="help">
      {GUIDES.map((guide) => (
        <GuideCard key={guide.slug} guide={guide} />
      ))}
    </div>
  );
}
