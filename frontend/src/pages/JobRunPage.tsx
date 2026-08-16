import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { createJob, getJob, listLabLessons, listLessonJobs } from '../api/lab'
import type { LabJob } from '../api/lab'
import { JobStatusBadge } from '../components/JobStatusBadge'

// Mirrors lab/models.py's TranscriptionParams/DiarizationParams (server-side
// dict[str, Any] at the generic /api/lab/jobs boundary by design, AL §5.2 — these
// two shapes are hand-typed here rather than OpenAPI-generated because neither is
// ever a typed request/response body itself).
interface TranscriptionParamsInput {
  model_id: string
  beam_size: number
  initial_prompt: string
}

interface DiarizationParamsInput {
  model_id: string
}

const JOB_TYPE_DEFS = [
  {
    key: 'transcribe',
    label: 'תמלול',
    defaultParams: (): TranscriptionParamsInput => ({
      model_id: 'ivrit-ai/whisper-large-v3-turbo',
      beam_size: 5,
      initial_prompt: '',
    }),
  },
  {
    key: 'diarize',
    label: 'זיהוי דוברים',
    defaultParams: (): DiarizationParamsInput => ({ model_id: 'ivrit-ai/pyannote-speaker-diarization-3.1' }),
  },
] as const

export function JobRunPage() {
  const { lessonId } = useParams()
  const id = Number(lessonId)

  const { data: lessons } = useQuery({
    queryKey: ['lab', 'lessons', 'byId', id],
    queryFn: () => listLabLessons({ lessonIds: [id] }),
  })
  const lesson = lessons?.[0]

  const { data: initialJobs } = useQuery({
    queryKey: ['lab', 'lessons', id, 'jobs'],
    queryFn: () => listLessonJobs(id),
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--kt-space-5)' }}>
      <div className="kt-card">
        <h2>{lesson?.title_he ?? 'טוען...'}</h2>
        {lesson && (
          <p className="kt-meta">
            {lesson.rabbi_name_en} — {lesson.series_name_en}
          </p>
        )}
      </div>

      {initialJobs !== undefined &&
        JOB_TYPE_DEFS.map((def) => {
          const latest = initialJobs.find((j) => j.job_type === def.key)
          return (
            <JobTypePanel
              key={def.key}
              lessonId={id}
              jobTypeKey={def.key}
              label={def.label}
              defaultParams={def.defaultParams()}
              initialJob={latest}
            />
          )
        })}
    </div>
  )
}

function JobTypePanel({
  lessonId,
  jobTypeKey,
  label,
  defaultParams,
  initialJob,
}: {
  lessonId: number
  jobTypeKey: string
  label: string
  defaultParams: TranscriptionParamsInput | DiarizationParamsInput
  initialJob: LabJob | undefined
}) {
  const [jobId, setJobId] = useState<number | undefined>(initialJob?.id)
  const [showForm, setShowForm] = useState(initialJob === undefined)
  const [paramsText, setParamsText] = useState(() => JSON.stringify(defaultParams, null, 2))
  const [formError, setFormError] = useState<string | null>(null)

  const { data: job } = useQuery({
    queryKey: ['lab', 'job', jobId],
    queryFn: () => getJob(jobId as number),
    enabled: jobId !== undefined,
    initialData: jobId === initialJob?.id ? initialJob : undefined,
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 3000 : false),
  })

  const launchMutation = useMutation({
    mutationFn: () => {
      const params = JSON.parse(paramsText) as Record<string, unknown>
      return createJob({ lesson_id: lessonId, job_type: jobTypeKey, params })
    },
    onSuccess: (created) => {
      setFormError(null)
      setJobId(created.id)
      setShowForm(false)
    },
    onError: (e) => setFormError(e instanceof Error ? e.message : String(e)),
  })

  const isRunning = job?.status === 'running'

  return (
    <div className="kt-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3>{label}</h3>
        {job && <JobStatusBadge status={job.status} />}
      </div>

      {job && !showForm && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--kt-space-3)' }}>
          <p className="kt-meta">
            <span className="kt-time">{job.model_id}</span> · הופעל{' '}
            <span className="kt-time">{new Date(job.started_at).toLocaleString('he-IL')}</span>
          </p>
          {isRunning && <p>מריץ...</p>}
          {job.status === 'failed' && (
            <p className="kt-error" dir="ltr" style={{ textAlign: 'left', unicodeBidi: 'isolate' }}>
              {job.error}
            </p>
          )}
          {job.status === 'done' && job.result_json && (
            <details>
              <summary>תוצאה</summary>
              <pre
                dir="ltr"
                style={{
                  whiteSpace: 'pre-wrap',
                  fontSize: 'var(--kt-size-small)',
                  textAlign: 'left',
                  unicodeBidi: 'isolate',
                }}
              >
                {JSON.stringify(job.result_json, null, 2)}
              </pre>
            </details>
          )}
          {job.log && (
            <details>
              <summary>לוג</summary>
              <pre
                dir="ltr"
                style={{
                  whiteSpace: 'pre-wrap',
                  fontSize: 'var(--kt-size-small)',
                  textAlign: 'left',
                  unicodeBidi: 'isolate',
                }}
              >
                {job.log}
              </pre>
            </details>
          )}
          {!isRunning && (
            <button
              type="button"
              className="kt-btn kt-btn--secondary"
              onClick={() => {
                setShowForm(true)
                setParamsText(JSON.stringify(defaultParams, null, 2))
              }}
            >
              הרץ שוב
            </button>
          )}
        </div>
      )}

      {showForm && (
        <div className="kt-form">
          <div className="kt-field">
            <label htmlFor={`${jobTypeKey}-params`}>פרמטרים (JSON)</label>
            <textarea
              id={`${jobTypeKey}-params`}
              dir="ltr"
              rows={5}
              value={paramsText}
              onChange={(e) => setParamsText(e.target.value)}
            />
          </div>
          {formError && <p className="kt-error">{formError}</p>}
          <div className="kt-form-actions">
            <button type="button" className="kt-btn" onClick={() => launchMutation.mutate()}>
              הרץ
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
