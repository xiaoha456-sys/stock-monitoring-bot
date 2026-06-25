import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.stockmonitor.brief",
  appName: "持仓简报",
  webDir: "dist",
  server: {
    androidScheme: "https",
  },
};

export default config;
