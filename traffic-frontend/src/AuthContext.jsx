import { useEffect, useState } from "react";
import { AuthContext } from "./authContext.js";
import {
  getCurrentUser,
  loginUser as requestLogin,
  logoutUser as requestLogout,
  registerUser as requestRegister,
  setupInitialAdmin as requestAdminSetup,
} from "./api/client.js";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    getCurrentUser()
      .then(({ data }) => {
        if (active) setUser(data.user);
      })
      .catch(() => {
        if (active) setUser(null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  const login = async (credentials) => {
    const { data } = await requestLogin(credentials);
    setUser(data.user);
    return data.user;
  };

  const register = async (details) => {
    const { data } = await requestRegister(details);
    setUser(data.user);
    return data.user;
  };

  const setupAdmin = async (details) => {
    const { data } = await requestAdminSetup(details);
    setUser(data.user);
    return data.user;
  };

  const logout = async () => {
    try {
      await requestLogout();
    } finally {
      setUser(null);
    }
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, setupAdmin, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
