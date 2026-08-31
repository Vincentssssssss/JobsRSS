function normalizeBase(value: string): string {
  return (value || "").trim().replace(/\/+$/, "");
}

function backendBases(): string[] {
  const fromList = (process.env.BACKEND_API_BASE_URLS || "")
    .split(",")
    .map((item) => normalizeBase(item))
    .filter(Boolean);
  const fromSingle = normalizeBase(process.env.BACKEND_API_BASE_URL || "");
  const defaults = ["http://api:8000", "http://host.docker.internal:8000"];
  return Array.from(
    new Set([...fromList, fromSingle, ...defaults].map((item) => normalizeBase(item)).filter(Boolean))
  );
}

type RouteContext = {
  params: Promise<{ path: string[] }> | { path: string[] };
};

async function getPathSegments(context: RouteContext): Promise<string[]> {
  const resolved = await context.params;
  return resolved.path || [];
}

export async function GET(request: Request, context: RouteContext): Promise<Response> {
  const pathSegments = await getPathSegments(context);
  const incoming = new URL(request.url);
  const targetPath = `/${pathSegments.join("/")}${incoming.search}`;
  const attempts: Array<{ target: string; error: string }> = [];

  for (const base of backendBases()) {
    const targetUrl = `${base}${targetPath}`;
    try {
      const response = await fetch(targetUrl, {
        method: "GET",
        cache: "no-store",
        headers: {
          Accept: request.headers.get("accept") || "application/json",
        },
      });

      return new Response(response.body, {
        status: response.status,
        headers: {
          "content-type": response.headers.get("content-type") || "application/json",
          "cache-control": "no-store",
        },
      });
    } catch (error) {
      attempts.push({ target: targetUrl, error: String(error) });
    }
  }

  return Response.json(
    {
      detail: "backend_unavailable",
      attempts,
    },
    {
      status: 502,
      headers: {
        "cache-control": "no-store",
      },
    }
  );
}
