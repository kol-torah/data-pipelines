import { Routes, Route } from 'react-router-dom'
import { Header } from './components/Header'
import { HomePage } from './pages/HomePage'
import { RabbisPage } from './pages/RabbisPage'
import { SeriesPage } from './pages/SeriesPage'
import { SeriesDetailPage } from './pages/SeriesDetailPage'

function App() {
  return (
    <div className="kt-page">
      <Header />
      <main className="kt-main">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/rabbis" element={<RabbisPage />} />
          <Route path="/series" element={<SeriesPage />} />
          <Route path="/series/:seriesId" element={<SeriesDetailPage />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
