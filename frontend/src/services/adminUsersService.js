import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

export const loadAdminUsers = async () => {
  const res = await fetch(buildSiemPath("/admin/users"), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, []);

  if (!res.ok) {
    throw new Error(getApiErrorMessage(data, "Unable to load users", ["error"]));
  }

  return data;
};

export const createAdminUser = async ({ username, password, role }) => {
  const res = await fetch(buildSiemPath("/admin/users"), {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      username,
      password,
      role,
    }),
  });
  const data = await parseJsonResponse(res, {});

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to create user", ["error", "message"])
    );
  }

  return data;
};

export const updateAdminUserStatus = async (targetUsername, isActive) => {
  const res = await fetch(buildSiemPath(`/admin/users/${encodeURIComponent(targetUsername)}/status`), {
    method: "PATCH",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      is_active: isActive,
    }),
  });
  const data = await parseJsonResponse(res, {});

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to update user status", ["error", "message"])
    );
  }

  return data;
};

export const resetAdminUserPassword = async (targetUsername, password) => {
  const res = await fetch(buildSiemPath(`/admin/users/${encodeURIComponent(targetUsername)}/password`), {
    method: "PATCH",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      password,
    }),
  });
  const data = await parseJsonResponse(res, {});

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to update password", ["error", "message"])
    );
  }

  return data;
};

export const updateAdminUserRole = async (targetUsername, role) => {
  const res = await fetch(buildSiemPath(`/admin/users/${encodeURIComponent(targetUsername)}/role`), {
    method: "PATCH",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      role,
    }),
  });
  const data = await parseJsonResponse(res, {});

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to update user role", ["error", "message"])
    );
  }

  return data;
};
