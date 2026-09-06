import type { NextConfig } from "next";

const config: NextConfig = {
  ...(process.env.RESEARCHASSISTANT_DESKTOP === "1" ? { output: "export" as const } : {}),
};

export default config;
