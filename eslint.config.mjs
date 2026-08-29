import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    files: ["app/procurement/page.tsx"],
    rules: {
      "@next/next/no-html-link-for-pages": "off",
    },
  },
  {
    files: [
      "app/procurement/ProcurementWorkspaceV2.tsx",
      "app/procurement/ProcurementWorkspaceV4.tsx",
    ],
    rules: {
      "react-hooks/static-components": "off",
    },
  },
  {
    // ProcurementWorkspaceV13 is the explicit view-scoped I/O owner. Its effects
    // synchronously mark loading/reset pagination before starting or switching an
    // external request; request cancellation and stale-response protection remain
    // enforced by the scoped data client and component controllers.
    files: ["app/procurement/ProcurementWorkspaceV13.tsx"],
    rules: {
      "react-hooks/set-state-in-effect": "off",
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
