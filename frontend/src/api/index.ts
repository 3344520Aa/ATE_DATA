import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 0, // 0 means no timeout, crucial for large file uploads
})

// 请求拦截器，自动带上token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    // For blob responses, return the full response so callers can access headers
    if (response.config.responseType === 'blob') {
      return response
    }
    return response.data
  },
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(error.response?.data?.detail || '请求失败')
  }
)

export { api }
export default api