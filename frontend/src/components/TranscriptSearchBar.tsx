import type { TranscriptSearch } from '../lib/useTranscriptSearch'

// ▲/▼ rather than ‹/› deliberately: vertical arrows are unambiguous in an RTL
// layout, horizontal ones are not (merge-and-search-plan.md §4.3).
export function TranscriptSearchBar({ search }: { search: TranscriptSearch }) {
  const { query, setQuery, matchCount, currentMatch, next, previous, active } = search
  return (
    <div className="kt-search">
      <input
        type="search"
        value={query}
        placeholder="חיפוש בתמלול"
        aria-label="חיפוש בתמלול"
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            if (e.shiftKey) previous()
            else next()
          } else if (e.key === 'Escape') {
            setQuery('')
          }
        }}
      />
      {/* No "0 תוצאות" while the box is empty — that reads as a failed search. */}
      {active && (
        <span className="kt-meta kt-search-count">
          {matchCount === 0 ? (
            'אין תוצאות'
          ) : (
            <span className="kt-time">
              {currentMatch + 1} / {matchCount}
            </span>
          )}
        </span>
      )}
      <button
        type="button"
        className="kt-btn kt-btn--secondary"
        aria-label="התוצאה הקודמת"
        disabled={matchCount === 0}
        onClick={previous}
      >
        ▲
      </button>
      <button
        type="button"
        className="kt-btn kt-btn--secondary"
        aria-label="התוצאה הבאה"
        disabled={matchCount === 0}
        onClick={next}
      >
        ▼
      </button>
    </div>
  )
}
