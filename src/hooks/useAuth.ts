import { useAuthStore } from '../store/authStore';

export function useAuth() {
  const { token, user, isAuthenticated, login, logout } = useAuthStore();

  return {
    token,
    user,
    isAuthenticated,
    login,
    logout,
    isSuperAdmin: user?.role === 'super_admin',
    isOperator: user?.role === 'operator',
  };
}
