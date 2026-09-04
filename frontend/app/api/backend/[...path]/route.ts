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

function formatError(error: unknown): string {
  if (error instanceof Error) {
    const cause = (error as Error & { cause?: unknown }).cause;
    if (cause instanceof Error) {
      return `${error.name}: ${error.message}; cause=${cause.name}: ${cause.message}`;
    }
    if (cause) {
      return `${error.name}: ${error.message}; cause=${String(cause)}`;
    }
    return `${error.name}: ${error.message}`;
  }
  return String(error);
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
  const attempts: Array<{ target: string; error: string; round: number }> = [];
  const bases = backendBases();
  const retryDelaysMs = [250, 800];

  for (let round = 0; round <= retryDelaysMs.length; round += 1) {
    for (const base of bases) {
      const targetUrl = `${base}${targetPath}`;
      try {
        const response = await fetch(targetUrl, {
          method: "GET",
          cache: "no-store",
          headers: {
            Accept: request.headers.get("accept") || "application/json",
          },
          signal: AbortSignal.timeout(4000),
        });

        return new Response(response.body, {
          status: response.status,
          headers: {
            "content-type": response.headers.get("content-type") || "application/json",
            "cache-control": "no-store",
          },
        });
      } catch (error) {
        attempts.push({ target: targetUrl, error: formatError(error), round: round + 1 });
      }
    }
    if (round < retryDelaysMs.length) {
      await new Promise((resolve) => setTimeout(resolve, retryDelaysMs[round]));
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
