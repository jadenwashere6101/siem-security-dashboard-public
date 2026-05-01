import { buildSiemPath } from "../utils/siemPath";

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
