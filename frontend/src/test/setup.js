import '@testing-library/jest-dom/vitest'

// jsdom doesn't implement matchMedia — stub it so components that check
// system theme / reduced-motion preference don't throw during render.
window.matchMedia = window.matchMedia || function (query) {
  return {
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }
}
