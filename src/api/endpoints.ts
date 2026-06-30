export const endpoints = {
  auth: {
    login: '/auth/login',
  },
  task: {
    create: '/task',
    status: (id: string) => `/task/${id}/status`,
    result: (id: string) => `/sessions/${id}`,
  },
  history: {
    list: '/sessions',
  },
  admin: {
    users: '/admin/users',
    updateRole: (id: string) => `/admin/users/${id}/role`,
    deleteUser: (id: string) => `/admin/users/${id}`,
    settings: '/settings',
    settingsDirector: '/settings/director',
    settingsWorker: (type: string) => `/settings/workers/${type}`,
    settingsWorkers: '/settings/workers',
    settingsSystem: '/settings/system',
    availableModels: '/settings/available-models',
    testConnection: (provider: string) => `/settings/test-connection/${provider}`,
  }
};
