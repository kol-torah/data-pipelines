/** Link to a lesson at its source.
 *
 *  `stopPropagation` because both lesson tables put this inside a row that is itself
 *  clickable — without it, following the link would also select the lesson or navigate
 *  the row.
 *
 *  The label is deliberately generic rather than "YouTube": 1,861 of the catalogue's
 *  lessons are YouTube watch pages, but the rest are direct media files, and the column
 *  should not claim otherwise. */
export function SourceLink({ url }: { url: string }) {
  let host: string
  try {
    host = new URL(url).hostname.replace(/^www\./, '')
  } catch {
    // A malformed url is still worth linking — the source is what it is.
    host = 'מקור'
  }
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      dir="ltr"
      className="kt-time"
      onClick={(e) => e.stopPropagation()}
    >
      {host}
    </a>
  )
}
