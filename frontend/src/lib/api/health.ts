const baseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

export type Health = {
  status: "ok";
  service: "ml-studio-api";
  database: "ready";
};

export async function getHealth(signal?: AbortSignal): Promise<Health> {
  const response = await fetch(baseUrl.replace(/\/$/, "") + "/health", {
    cache: "no-store",
    signal: signal
      ? AbortSignal.any([signal, AbortSignal.timeout(5000)])
      : AbortSignal.timeout(5000),
  });
  if (!response.ok) throw new Error("Backend unavailable");
  const data: unknown = await response.json();
  if (
    typeof data !== "object" ||
    data === null ||
    !("status" in data) || data.status !== "ok" ||
    !("service" in data) || data.service !== "ml-studio-api" ||
    !("database" in data) || data.database !== "ready"
  ) {
    throw new Error("Unexpected health response");
  }
  return { status: "ok", service: "ml-studio-api", database: "ready" };
}
