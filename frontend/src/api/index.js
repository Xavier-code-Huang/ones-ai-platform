import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 30000 })

// 请求拦截: 自动添加 Token
api.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 响应拦截: 401 跳登录
api.interceptors.response.use(
  res => res.data,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default {
  // Auth
  login: (email, password) => api.post('/auth/login', { email, password }),
  me: () => api.get('/auth/me'),
  // Servers
  getServers: () => api.get('/servers'),
  verifyCredential: (serverId, data) => api.post(`/servers/${serverId}/verify`, data),
  getCredentials: (serverId) => api.get(`/servers/${serverId}/credentials`),
  deleteCredential: (serverId, credId) => api.delete(`/servers/${serverId}/credentials/${credId}`),
  addServer: (data) => api.post('/servers', data),
  checkHealth: (serverId) => api.post(`/servers/${serverId}/health`),
  // Tasks
  createTask: (data) => api.post('/tasks', data),
  getTasks: (params) => api.get('/tasks', { params }),
  getTask: (id) => api.get(`/tasks/${id}`),
  cancelTask: (id) => api.delete(`/tasks/${id}`),
  // Evaluations
  submitEval: (data) => api.post('/evaluations', data),
  // Admin
  getOverview: (days) => api.get('/admin/overview', { params: { days } }),
  getTrends: (days, granularity) => api.get('/admin/trends', { params: { days, granularity } }),
  getUserRankings: (days) => api.get('/admin/users', { params: { days } }),
  getUserDetail: (userId, days) => api.get(`/admin/users/${userId}/detail`, { params: { days } }),
  getEvalStats: (days) => api.get('/admin/evaluations/stats', { params: { days } }),
  getConfigs: () => api.get('/admin/configs'),
  updateConfigs: (configs) => api.post('/admin/configs', { configs }),
}
