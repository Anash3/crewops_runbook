import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type RouteContext = { params: Promise<{ path: string[] }> };

async function forward(request: NextRequest, context: RouteContext) {
  const segments = (await context.params).path;
  const path = `/api/${segments.map(encodeURIComponent).join("/")}`;
  const allowed = /^\/api\/(overview|runs(?:\/[a-f0-9]{32}(?:\/events)?)?|harness-runs(?:\/[a-f0-9]{32})?|approvals(?:\/[A-Za-z0-9_-]+\/(?:approve|reject))?|runbooks(?:\/[a-z0-9_]+)?)$/;
  if (!allowed.test(path)) {
    return Response.json({ detail: "Unknown API route" }, { status: 404 });
  }

  const backend = process.env.BACKEND_API_URL || "http://127.0.0.1:8001";
  const isDecision = /^\/api\/approvals\/[^/]+\/(approve|reject)$/.test(path);
  const key = isDecision
    ? process.env.RUNBOOK_APPROVAL_API_KEY
    : process.env.BACKEND_API_KEY;
  const headers = new Headers();
  if (key) headers.set("Authorization", `Bearer ${key}`);
  if (request.method === "POST") headers.set("Content-Type", "application/json");
  if (request.headers.has("last-event-id")) {
    headers.set("Last-Event-ID", request.headers.get("last-event-id")!);
  }

  try {
    const upstream = await fetch(`${backend}${path}`, {
      method: request.method,
      headers,
      body: request.method === "POST" ? await request.text() : undefined,
      cache: "no-store",
      signal: request.signal,
    });
    const responseHeaders = new Headers({
      "Content-Type": upstream.headers.get("content-type") || "application/json",
      "Cache-Control": "no-store",
    });
    if (path.endsWith("/events")) {
      responseHeaders.set("X-Accel-Buffering", "no");
      return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
    }
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return Response.json({ detail: "CrewOps backend is unavailable" }, { status: 502 });
  }
}

export async function GET(request: NextRequest, context: RouteContext) {
  return forward(request, context);
}

export async function POST(request: NextRequest, context: RouteContext) {
  return forward(request, context);
}
