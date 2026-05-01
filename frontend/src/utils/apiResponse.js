export const parseJsonResponse = async (response, fallbackValue) => {
  return response.json().catch(() => fallbackValue);
};

export const getApiErrorMessage = (
  data,
  fallbackMessage,
  fields = ["error", "message"]
) => {
  for (const field of fields) {
    if (data?.[field]) {
      return data[field];
    }
  }

  return fallbackMessage;
};
