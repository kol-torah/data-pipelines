export interface HealthResponse {
  status: string
}

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch('/api/health')
  if (!res.ok) {
    throw new Error(`GET /api/health failed: ${res.status}`)
  }
  return res.json() as Promise<HealthResponse>
}
