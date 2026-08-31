const backendBase = (process.env.BACKEND_API_BASE_URL || "http://localhost:8000").replace(
  /\/+$/,
  "",
);

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
  const targetUrl = `${backendBase}/${pathSegments.join("/")}${incoming.search}`;

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
}
