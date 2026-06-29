export const endpoints = {
  auth: {
    login: '/api/auth/login',
  },
  task: {
    create: '/api/task',
    status: (id: string) => `/api/task/${id}/status`,
    result: (id: string) => `/api/sessions/${id}`,
  },
  history: {
    list: '/api/sessions',
  },
  admin: {
    users: '/api/admin/users',
    updateRole: (id: string) => `/api/admin/users/${id}/role`,
    deleteUser: (id: string) => `/api/admin/users/${id}`,
    settings: '/api/settings',
    settingsDirector: '/api/settings/director',
    settingsWorker: (type: string) => `/api/settings/workers/${type}`,
    settingsWorkers: '/api/settings/workers',
    settingsSystem: '/api/settings/system',
    availableModels: '/api/settings/available-models',
    testConnection: (provider: string) => `/api/settings/test-connection/${provider}`,
  }
};
