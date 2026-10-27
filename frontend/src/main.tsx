import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource/graduate/400.css'
import '@fontsource/cormorant-garamond/500.css'
import '@fontsource/cormorant-garamond/600.css'
import '@fontsource/lato/400.css'
import '@fontsource/lato/700.css'
import './index.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
