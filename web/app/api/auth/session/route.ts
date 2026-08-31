import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const payload = (await request.json().catch(() => null)) as { access_token?: unknown } | null;
  const accessToken = typeof payload?.access_token === "string" ? payload.access_token : "";
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!accessToken || !url || !key) return NextResponse.json({ detail: "The session could not be established." }, { status: 400 });
  const response = await fetch(`${url.replace(/\/$/, "")}/auth/v1/user`, { headers: { apikey: key, Authorization: `Bearer ${accessToken}` }, cache: "no-store" });
  if (!response.ok) return NextResponse.json({ detail: "The sign-in session is invalid or expired." }, { status: 401 });
  const result = NextResponse.json({ signed_in: true });
  result.cookies.set("ra_session", accessToken, { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", path: "/", maxAge: 60 * 60 * 8 });
  return result;
}
