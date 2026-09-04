import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const payload = (await request.json().catch(() => null)) as { access_token?: unknown } | null;
  const accessToken = typeof payload?.access_token === "string" ? payload.access_token : "";
  if (!accessToken) return NextResponse.json({ detail: "The session could not be established." }, { status: 400 });
  // The private API is the canonical JWT verifier. This web-tier cookie is only
  // a transport for that bearer token; it is never used as an authorization
  // decision by the Next.js routes themselves.
  const result = NextResponse.json({ signed_in: true });
  result.cookies.set("ra_session", accessToken, { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", path: "/", maxAge: 60 * 60 * 8 });
  return result;
}
