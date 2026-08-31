import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const payload = (await request.json().catch(() => null)) as { email?: unknown } | null;
  const email = typeof payload?.email === "string" ? payload.email.trim() : "";
  if (!email || !email.includes("@") || email.length > 320) return NextResponse.json({ detail: "Enter a valid email address." }, { status: 400 });
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) return NextResponse.json({ detail: "Sign-in is not configured." }, { status: 503 });
  const response = await fetch(`${url.replace(/\/$/, "")}/auth/v1/otp`, {
    method: "POST",
    headers: { apikey: key, "Content-Type": "application/json" },
    body: JSON.stringify({ email, create_user: true, email_redirect_to: new URL("/auth/callback", request.url).toString() }),
    cache: "no-store",
  });
  if (!response.ok) return NextResponse.json({ detail: "The sign-in link could not be sent." }, { status: 502 });
  return NextResponse.json({ sent: true });
}
