import markUrl from '../assets/logo/mark.svg'

// .kt-header/.kt-logo/.kt-wordmark, vendored from ../documentation/design/ui
// (admin-lab-plan.md §0.1) — drops .kt-searchbar, not used by this app.
export function Header() {
  return (
    <header className="kt-header">
      <a className="kt-logo" href="/" aria-label="קול תורה — לדף הבית">
        <img src={markUrl} alt="" width={21} height={28} />
        <span className="kt-wordmark">קול תורה</span>
      </a>
      <span className="kt-meta" style={{ flex: 1 }}>
        מעבדה — עיבוד שיעורים
      </span>
    </header>
  )
}
