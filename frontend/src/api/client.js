import axios from 'axios'
import { useAuthStore } from '../store/auth'

const api = axios.create({
  baseURL: '/api',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

let refreshPromise = null

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config
    if (
      error.response?.status === 401 &&
      !original._retry &&
      !original.url?.includes('/auth/login') &&
      !original.url?.includes('/auth/refresh')
    ) {
      original._retry = true
      if (!refreshPromise) {
        refreshPromise = api.post('/auth/refresh')
          .then((res) => {
            useAuthStore.getState().setAccessToken(res.data.access_token)
            return res.data.access_token
          })
          .catch(() => {
            useAuthStore.getState().logout()
            window.location.href = '/login'
            return null
          })
          .finally(() => { refreshPromise = null })
      }
      const newToken = await refreshPromise
      if (newToken) {
        original.headers.Authorization = `Bearer ${newToken}`
        return api(original)
      }
    }
    // `detail` is not always a string: FastAPI validation errors (422) send a
    // list of objects, and plan-limit errors (402) send {error, message, ...}.
    // Pages pass it straight to toast(), and React crashes on non-strings, so
    // flatten here. The original object stays on `data.detail_raw`.
    const data = error.response?.data
    const d = data?.detail
    if (d && typeof d !== 'string') {
      data.detail_raw = d
      data.detail = Array.isArray(d) ? d.map((e) => e.msg).join('; ') : d.message || 'Request failed'
    }
    return Promise.reject(error)
  }
)

export default api

export const authAPI = {
  login:    (email, password) =>
    api.post('/auth/login', new URLSearchParams({ username: email, password }), {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    }),
  register: (email, password, fullName) =>
    api.post('/auth/register', { email, password, full_name: fullName }),
  logout:   () => api.post('/auth/logout'),
  me:       () => api.get('/auth/me'),
  refresh:  () => api.post('/auth/refresh'),
  updateMe: (data) => api.patch('/auth/me', data),
  changePassword: (currentPassword, newPassword) =>
    api.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    }),
  forgotPassword:   (email) => api.post('/auth/forgot-password', { email }),
  resetPassword:    (token, newPassword) =>
    api.post('/auth/reset-password', { token, new_password: newPassword }),
  verifyEmail:      (token) => api.post('/auth/verify-email', { token }),
  sendVerification: () => api.post('/auth/send-verification'),
}

export const resumeAPI = {
  generate: (jdText, jdUrl, emphasis) =>
    api.post('/generate-resume', { jd_text: jdText, jd_url: jdUrl, emphasis }),
  status:   (jobId) => api.get(`/jobs/${jobId}/status`),
  download: (jobId) => `/api/download/${jobId}`,
}

export const jobsAPI = {
  list:            (params) => api.get('/jobs', { params }),
  get:             (jobId)  => api.get(`/jobs/${jobId}`),
  retry:           (jobId)  => api.post(`/jobs/${jobId}/retry`),
  delete:          (jobId)  => api.delete(`/jobs/${jobId}`),
  deleteAllFailed: ()       => api.delete('/jobs'),
  stats:           ()       => api.get('/stats'),
}

export const metabaseAPI = {
  importResume: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    // Must override the instance's JSON default, or axios serialises the
    // FormData to JSON and the backend never receives the file (422).
    // Long timeout: text extraction + LLM parse takes 10-30s.
    return api.post('/metabase/import-resume', fd, {
      timeout: 120000,
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  getPersonal:      ()     => api.get('/metabase/personal'),
  savePersonal:     (data) => api.post('/metabase/personal', data),
  getSkills:        ()     => api.get('/metabase/skills'),
  addSkill:         (data) => api.post('/metabase/skills', data),
  updateSkill:      (id, data) => api.patch(`/metabase/skills/${id}`, data),
  deleteSkill:      (id)   => api.delete(`/metabase/skills/${id}`),
  getProjects:      ()     => api.get('/metabase/projects'),
  addProject:       (data) => api.post('/metabase/projects', data),
  updateProject:    (id, data) => api.patch(`/metabase/projects/${id}`, data),
  deleteProject:    (id)   => api.delete(`/metabase/projects/${id}`),
  getExperience:    ()     => api.get('/metabase/experience'),
  addExperience:    (data) => api.post('/metabase/experience', data),
  updateExperience: (id, data) => api.patch(`/metabase/experience/${id}`, data),
  deleteExperience: (id)   => api.delete(`/metabase/experience/${id}`),
}

export const billingAPI = {
  plans:    ()     => api.get('/billing/plans'),
  status:   ()     => api.get('/billing/status'),
  checkout: (plan) => api.post('/billing/checkout', { plan }),
  sync:     (order_id) => api.post('/billing/sync', { order_id }),
  cancel:   ()     => api.post('/billing/cancel'),
}

export const contentAPI = {
  generateCoverLetter:  (data) => api.post('/cover-letter', data),
  listCoverLetters:     ()     => api.get('/cover-letters'),
  getCoverLetter:       (id)   => api.get(`/cover-letters/${id}`),
  deleteCoverLetter:    (id)   => api.delete(`/cover-letters/${id}`),

  generateInterviewPrep: (data) => api.post('/interview-prep', data),
  listInterviewPreps:    ()     => api.get('/interview-preps'),
  getInterviewPrep:      (id)   => api.get(`/interview-preps/${id}`),
  deleteInterviewPrep:   (id)   => api.delete(`/interview-preps/${id}`),
}

export const recommendationsAPI = {
  get:     (refresh = false) => api.get('/recommendations', { params: { refresh } }),
}
