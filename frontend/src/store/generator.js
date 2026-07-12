/**
 * store/generator.js
 * Persists the generator state across tab navigation.
 * 
 * Without this, switching from Generate → Dashboard → Generate
 * loses the in-progress job and the result.
 */
import { create } from 'zustand'

export const useGeneratorStore = create((set) => ({
  // Input state
  mode:     'text',   // 'text' | 'url'
  jdText:   '',
  jdUrl:    '',
  emphasis: '',

  // Job state
  jobId:    null,
  loading:  false,
  step:     0,
  result:   null,
  error:    null,

  // Actions
  setMode:     (mode)     => set({ mode }),
  setJdText:   (jdText)   => set({ jdText }),
  setJdUrl:    (jdUrl)    => set({ jdUrl }),
  setEmphasis: (emphasis) => set({ emphasis }),
  setJobId:    (jobId)    => set({ jobId }),
  setLoading:  (loading)  => set({ loading }),
  setStep:     (step)     => set({ step }),
  setResult:   (result)   => set({ result, loading: false }),
  setError:    (error)    => set({ error, loading: false }),

  reset: () => set({
    jobId: null, loading: false, step: 0, result: null, error: null,
  }),
}))
