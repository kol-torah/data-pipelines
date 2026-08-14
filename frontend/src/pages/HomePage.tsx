import { useQuery } from '@tanstack/react-query'
import { getHealth } from '../api/health'

export function HomePage() {
  const { data, error, isPending } = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
  })

  return (
    <div className="kt-card">
      <h2>בדיקת חיבור לשרת</h2>
      {isPending && <p>בודק חיבור...</p>}
      {error && <p>שגיאה: {error.message}</p>}
      {data && <p className="kt-time">status: {data.status}</p>}
    </div>
  )
}
