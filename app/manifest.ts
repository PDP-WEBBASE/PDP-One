import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "PDP One",
    short_name: "PDP One",
    description: "سامانه یکپارچه مدیریت پروژه، قرارداد و مناقصات",
    start_url: "/",
    display: "standalone",
    background_color: "#f3f6f7",
    theme_color: "#0b2236",
    lang: "fa",
    dir: "rtl",
    icons: [{ src: "/favicon.svg", sizes: "any", type: "image/svg+xml" }],
  };
}

