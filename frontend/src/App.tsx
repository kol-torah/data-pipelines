import { Routes, Route } from 'react-router-dom'
import { Header } from './components/Header'
import { HomePage } from './pages/HomePage'
import { SpeakersPage } from './pages/SpeakersPage'
import { SeriesPage } from './pages/SeriesPage'
import { SeriesDetailPage } from './pages/SeriesDetailPage'
import { LessonPickerPage } from './pages/LessonPickerPage'
import { JobRunPage } from './pages/JobRunPage'

function App() {
  return (
    <div className="kt-page">
      <Header />
      <main className="kt-main">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/speakers" element={<SpeakersPage />} />
          <Route path="/series" element={<SeriesPage />} />
          <Route path="/series/:seriesId" element={<SeriesDetailPage />} />
          <Route path="/lab" element={<LessonPickerPage />} />
          <Route path="/lab/lessons/:lessonId" element={<JobRunPage />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
