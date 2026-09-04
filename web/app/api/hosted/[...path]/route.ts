import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ path: string[] }> };

function upstreamBase(): string {
  const configured = process.env.HOSTED_API_HOSTPORT ?? process.env.HOSTED_API_URL ?? "";
  if (!configured) return "";
  return configured.startsWith("http://") || configured.startsWith("https://") ? configured : `http://${configured}`;
}

export async function GET(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  return proxy(request, context);
}

export async function POST(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  return proxy(request, context);
}

export async function PUT(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  return proxy(request, context);
}

async function proxy(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  const origin = request.headers.get("origin");
  if (request.method !== "GET" && origin && origin !== request.nextUrl.origin) return NextResponse.json({ detail: "Same-origin request required." }, { status: 403 });
  const base = upstreamBase();
  if (!base) return NextResponse.json({ detail: "Hosted API is not configured." }, { status: 503 });
  const { path } = await context.params;
  const target = `${base.replace(/\/$/, "")}/${path.join("/")}${request.nextUrl.search}`;
  const session = request.cookies.get("ra_session")?.value;
  const headers = new Headers();
  headers.set("Accept", "application/json");
  if (session) headers.set("Authorization", `Bearer ${session}`);
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  const body = request.method === "GET" ? undefined : await request.arrayBuffer();
  try {
    const response = await fetch(target, { method: request.method, headers, body, cache: "no-store" });
    return new NextResponse(response.body, { status: response.status, headers: { "Content-Type": response.headers.get("content-type") ?? "application/json" } });
  } catch {
    return NextResponse.json({ detail: "Hosted API is temporarily unavailable." }, { status: 502 });
  }
}
