import { NextResponse } from "next/server";

export async function POST(): Promise<NextResponse> {
  const result = NextResponse.json({ signed_out: true });
  result.cookies.set("ra_session", "", { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", path: "/", maxAge: 0 });
  return result;
}
