"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export default function AuthCallback(): React.ReactElement {
  const router = useRouter();
  const [message, setMessage] = useState("Finishing sign-in…");

  useEffect(() => {
    const accessToken = new URLSearchParams(window.location.hash.replace(/^#/, "")).get("access_token");
    if (!accessToken) {
      const timer = window.setTimeout(() => setMessage("This sign-in link is missing its session. Request a new one."), 0);
      return () => window.clearTimeout(timer);
    }
    void fetch("/api/auth/session", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ access_token: accessToken }) }).then((response) => {
      if (!response.ok) throw new Error("session failed");
      router.replace("/");
    }).catch(() => setMessage("This sign-in link has expired. Request a new one."));
  }, [router]);

  return <main className="auth-callback"><p>{message}</p></main>;
}
