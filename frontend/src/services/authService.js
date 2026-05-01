import { buildSiemPath } from "../utils/siemPath";

export const loadCurrentSession = async () => {
  const res = await fetch(buildSiemPath("/auth/me"), {
    credentials: "include",
  });

  return res.json();
};

export const loginToDashboard = async (username, password) => {
  const res = await fetch(buildSiemPath("/login"), {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      username,
      password,
    }),
  });

  const data = await res.json();

  if (!res.ok) {
    throw new Error(data.error || "Login failed");
  }

  return data;
};

export const logoutFromDashboard = async () => {
  await fetch(buildSiemPath("/logout"), {
    method: "POST",
    credentials: "include",
  });
};
