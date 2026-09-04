import { NextRequest, NextResponse } from "next/server";

function upstreamErrorCode(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") return null;
  for (const key of ["error_code", "code", "error"]) {
    const value = (payload as Record<string, unknown>)[key];
    if (typeof value === "string" && value.trim()) return value.trim().toLowerCase();
  }
  return null;
}

function safeSupabaseFailure(status: number, payload: unknown): string {
  const code = upstreamErrorCode(payload);
  if (status === 429 || code === "over_email_send_rate_limit") {
    return "Too many sign-in emails were requested. Wait a moment, then try again.";
  }
  if (code === "email_address_invalid" || code === "validation_failed") {
    return "Supabase rejected this email address. Check it and try again.";
  }
  if (code === "email_provider_disabled") {
    return "Email sign-in is disabled in Supabase Auth. Enable it, then try again.";
  }
  return "Supabase could not send the sign-in email. Check the Auth email settings and try again.";
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const payload = (await request.json().catch(() => null)) as { email?: unknown } | null;
  const email = typeof payload?.email === "string" ? payload.email.trim() : "";
  if (!email || !email.includes("@") || email.length > 320) return NextResponse.json({ detail: "Enter a valid email address." }, { status: 400 });
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) return NextResponse.json({ detail: "Sign-in is not configured." }, { status: 503 });
  try {
    const response = await fetch(`${url.replace(/\/$/, "")}/auth/v1/otp`, {
      method: "POST",
      headers: { apikey: key, "Content-Type": "application/json" },
      body: JSON.stringify({ email, create_user: true, redirect_to: new URL("/auth/callback", request.url).toString() }),
      cache: "no-store",
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      return NextResponse.json({ detail: safeSupabaseFailure(response.status, payload) }, { status: 502 });
    }
    return NextResponse.json({ sent: true });
  } catch {
    return NextResponse.json({ detail: "Supabase is temporarily unreachable. Try again in a moment." }, { status: 502 });
  }
}
