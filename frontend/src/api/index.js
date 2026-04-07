import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 120000 })

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
  toggleServer: (serverId) => api.patch(`/servers/${serverId}/toggle`),
  getAgentDir: (serverId, credentialId) => api.get(`/servers/${serverId}/agent-dir`, { params: { credential_id: credentialId } }),
  saveAgentDir: (serverId, data) => api.put(`/servers/${serverId}/agent-dir`, data),
  // Tasks
  createTask: (data) => api.post('/tasks', data),
  getTasks: (params) => api.get('/tasks', { params }),
  getTask: (id) => api.get(`/tasks/${id}`),
  cancelTask: (id) => api.delete(`/tasks/${id}`),
  getTaskLogs: (id) => api.get(`/tasks/${id}/logs`),
  getTicketTerminalLogs: (taskId, ticketDbId) => api.get(`/tasks/${taskId}/tickets/${ticketDbId}/terminal-logs`),
  getTicketReport: (taskId, ticketId) => api.get(`/tasks/${taskId}/tickets/${ticketId}/report`),
  reworkTicket: (taskId, ticketId, data) => api.post(`/tasks/${taskId}/tickets/${ticketId}/rework`, data),
  getTicketPhases: (taskId, ticketDbId) => api.get(`/tasks/${taskId}/tickets/${ticketDbId}/phases`),
  editTicket: (taskId, ticketDbId, data) => api.put(`/tasks/${taskId}/tickets/${ticketDbId}`, data),
  getCodePaths: (serverId) => api.get('/tasks/code-paths', { params: { server_id: serverId } }),
  deleteCodePath: (pathId) => api.delete(`/tasks/code-paths/${pathId}`),
  previewTickets: (data) => api.post('/tasks/preview', data),
  // Containers
  getContainerStatus: (taskId, ticketDbId) => api.get(`/tasks/${taskId}/tickets/${ticketDbId}/container`),
  startContainer: (taskId, ticketDbId) => api.post(`/tasks/${taskId}/tickets/${ticketDbId}/container/start`),
  // Evaluations
  submitEval: (data) => api.post('/evaluations', data),
  // Admin
  getOverview: (days) => api.get('/admin/overview', { params: { days } }),
  getTrends: (days, granularity) => api.get('/admin/trends', { params: { days, granularity } }),
  getUserRankings: (days) => api.get('/admin/users', { params: { days } }),
  getUserDetail: (userId, days) => api.get(`/admin/users/${userId}/detail`, { params: { days } }),
  getUserTrends: (userId, days, granularity) => api.get(`/admin/users/${userId}/trends`, { params: { days, granularity } }),
  getEvalStats: (days) => api.get('/admin/evaluations/stats', { params: { days } }),
  getConfigs: () => api.get('/admin/configs'),
  updateConfigs: (configs) => api.post('/admin/configs', { configs }),
  // External Teams
  getExternalTeams: () => api.get('/admin/external-teams'),
  createExternalTeam: (data) => api.post('/admin/external-teams', data),
  deleteExternalTeam: (id) => api.delete(`/admin/external-teams/${id}`),
  getExternalTeamStats: (id, days) => api.get(`/admin/external-teams/${id}/stats`, { params: { days } }),
  getMemberLogs: (teamId, memberName, days) => api.get(`/admin/external-teams/${teamId}/members/${encodeURIComponent(memberName)}/logs`, { params: { days } }),
  getExternalOverview: (days) => api.get('/admin/external-overview', { params: { days } }),
  // Accuracy Evaluation
  getAccuracySummary: () => api.get('/accuracy/summary'),
  getAccuracyTickets: (page, pageSize, effectiveOnly) => api.get('/accuracy/tickets', { params: { page, page_size: pageSize, effective_only: effectiveOnly || undefined } }),
  batchAccuracyEval: (limit) => api.post('/accuracy/batch', null, { params: { limit }, timeout: 600000 }),
}
